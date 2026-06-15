import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL


def generate_report(info: dict, scores: dict, signals: dict) -> str:
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

    prompt = f"""
あなたは個人投資家向けの株式分析アシスタントです。
以下のデータをもとに、中長期の配当投資の観点から参考情報をまとめてください。

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
上記データをもとに以下の3点を日本語で簡潔にまとめてください。
1. この銘柄の強み・魅力
2. 注意すべきリスク
3. 中長期保有の観点からの総合所見（買い検討・様子見・非推奨のいずれか）

※ これは個人の投資判断を補助する参考情報であり、投資助言ではありません。
※ 簡潔に、合計300〜400字程度でまとめてください。
""".strip()

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
