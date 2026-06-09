"""
Peer review implementations for the founder ecosystem.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    accepted: bool
    overall_score: float
    reviews: List[dict] = field(default_factory=list)
    meta_review: str = ""


class PlaceholderPeerReview:
    def __init__(self, acceptance_rate: float = 0.7, seed: int = None):
        self.acceptance_rate = acceptance_rate
        self.rng = random.Random(seed)

    def evaluate(
        self,
        paper_title: str,
        paper_text: str,
        author_id: str,
        paper_pdf_path: Optional[str] = None,
    ) -> ReviewResult:
        accepted = self.rng.random() < self.acceptance_rate
        score = self.rng.uniform(5.0, 9.0) if accepted else self.rng.uniform(2.0, 5.5)
        reviews = [
            {
                "reviewer": "Reviewer_1",
                "score": round(score + self.rng.uniform(-1, 1), 1),
                "summary": "Template review.",
            },
            {
                "reviewer": "Reviewer_2",
                "score": round(score + self.rng.uniform(-1, 1), 1),
                "summary": "Template review.",
            },
            {
                "reviewer": "Reviewer_3",
                "score": round(score + self.rng.uniform(-1, 1), 1),
                "summary": "Template review.",
            },
        ]
        return ReviewResult(
            accepted=accepted,
            overall_score=round(score, 1),
            reviews=reviews,
            meta_review=(
                f"Overall, the reviewers {'recommend acceptance' if accepted else 'recommend rejection'}."
            ),
        )


class FounderReviewSociety:
    """
    Review papers with reviewers sampled from the founder pool.
    """

    def __init__(
        self,
        model: str = "qwen3.6-plus",
        review_count: int = 3,
        acceptance_threshold: float = 6.5,
        seed: Optional[int] = None,
        recorder=None,
    ):
        self.model = model
        self.review_count = review_count
        self.acceptance_threshold = acceptance_threshold
        self.rng = random.Random(seed)
        self.recorder = recorder
        self._founders = {}

    def register_founders(self, founders):
        self._founders = {shell.founder_id: shell for shell in founders}

    def _select_reviewers(self, author_id: str) -> List[str]:
        candidates = [fid for fid in self._founders.keys() if fid != author_id]
        if not candidates:
            # 审稿人不足（如单 founder 生态）：返回空，由 evaluate 走降级路径，
            # 不再抛异常导致 founder 破产。双盲评审需要至少 2 个 founder。
            return []
        if len(candidates) >= self.review_count:
            return self.rng.sample(candidates, self.review_count)
        return [self.rng.choice(candidates) for _ in range(self.review_count)]

    def _paper_content(self, paper_text: str, paper_pdf_path: Optional[str]) -> str:
        if paper_pdf_path:
            try:
                from ai_scientist.perform_llm_review import load_paper

                return load_paper(paper_pdf_path)
            except Exception as e:
                logger.warning(f"Failed to load PDF for review, fallback to text: {e}")
        return paper_text

    def _reviewer_system_prompt(self, reviewer_id: str, skill_text: str) -> str:
        from ai_scientist.perform_llm_review import reviewer_system_prompt_base

        return (
            reviewer_system_prompt_base
            + "\nYou are participating in a reviewer pool inside an AI research ecosystem."
            + f"\nReviewer identity: {reviewer_id}."
            + "\nYour methodological preferences are:"
            + f"\n{skill_text}\n"
            + "Use these preferences only to shape emphasis and criticism, not to reveal your identity."
        )

    def evaluate(
        self,
        paper_title: str,
        paper_text: str,
        author_id: str,
        paper_pdf_path: Optional[str] = None,
    ) -> ReviewResult:
        reviewer_ids = self._select_reviewers(author_id)
        if not reviewer_ids:
            # 审稿人不足，跳过评审（不接收、不破产）。让 founder 正常进入下一 cycle。
            logger.warning(
                f"[peer_review] 审稿人不足，跳过对 {author_id} 的评审"
                f"（双盲评审需要至少 2 个 founder）"
            )
            return ReviewResult(
                accepted=False,
                overall_score=0.0,
                reviews=[],
                meta_review="Review skipped: not enough eligible reviewers in the ecosystem.",
            )
        content = self._paper_content(paper_text, paper_pdf_path)
        reviews = []
        scores = []

        for idx, reviewer_id in enumerate(reviewer_ids, start=1):
            from ai_scientist.llm import create_client
            from ai_scientist.perform_llm_review import perform_review

            reviewer_shell = self._founders[reviewer_id]
            reviewer_skill = reviewer_shell.skill_manager.load()
            client, client_model = create_client(self.model)
            review = perform_review(
                content,
                client_model,
                client,
                num_reflections=1,
                num_fs_examples=0,
                num_reviews_ensemble=1,
                reviewer_system_prompt=self._reviewer_system_prompt(
                    reviewer_id, reviewer_skill
                ),
            )
            if review is None:
                review = {
                    "Overall": 1.0,
                    "Summary": "Reviewer returned no structured review output.",
                }
            overall = float(review.get("Overall", review.get("overall", 5)))
            summary = review.get("Summary", "") or review.get("summary", "")
            review_payload = {
                "reviewer": reviewer_id,
                "reviewer_slot": idx,
                "score": overall,
                "summary": summary,
                "raw_review": review,
            }
            reviews.append(review_payload)
            scores.append(overall)
            if self.recorder is not None:
                self.recorder.log_llm(
                    reviewer_id,
                    "peer_review_individual",
                    {
                        "paper_title": paper_title,
                        "author_id": author_id,
                        "paper_pdf_path": paper_pdf_path,
                        "review": review_payload,
                    },
                )

        avg_score = sum(scores) / max(len(scores), 1)
        accepted = avg_score >= self.acceptance_threshold
        meta_review = (
            f"Three-reviewer panel average score: {avg_score:.2f}/10. "
            f"The panel {'recommends acceptance' if accepted else 'recommends rejection'} "
            f"for '{paper_title}'."
        )
        result = ReviewResult(
            accepted=accepted,
            overall_score=round(avg_score, 2),
            reviews=reviews,
            meta_review=meta_review,
        )
        if self.recorder is not None:
            self.recorder.log_llm(
                author_id,
                "peer_review_meta",
                {
                    "paper_title": paper_title,
                    "author_id": author_id,
                    "paper_pdf_path": paper_pdf_path,
                    "reviewer_ids": reviewer_ids,
                    "result": {
                        "accepted": result.accepted,
                        "overall_score": result.overall_score,
                        "meta_review": result.meta_review,
                        "reviews": reviews,
                    },
                },
            )
        logger.info(
            f"[PeerReviewSociety] {paper_title[:80]} -> accepted={accepted} avg={avg_score:.2f}"
        )
        return result
