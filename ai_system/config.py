"""
全局配置常量。Debug 版本使用简化参数。
"""

# --- Founder ---
DEFAULT_INITIAL_TOKEN_USD = 1.0  # 新 Founder 初始美元额度
DEFAULT_SKILL_TEXT = (
    "You are a rigorous researcher who values empirical validation. "
    "You prefer well-motivated hypotheses with clear experimental designs. "
    "You aim to contribute novel insights while ensuring reproducibility. "
    "You have not yet developed a specialized methodological preference."
)

# --- Investor (YesMan) ---
INVESTOR_TOTAL_BUDGET_USD = 100.0  # 单个 Investor 的总预算池
INVESTOR_APPROVAL_TOKEN_USD = 10.0  # 每次都批这么多
INVESTOR_EXTRA_TOKEN_USD = 15.0  # 追加经费额度
INVESTOR_DIRECTION = "General machine learning research, open to all subfields."

# --- Budget ---
# 使用 token_tracker 的 MODEL_PRICES 做美元成本换算
GLOBAL_BUDGET_CAP_USD = 100.0  # 系统总美元消耗上限

# --- Peer Review ---
REVIEWERS_PER_PAPER = 3
ACCEPTANCE_THRESHOLD = 6.0  # 1-10 分制，YesMan 版不实际使用

# --- Paths ---
SKILL_STORE_DIR = "ai_system/skill_store"
PROFILE_STORE_DIR = "ai_system/profile_store"
