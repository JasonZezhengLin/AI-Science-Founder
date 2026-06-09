"""
Skill 文本管理器。

- 存储：JSON 文件，key 为 founder_id
- 更新：LLM 调用，吸收各类反馈
- 注入：由 FounderShell 在调用 agent 前注入到系统提示词
"""

import json
import os
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class SkillManager:
    """管理单个 Founder 的 skill 文本。"""

    def __init__(self, founder_id: str, store_dir: str = "ai_system/skill_store", recorder=None):
        self.founder_id = founder_id
        self.store_dir = store_dir
        self.recorder = recorder
        os.makedirs(store_dir, exist_ok=True)
        self._file = os.path.join(store_dir, f"{founder_id}.json")

    def load(self) -> str:
        """加载当前 skill，如不存在则返回默认模板。"""
        from ai_system.config import DEFAULT_SKILL_TEXT

        if os.path.exists(self._file):
            with open(self._file, "r") as f:
                data = json.load(f)
                return data.get("skill", DEFAULT_SKILL_TEXT)
        return DEFAULT_SKILL_TEXT

    def save(self, skill_text: str):
        """保存 skill 文本到文件。"""
        history = []
        if os.path.exists(self._file):
            try:
                with open(self._file, "r") as f:
                    existing = json.load(f)
                    history = existing.get("history", [])
            except Exception:
                history = []
        with open(self._file, "w") as f:
            json.dump(
                {
                    "founder_id": self.founder_id,
                    "skill": skill_text,
                    "history": history,
                },
                f,
                indent=2,
            )
        logger.info(f"Skill 已保存: {self.founder_id}")

    def _append_history(
        self,
        old_skill: str,
        new_skill: str,
        event_description: str,
        feedback_text: str,
    ):
        history = []
        if os.path.exists(self._file):
            try:
                with open(self._file, "r") as f:
                    existing = json.load(f)
                    history = existing.get("history", [])
            except Exception:
                history = []
        history.append(
            {
                "timestamp": datetime.now().isoformat(),
                "event_description": event_description,
                "old_skill": old_skill,
                "new_skill": new_skill,
                "feedback_excerpt": feedback_text[:500],
            }
        )
        with open(self._file, "w") as f:
            json.dump(
                {
                    "founder_id": self.founder_id,
                    "skill": new_skill,
                    "history": history,
                },
                f,
                indent=2,
            )

    def update_from_feedback(
        self,
        current_skill: str,
        event_description: str,
        feedback_text: str,
        model: str = "qwen3.6-plus",
    ):
        """
        LLM 驱动的 skill 更新。

        Args:
            current_skill: 当前的 skill 文本
            event_description: 事件描述（如"你的论文被接收"）
            feedback_text: 反馈原文（审稿意见/Investor 评语等）
            model: 用于更新的 LLM 模型

        Returns:
            `(new_skill_text, success_bool)`.
        """
        if "mock" in model.lower():
            new_skill = current_skill + f"\n[mock-update: {event_description}]"
            self._append_history(current_skill, new_skill, event_description, feedback_text)
            logger.info(f"Skill 已 mock 更新: {self.founder_id}")
            return new_skill, True

        from ai_scientist.llm import create_client, get_response_from_llm

        prompt = f"""Based on the following feedback, update the researcher's skill profile.
Extract actionable lessons. Adjust methodological preferences.
Preserve existing valuable insights unless contradicted by new evidence.
Keep the skill concise (under 500 words).

Current Skill:
{current_skill}

Event: {event_description}

Feedback Received:
{feedback_text}

Please output ONLY the updated skill text. Do not include any other commentary."""

        try:
            client, client_model = create_client(model)
            response, _ = get_response_from_llm(
                prompt=prompt,
                client=client,
                model=client_model,
                system_message="You are a researcher updating your own skill notes.",
                msg_history=[],
            )
            new_skill = response.strip()
            if not new_skill:
                logger.warning(f"Skill 更新返回空文本: {self.founder_id}")
                return current_skill, False
            self._append_history(current_skill, new_skill, event_description, feedback_text)
            if self.recorder is not None:
                self.recorder.log_llm(
                    self.founder_id,
                    "skill_update",
                    {
                        "event_description": event_description,
                        "feedback_text": feedback_text,
                        "prompt": prompt,
                        "response_text": response,
                        "old_skill": current_skill,
                        "new_skill": new_skill,
                        "success": True,
                    },
                )
            logger.info(f"Skill 已更新: {self.founder_id}")
            return new_skill, True
        except Exception as e:
            if self.recorder is not None:
                self.recorder.log_llm(
                    self.founder_id,
                    "skill_update",
                    {
                        "event_description": event_description,
                        "feedback_text": feedback_text,
                        "prompt": prompt,
                        "error": str(e),
                        "old_skill": current_skill,
                        "success": False,
                    },
                )
            logger.error(f"Skill 更新失败: {e}")
            return current_skill, False

    def initial_skill(self) -> str:
        """获取初始 skill（默认模板）。"""
        from ai_system.config import DEFAULT_SKILL_TEXT

        return DEFAULT_SKILL_TEXT
