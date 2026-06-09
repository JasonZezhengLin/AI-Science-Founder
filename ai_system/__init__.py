"""
AI Scientist Founder Ecosystem.

将独立的 AI Scientist 改装为多主体科研生态中的 Founder 角色。
当前版本包含消息驱动时钟、批次 Investor、同行评审社会、挂起/恢复、
内部文献库，以及与 AI Scientist 主体的实验/写作适配层。
"""

from ai_system.config import (
    DEFAULT_INITIAL_TOKEN_USD,
    DEFAULT_SKILL_TEXT,
    INVESTOR_APPROVAL_TOKEN_USD,
    INVESTOR_EXTRA_TOKEN_USD,
    INVESTOR_DIRECTION,
)
from ai_system.env_setup import setup_openai_env
from ai_system.token_budget import (
    TokenBudget,
    BudgetExhaustedException,
    apply,
    remove,
    deduct_manual,
    deduct_against,
    deduct_against_since,
    snapshot_token_counts,
    set_budget,
    clear_budget,
)
from ai_system.skill_manager import SkillManager
from ai_system.reputation import FounderProfile
from ai_system.investor import (
    YesManInvestor,
    FundingDecision,
    LLMInvestor,
    RuleBasedInvestor,
    FundRoleInvestor,
)
from ai_system.literature_db import LiteratureDB, get_literature_db
from ai_system.peer_review import FounderReviewSociety, PlaceholderPeerReview, ReviewResult
from ai_system.proposal_builder import build_proposal, build_proposal_debug, Proposal
from ai_system.founder_shell import FounderShell, FounderStatus
from ai_system.resource_scheduler import ResourceScheduler
from ai_system.suspension import ExperimentCheckpoint, ResumeToken
