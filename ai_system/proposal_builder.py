"""
Proposal Builder — Shell 的 LLM 调用 ①。

将 Agent 产出的 idea.json 格式化为正式基金申请书，
并结合 Investor 方向描述选择最合适的 Investor。
"""

import json
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Proposal:
    proposal_text: str
    selected_investor_id: str
    selection_reason: str


def build_proposal(
    idea: dict,
    founder_id: str,
    founder_profile_summary: dict,
    investors: List[dict],
    model: str = "qwen3.6-plus",
    recorder=None,
    cycle_count: Optional[int] = None,
) -> Optional[Proposal]:
    """
    LLM 驱动的申请书构建 + Investor 选择。

    Args:
        idea: Agent 产出的 idea dict (Name, Title, Abstract, etc.)
        founder_id: Founder 标识
        founder_profile_summary: 档案摘要 (total_papers, accepted_papers, etc.)
        investors: Investor 列表，每项含 investor_id, direction
        model: LLM 模型

    Returns:
        Proposal 对象，或 None（LLM 调用失败时）
    """
    from ai_scientist.llm import create_client, get_response_from_llm

    investor_list_text = "\n\n".join(
        f"Investor ID: {inv['investor_id']}\n"
        f"研究方向偏好: {inv.get('direction', 'General ML')}"
        for inv in investors
    )

    idea_text = json.dumps(idea, indent=2, ensure_ascii=False)

    profile_text = json.dumps(founder_profile_summary, indent=2, ensure_ascii=False)

    prompt = f"""You are helping a researcher format a funding proposal and select the most suitable investor.

## Researcher Profile
{profile_text}

## Generated Research Idea
{idea_text}

## Available Investors
{investor_list_text}

## Task
1. Read the research idea carefully.
2. Compare the idea's research direction with each investor's stated preferences.
3. Select the SINGLE most suitable investor based on direction match.
4. Format the idea into a formal funding proposal (1-2 paragraphs) suitable for submission to that investor.
5. Output the result as a JSON object with the following fields:
   - "selected_investor_id": the chosen investor's ID
   - "selection_reason": brief reason for the selection (1-2 sentences)
   - "proposal_text": the formatted funding proposal

Output ONLY the JSON object. Do not include any other text."""

    try:
        client, client_model = create_client(model)
        response_text, _ = get_response_from_llm(
            prompt=prompt,
            client=client,
            model=client_model,
            system_message="You are a research funding strategist. Output only valid JSON.",
            msg_history=[],
        )

        # Extract JSON from response (handle markdown code blocks)
        text = response_text.strip()
        if text.startswith("```"):
            import re
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)

        result = json.loads(text)
        if recorder is not None:
            recorder.log_llm(
                founder_id,
                "proposal_builder",
                {
                    "cycle_count": cycle_count,
                    "prompt": prompt,
                    "system_message": "You are a research funding strategist. Output only valid JSON.",
                    "response_text": response_text,
                    "parsed_result": result,
                },
            )
        return Proposal(
            proposal_text=result["proposal_text"],
            selected_investor_id=result["selected_investor_id"],
            selection_reason=result["selection_reason"],
        )

    except Exception as e:
        if recorder is not None:
            recorder.log_llm(
                founder_id,
                "proposal_builder",
                {
                    "cycle_count": cycle_count,
                    "prompt": prompt,
                    "system_message": "You are a research funding strategist. Output only valid JSON.",
                    "error": str(e),
                },
            )
        logger.error(f"[{founder_id}] 提案构建失败: {e}")
        return None


def build_proposal_debug(
    idea: dict,
    founder_id: str,
    investors: List[dict],
    founder_profile_summary: dict = None,
    model: str = "qwen3.6-plus",
    recorder=None,
    cycle_count: Optional[int] = None,
) -> Proposal:
    """
    Debug 版：跳过 LLM 调用，直接选第一个 Investor 并格式化 idea。
    """
    if not investors:
        raise ValueError("No investors available")

    inv = investors[0]
    title = idea.get("Title", "Untitled")
    abstract = idea.get("Abstract", "No abstract provided.")
    hypothesis = idea.get("Short Hypothesis", "")

    proposal_text = (
        f"# Research Proposal: {title}\n\n"
        f"## Hypothesis\n{hypothesis}\n\n"
        f"## Abstract\n{abstract}\n\n"
        f"## Proposed Experiments\n{idea.get('Experiments', 'N/A')}\n\n"
        f"## Risks and Limitations\n{idea.get('Risk Factors and Limitations', 'N/A')}"
    )

    return Proposal(
        proposal_text=proposal_text,
        selected_investor_id=inv["investor_id"],
        selection_reason=f"Debug mode: auto-assigned to {inv['investor_id']}",
    )
