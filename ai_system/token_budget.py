"""
Token budget management plus an optional monkey-patch for `backend.query()`.

Key points:
- Budget state uses `contextvars.ContextVar` instead of a global mutable slot.
- Shell-level LLM calls can charge a specific budget explicitly.
- Agent-side LLM calls can be charged implicitly when `backend.query()` is patched.
"""

import contextvars
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

FALLBACK_COST_PER_CALL_USD = 0.005


class BudgetExhaustedException(Exception):
    """Raised when a founder's budget is exhausted."""


class TokenBudget:
    """Per-founder token budget with basic thread safety."""

    def __init__(self, initial_usd: float):
        self.remaining_usd = float(initial_usd)
        self.total_consumed_usd = 0.0
        self.deduct_call_count = 0
        self._lock = threading.Lock()

    def can_afford(self, estimated_cost_usd: float = 0.0) -> bool:
        with self._lock:
            return (self.remaining_usd - estimated_cost_usd) > 0

    def deduct(self, cost_usd: float, raise_on_empty: bool = True):
        with self._lock:
            self.remaining_usd -= cost_usd
            self.total_consumed_usd += cost_usd
            self.deduct_call_count += 1
            exhausted = self.remaining_usd <= 0
            remaining = self.remaining_usd
            consumed = self.total_consumed_usd
        if raise_on_empty and exhausted:
            raise BudgetExhaustedException(
                f"预算耗尽 (剩余 ${remaining:.4f}, 已消耗 ${consumed:.4f})"
            )

    def replenish(self, amount_usd: float):
        with self._lock:
            self.remaining_usd += amount_usd

    def summary(self) -> dict:
        with self._lock:
            return {
                "remaining_usd": round(self.remaining_usd, 4),
                "total_consumed_usd": round(self.total_consumed_usd, 4),
                "deduct_calls": self.deduct_call_count,
            }


_budget_ctx: contextvars.ContextVar[Optional[TokenBudget]] = contextvars.ContextVar(
    "_budget_ctx", default=None
)
_original_query: Optional[Callable] = None
_apply_lock = threading.Lock()


def set_budget(budget: TokenBudget) -> contextvars.Token:
    return _budget_ctx.set(budget)


def reset_budget(token: contextvars.Token):
    _budget_ctx.reset(token)


def clear_budget():
    _budget_ctx.set(None)


def get_budget() -> Optional[TokenBudget]:
    return _budget_ctx.get()


class _TokenTrackerDeltaReader:
    """Reads incremental token usage from the shared token tracker."""

    def __init__(self):
        self._local = threading.local()

    def _get_prev(self):
        if not hasattr(self._local, "prev"):
            self._local.prev = {}
        return self._local.prev

    def _resolve_model(self, model: str):
        try:
            from ai_scientist.utils.token_tracker import token_tracker
        except Exception:
            return model, None, None

        counts = token_tracker.token_counts.get(model)
        counts_model = model
        if counts is None:
            for key in token_tracker.token_counts.keys():
                if key.startswith(model) or model.startswith(key):
                    counts = token_tracker.token_counts[key]
                    counts_model = key
                    break

        model_prices = getattr(token_tracker, "MODEL_PRICES", {})
        prices = model_prices.get(counts_model) or model_prices.get(model)
        if not prices:
            for known_model, known_prices in model_prices.items():
                if (
                    counts_model.startswith(known_model)
                    or known_model.startswith(counts_model)
                    or model.startswith(known_model)
                    or known_model.startswith(model)
                ):
                    prices = known_prices
                    break

        return counts_model, counts, prices

    def take_snapshot(self, model: str) -> dict:
        counts_model, counts, _ = self._resolve_model(model)
        if not counts:
            return {
                "model": counts_model,
                "prompt": 0,
                "completion": 0,
                "available": False,
            }
        return {
            "model": counts_model,
            "prompt": counts.get("prompt", 0),
            "completion": counts.get("completion", 0),
            "available": True,
        }

    def cost_since(self, snapshot: dict, model: str) -> float:
        counts_model, counts, prices = self._resolve_model(model)
        if not counts or not prices:
            return FALLBACK_COST_PER_CALL_USD

        if not snapshot.get("available"):
            delta_prompt = counts.get("prompt", 0)
            delta_completion = counts.get("completion", 0)
            if delta_prompt <= 0 and delta_completion <= 0:
                return 0.0
            cost = (
                delta_prompt * prices.get("prompt", 0)
                + delta_completion * prices.get("completion", 0)
            )
            return max(cost, FALLBACK_COST_PER_CALL_USD * 0.01)

        snapshot_model = snapshot.get("model", counts_model)
        if snapshot_model != counts_model:
            try:
                from ai_scientist.utils.token_tracker import token_tracker

                snapshot_counts = token_tracker.token_counts.get(snapshot_model)
                if snapshot_counts:
                    counts = snapshot_counts
            except Exception:
                pass

        delta_prompt = counts.get("prompt", 0) - snapshot.get("prompt", 0)
        delta_completion = counts.get("completion", 0) - snapshot.get(
            "completion", 0
        )
        if delta_prompt <= 0 and delta_completion <= 0:
            return 0.0

        cost = (
            delta_prompt * prices.get("prompt", 0)
            + delta_completion * prices.get("completion", 0)
        )
        return max(cost, FALLBACK_COST_PER_CALL_USD * 0.01)

    def read_delta_cost(self, model: str) -> float:
        counts_model, counts, prices = self._resolve_model(model)
        if not counts:
            return FALLBACK_COST_PER_CALL_USD

        prev_dict = self._get_prev()
        prev = prev_dict.get(counts_model, {"prompt": 0, "completion": 0})
        current_prompt = counts.get("prompt", 0)
        current_completion = counts.get("completion", 0)
        delta_prompt = current_prompt - prev["prompt"]
        delta_completion = current_completion - prev["completion"]
        prev_dict[counts_model] = {
            "prompt": current_prompt,
            "completion": current_completion,
        }

        if not prices:
            return FALLBACK_COST_PER_CALL_USD

        cost = (
            delta_prompt * prices.get("prompt", 0)
            + delta_completion * prices.get("completion", 0)
        )
        return max(cost, FALLBACK_COST_PER_CALL_USD * 0.01)


_delta_reader = _TokenTrackerDeltaReader()


def apply():
    """Monkey-patch `backend.query()` so agent-side LLM calls charge the current budget."""

    global _original_query
    with _apply_lock:
        if _original_query is not None:
            return

        try:
            from ai_scientist.treesearch import backend as backend_module
        except Exception as exc:
            logger.debug(f"无法导入 ai_scientist.treesearch.backend: {exc}")
            return

        _original_query = backend_module.query

        def budget_aware_query(
            system_message=None,
            user_message=None,
            model="qwen3.6-plus",
            temperature=None,
            max_tokens=None,
            func_spec=None,
            **model_kwargs,
        ):
            budget = _budget_ctx.get()
            if budget is not None and not budget.can_afford():
                raise BudgetExhaustedException(
                    f"预算已耗尽 (剩余 ${budget.remaining_usd:.4f})"
                )

            result = _original_query(
                system_message=system_message,
                user_message=user_message,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                func_spec=func_spec,
                **model_kwargs,
            )

            if budget is not None:
                cost = _delta_reader.read_delta_cost(model)
                budget.deduct(cost, raise_on_empty=True)
            return result

        backend_module.query = budget_aware_query
        logger.info("TokenBudget monkey-patch 已应用。")


def remove():
    """Restore the original `backend.query()` implementation."""

    global _original_query
    with _apply_lock:
        if _original_query is None:
            return
        try:
            from ai_scientist.treesearch import backend as backend_module

            backend_module.query = _original_query
        except Exception:
            pass
        _original_query = None


def snapshot_token_counts(model: str = "qwen3.6-plus") -> dict:
    return _delta_reader.take_snapshot(model)


def deduct_against(
    budget: TokenBudget,
    cost_usd: Optional[float] = None,
    model: str = "qwen3.6-plus",
):
    if budget is None:
        return
    if cost_usd is None:
        cost_usd = _delta_reader.read_delta_cost(model)
    budget.deduct(cost_usd, raise_on_empty=True)


def deduct_against_since(
    budget: TokenBudget,
    snapshot: dict,
    model: str = "qwen3.6-plus",
):
    if budget is None:
        return
    cost_usd = _delta_reader.cost_since(snapshot, model)
    if cost_usd <= 0:
        return
    budget.deduct(cost_usd, raise_on_empty=True)


def deduct_manual(cost_usd: Optional[float] = None, model: str = "qwen3.6-plus"):
    """Charge the budget stored in the current context."""

    budget = _budget_ctx.get()
    if budget is None:
        return
    if cost_usd is None:
        cost_usd = _delta_reader.read_delta_cost(model)
    budget.deduct(cost_usd, raise_on_empty=True)
