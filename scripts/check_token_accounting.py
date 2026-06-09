#!/usr/bin/env python
import json
import os
from copy import deepcopy

from ai_system.env_setup import setup_openai_env
from ai_scientist.llm import create_client, make_llm_call
from ai_scientist.utils.token_tracker import token_tracker
from ai_system.token_budget import snapshot_token_counts, _delta_reader


def _safe_getattr(obj, path, default=None):
    cur = obj
    for part in path.split("."):
        if cur is None:
            return default
        if isinstance(cur, dict):
            cur = cur.get(part, default)
        else:
            cur = getattr(cur, part, default)
    return cur


def _usage_summary(resp):
    return {
        "model": getattr(resp, "model", None),
        "created": getattr(resp, "created", None),
        "prompt_tokens": _safe_getattr(resp, "usage.prompt_tokens"),
        "completion_tokens": _safe_getattr(resp, "usage.completion_tokens"),
        "total_tokens": _safe_getattr(resp, "usage.total_tokens"),
        "reasoning_tokens": _safe_getattr(
            resp, "usage.completion_tokens_details.reasoning_tokens"
        ),
        "cached_tokens": _safe_getattr(resp, "usage.prompt_tokens_details.cached_tokens"),
        "usage_obj_type": type(getattr(resp, "usage", None)).__name__,
        "has_usage": hasattr(resp, "usage"),
        "has_completion_tokens_details": _safe_getattr(
            resp, "usage.completion_tokens_details", "__MISSING__"
        )
        != "__MISSING__",
    }


def main():
    setup_openai_env()
    model = os.environ.get("MODEL", "qwen3.6-plus")
    prompt = os.environ.get(
        "PROMPT",
        "Reply with exactly this JSON and nothing else: {\"ok\": true, \"n\": 1}",
    )
    system_message = os.environ.get(
        "SYSTEM_MESSAGE", "You are a precise assistant. Output only the requested JSON."
    )

    client, client_model = create_client(model)
    messages = [{"role": "user", "content": prompt}]

    print("=== Probe Config ===")
    print(json.dumps({"requested_model": model, "resolved_model": client_model}, indent=2))

    print("\n=== Raw Client Call ===")
    raw_resp = client.chat.completions.create(
        model=client_model,
        messages=[
            {"role": "system", "content": system_message},
            *messages,
        ],
        temperature=0.0,
        max_tokens=128,
        n=1,
    )
    print(json.dumps(_usage_summary(raw_resp), indent=2, ensure_ascii=False))
    print("raw_content_preview:", repr(raw_resp.choices[0].message.content[:200]))

    print("\n=== Tracked Call ===")
    token_tracker.reset()
    before_snapshot = snapshot_token_counts(client_model)
    before_counts = deepcopy(token_tracker.get_summary())

    tracked_resp = make_llm_call(
        client=client,
        model=client_model,
        temperature=0.0,
        system_message=system_message,
        prompt=messages,
    )

    after_snapshot = snapshot_token_counts(client_model)
    after_counts = deepcopy(token_tracker.get_summary())
    delta_cost = _delta_reader.cost_since(before_snapshot, client_model)

    print(json.dumps(_usage_summary(tracked_resp), indent=2, ensure_ascii=False))
    print("tracked_content_preview:", repr(tracked_resp.choices[0].message.content[:200]))
    print("\ntracker_before:", json.dumps(before_counts, indent=2, ensure_ascii=False))
    print("tracker_after:", json.dumps(after_counts, indent=2, ensure_ascii=False))
    print("snapshot_before:", json.dumps(before_snapshot, indent=2, ensure_ascii=False))
    print("snapshot_after:", json.dumps(after_snapshot, indent=2, ensure_ascii=False))
    print("delta_cost_from_snapshot:", delta_cost)

    if client_model not in token_tracker.MODEL_PRICES:
        print(
            "\nWARNING: model not present in token_tracker.MODEL_PRICES; "
            "budget system will fall back to fixed per-call charging."
        )


if __name__ == "__main__":
    main()
