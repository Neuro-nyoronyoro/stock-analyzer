import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def build_context(holdings_data: list, watchlist_data: list, market_data: dict) -> str:
    """ポートフォリオ・市場情報をAIへのコンテキスト文字列に変換する"""
    lines = []

    if holdings_data:
        lines.append("【保有銘柄】")
        for h in holdings_data:
            gain_str = ""
            if h.get("gain") is not None:
                gain_str = f", 損益 {h['gain']:+,.0f}円（{h['pct']:+.2f}%）"
            lines.append(
                f"- {h['name']}（{h['ticker']}）: {h['shares']}株"
                f", 取得単価 {h['avg_cost']:,.0f}円"
                f", 現在価格 {h['price']}"
                f", 評価額 {h['value']}"
                + gain_str
            )
    else:
        lines.append("【保有銘柄】なし")

    if watchlist_data:
        lines.append("\n【ウォッチリスト】")
        for w in watchlist_data:
            price_str = f": {w['price']}" if w.get("price") else ""
            lines.append(f"- {w['name']}（{w['ticker']}）{price_str}")
    else:
        lines.append("\n【ウォッチリスト】なし")

    if market_data:
        lines.append("\n【市場概況（直近）】")
        for name, data in market_data.items():
            if data:
                lines.append(f"- {name}: {data['price']:,.2f}（前日比 {data['pct']:+.2f}%）")

    return "\n".join(lines)


_STYLE_MAP   = {
    "dividend": "高配当・安定配当重視（インカムゲイン）",
    "growth":   "成長重視（キャピタルゲイン）",
    "value":    "割安銘柄重視（バリュー投資）",
    "balanced": "バランス型（配当・成長・割安を均等重視）",
    "custom":   "カスタム設定",
}
_RISK_MAP    = {"low": "低リスク志向（安定重視）", "medium": "中程度のリスク許容", "high": "高リスク許容（積極的）"}
_HORIZON_MAP = {"short": "短期（1年未満）", "medium": "中期（1〜5年）", "long": "長期（5年以上）"}


def chat_response(messages: list, context: str, user_profile: dict = None) -> str:
    """会話履歴とポートフォリオ情報をもとにAI応答を生成する"""
    if not ANTHROPIC_API_KEY:
        return "※ ANTHROPIC_API_KEY が未設定です。.env ファイルを確認してください。"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    if user_profile and user_profile.get("is_set"):
        style   = _STYLE_MAP.get(user_profile["investment_style"], "バランス型")
        risk    = _RISK_MAP.get(user_profile["risk_tolerance"], "中程度のリスク許容")
        horizon = _HORIZON_MAP.get(user_profile["time_horizon"], "長期（5年以上）")
        profile_str = f"投資スタイル: {style} / {risk} / 投資期間: {horizon}"
        if user_profile.get("investment_memo"):
            profile_str += f"\n本人コメント: {user_profile['investment_memo']}"
    else:
        profile_str = "投資スタイル: 中長期・配当重視 / 低〜中リスク / 投資期間: 長期（5年以上）"

    system_prompt = f"""あなたは個人投資家専用のAI投資アドバイザーです。

【ユーザーの投資プロフィール】
{profile_str}

【現在の投資状況（リアルタイムデータ）】
{context}

回答の方針:
- ユーザーの投資プロフィールに合わせた視点でアドバイスする
- 上記のデータを積極的に参照し、具体的な数値に基づいて分析する
- 投資は自己責任であることを前提に、参考情報として提供する
- 日本語で答える
- リスクがある場合は必ず指摘する
- 「投資助言ではない」という注釈は不要（ユーザーは理解済み）

【文字数・構成ルール】
- 回答全体は700文字以内に収めること
- 長くなる場合は箇条書きや見出しで簡潔に構造化し、必ず最後まで書き切ること
- 途中で終わることは絶対に避けること"""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text
