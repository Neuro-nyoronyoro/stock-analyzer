import os
from dotenv import load_dotenv

# .envのパスをconfig.pyと同じディレクトリに固定する
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
JQUANTS_REFRESH_TOKEN = os.getenv("JQUANTS_REFRESH_TOKEN", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# スコアリングの重み（合計1.0）
SCORE_WEIGHTS = {
    "dividend": 0.30,   # 配当
    "financial": 0.35,  # 財務健全性
    "growth":    0.20,  # 成長性
    "value":     0.15,  # 割安度
}

# スクリーニングのデフォルト条件
DEFAULT_SCREEN = {
    "min_dividend_yield": 0.0,   # 配当利回り下限（%）
    "max_per": 35.0,             # PER上限
    "min_roe": 5.0,              # ROE下限（%）
    "min_score": 40.0,           # 総合スコア下限
}

CLAUDE_MODEL = "claude-sonnet-4-6"

SES_SENDER_EMAIL = os.getenv("SES_SENDER_EMAIL", "")
APP_URL = os.getenv("APP_URL", "http://app.kimura-stock.com:8501")
