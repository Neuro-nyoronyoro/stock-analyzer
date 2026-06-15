import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_STYLE_MAP = {
    "dividend": "高配当・安定配当を重視したインカムゲイン投資",
    "growth":   "売上・利益成長を重視した成長投資（キャピタルゲイン重視）",
    "value":    "PER・PBRが低い割安銘柄を狙ったバリュー投資",
    "balanced": "配当・成長・割安をバランスよく評価した中長期投資",
    "custom":   "独自の重み付けによる投資",
}
_RISK_MAP    = {"low": "低リスク志向（安定重視）", "medium": "中程度のリスク許容", "high": "高リスク許容（積極的）"}
_HORIZON_MAP = {"short": "短期（1年未満）", "medium": "中期（1〜5年）", "long": "長期（5年以上）"}


def generate_report(info: dict, scores: dict, signals: dict, user_profile: dict = None) -> str:
    """銘柄の分析データをもとにAI投資参考レポートを生成する"""
    if not ANTHROPIC_API_KEY:
        return "※ ANTHROPIC_API_KEY が未設定です。.env ファイルを確認してください。"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    dy    = f"{scores['dividend_yield']:.2f}%" if scores.get("dividend_yield") else "不明"
    per   = f"{scores['per']:.1f}倍" if scores.get("per") else "不明"
    roe   = f"{scores['roe']:.1f}%" if scores.get("roe") else "不明"
    price = info.get("price", "不明")

    signal_lines = "\n".join(
        f"- {k}: {v[0]}（{v[1]}）" for k, v in signals.items()
    ) or "シグナルデータなし"

    if user_profile and user_profile.get("is_set"):
        style_text   = _STYLE_MAP.get(user_profile["investment_style"], "中長期投資")
        risk_text    = _RISK_MAP.get(user_profile["risk_tolerance"], "中程度のリスク許容")
        horizon_text = _HORIZON_MAP.get(user_profile["time_horizon"], "長期（5年以上）")
        profile_text = f"{style_text} / {risk_text} / 投資期間: {horizon_text}"
        if user_profile.get("investment_memo"):
            profile_text += f"\n補足: {user_profile['investment_memo']}"
    else:
        profile_text = "中長期・配当重視・低〜中リスク / 投資期間: 長期（5年以上）"

    prompt = f"""
あなたは個人投資家向けの株式分析アシスタントです。
以下のデータをもとに、投資家プロフィールの観点から参考情報をまとめてください。

【投資家プロフィール】
{profile_text}

【銘柄情報】
- 銘柄名: {info.get('name', '不明')}（{info.get('ticker', '')}）
- セクター: {info.get('sector', '不明')}
- 現在株価: {price}
- 配当利回り: {dy}
- PER: {per}
- ROE: {roe}

【総合スコア（100点満点）】
- 総合: {scores.get('total_score', '-')}点
- 配当スコア: {scores.get('dividend_score', '-')}点
- 財務スコア: {scores.get('financial_score', '-')}点
- 成長スコア: {scores.get('growth_score', '-')}点
- 割安スコア: {scores.get('value_score', '-')}点

【テクニカルシグナル】
{signal_lines}

【分析依頼】
上記の投資家プロフィールの観点から以下の3点を日本語で簡潔にまとめてください。
1. この銘柄の強み・魅力（投資家プロフィールとの相性を含む）
2. 注意すべきリスク
3. 当該投資家プロフィールにおける総合所見（買い検討・様子見・非推奨のいずれか）

※ これは個人の投資判断を補助する参考情報であり、投資助言ではありません。
※ 簡潔に、合計300〜400字程度でまとめてください。
""".strip()

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
