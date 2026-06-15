import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
import anthropic

from core.fetcher import get_stock_info, get_price_history
from core.scorer import calc_total_score
from core.auth_check import require_login
from db.database import get_user_profile
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

st.set_page_config(page_title="銘柄比較", page_icon="⚖️", layout="wide")

user = require_login()
user_profile = get_user_profile(user["id"])

st.title("⚖️ 銘柄比較")
st.caption("複数の銘柄を指標・チャートで横断比較し、AIが総合分析します")

_STYLE_MAP = {
    "dividend": "高配当・安定配当を重視したインカムゲイン投資",
    "growth":   "売上・利益成長を重視した成長投資（キャピタルゲイン重視）",
    "value":    "PER・PBRが低い割安銘柄を狙ったバリュー投資",
    "balanced": "配当・成長・割安をバランスよく評価した中長期投資",
    "custom":   "独自の重み付けによる投資",
}
_RISK_MAP    = {"low": "低リスク志向（安定重視）", "medium": "中程度のリスク許容", "high": "高リスク許容（積極的）"}
_HORIZON_MAP = {"short": "短期（1年未満）", "medium": "中期（1〜5年）", "long": "長期（5年以上）"}

# ── ティッカー入力 ──────────────────────────────────────────────
st.subheader("比較する銘柄を入力（2〜5銘柄）")
st.caption("日本株は「9432.T」、米国株は「AAPL」のように入力してください")

cols = st.columns(5)
placeholders = ["9432.T", "7203.T", "AAPL", "MSFT", "GOOG"]
tickers_input = []
for i, col in enumerate(cols):
    with col:
        val = st.text_input(f"銘柄{i+1}", placeholder=placeholders[i], key=f"cmp_t{i}")
        if val.strip():
            tickers_input.append(val.strip().upper())

period = st.sidebar.selectbox("チャート期間", ["1mo", "3mo", "6mo", "1y", "2y", "5y"], index=3)

if len(tickers_input) < 2:
    st.info("2銘柄以上入力すると比較できます。")
    st.stop()

run = st.button("⚖️ 比較する", type="primary", use_container_width=False)

# 同じティッカーセットでキャッシュを再利用
_cache_key = f"compare_data_{'_'.join(sorted(tickers_input))}_{period}"

if not run and _cache_key not in st.session_state:
    st.stop()

if run or _cache_key not in st.session_state:
    with st.spinner("データ取得中..."):
        def _fetch(ticker: str):
            info   = get_stock_info(ticker)
            scores = calc_total_score(info, weights=user_profile["weights"])
            hist   = get_price_history(ticker, period)
            return ticker, info, scores, hist

        results: dict = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(_fetch, t): t for t in tickers_input}
            for future in as_completed(futures):
                ticker, info, scores, hist = future.result()
                if "error" not in info:
                    results[ticker] = {"info": info, "scores": scores, "hist": hist}
                else:
                    st.warning(f"⚠️ {ticker}: データ取得失敗（{info.get('error', '不明')}）")

    st.session_state[_cache_key] = results

data: dict = st.session_state[_cache_key]
valid_tickers = [t for t in tickers_input if t in data]

if len(valid_tickers) < 2:
    st.error("有効なデータが2銘柄以上取得できませんでした。ティッカーを確認してください。")
    st.stop()

# ── 指標比較テーブル ────────────────────────────────────────────
st.subheader("📊 指標比較")

def _fmt(v, fmt_str: str, default: str = "—") -> str:
    try:
        return fmt_str.format(v) if v is not None else default
    except Exception:
        return default

METRIC_ROWS = [
    ("銘柄名",      lambda info, sc: info.get("name", "—")),
    ("市場",        lambda info, sc: "🇯🇵 日本" if info.get("ticker", "").endswith(".T") else "🇺🇸 米国"),
    ("セクター",    lambda info, sc: info.get("sector") or "—"),
    ("株価",        lambda info, sc: _fmt(info.get("price"), f"{{:,.0f}} {info.get('currency', '')}")),
    ("配当利回り",  lambda info, sc: _fmt(sc.get("dividend_yield"), "{:.2f}%")),
    ("PER",         lambda info, sc: _fmt(sc.get("per"),              "{:.1f}倍")),
    ("PBR",         lambda info, sc: _fmt(info.get("pbr"),            "{:.2f}倍")),
    ("ROE",         lambda info, sc: _fmt(sc.get("roe"),              "{:.1f}%")),
    ("負債比率",    lambda info, sc: _fmt(info.get("debt_to_equity"), "{:.1f}")),
    ("売上成長率",  lambda info, sc: _fmt(info.get("revenue_growth"), "{:+.1f}%")),
    ("利益成長率",  lambda info, sc: _fmt(info.get("earnings_growth"),"{:+.1f}%")),
    ("─── スコア ───", None),
    ("配当スコア",  lambda info, sc: sc.get("dividend_score",  "—")),
    ("財務スコア",  lambda info, sc: sc.get("financial_score", "—")),
    ("成長スコア",  lambda info, sc: sc.get("growth_score",    "—")),
    ("割安スコア",  lambda info, sc: sc.get("value_score",     "—")),
    ("総合スコア",  lambda info, sc: sc.get("total_score",     "—")),
]

table: dict = {}
for label, fn in METRIC_ROWS:
    if fn is None:
        table[label] = {t: "" for t in valid_tickers}
        continue
    row = {}
    for t in valid_tickers:
        row[t] = fn(data[t]["info"], data[t]["scores"])
    table[label] = row

header = {t: f"{data[t]['info'].get('name', t)}\n({t})" for t in valid_tickers}
df_table = pd.DataFrame(table).T.rename(columns=header)
df_table.index.name = "指標"
st.dataframe(df_table, use_container_width=True, height=580)

# ── 正規化チャート ──────────────────────────────────────────────
st.subheader("📈 相対パフォーマンス比較（基準日 = 100）")
st.caption("期間開始日の株価を100として正規化し、各銘柄の相対的な値動きを比較します")

COLORS = ["#f39c12", "#3498db", "#2ecc71", "#e74c3c", "#9b59b6"]
fig = go.Figure()
has_trace = False

for i, ticker in enumerate(valid_tickers):
    hist = data[ticker]["hist"]
    if hist.empty or "Close" not in hist.columns:
        continue
    base = hist["Close"].iloc[0]
    if not base or base == 0:
        continue
    normalized = hist["Close"] / base * 100
    name = data[ticker]["info"].get("name", ticker)
    fig.add_trace(go.Scatter(
        x=hist.index,
        y=normalized,
        name=f"{name}（{ticker}）",
        line=dict(color=COLORS[i % len(COLORS)], width=2),
        hovertemplate="%{y:.1f}<extra>" + ticker + "</extra>",
    ))
    has_trace = True

if has_trace:
    fig.add_hline(y=100, line_dash="dot", line_color="#555", line_width=1)
    fig.update_layout(
        template="plotly_dark",
        height=420,
        yaxis_title="相対パフォーマンス（基準=100）",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hovermode="x unified",
        margin=dict(t=60),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("チャートデータを取得できませんでした。")

# ── AIレポート ──────────────────────────────────────────────────
st.divider()
st.subheader("🤖 AI比較分析レポート")
st.caption("※ このレポートは参考情報です。投資判断は必ずご自身でご確認ください。")

if st.button("比較AIレポートを生成", type="primary"):
    if not ANTHROPIC_API_KEY:
        st.error("ANTHROPIC_API_KEY が未設定です。.env ファイルを確認してください。")
        st.stop()

    lines = []
    for ticker in valid_tickers:
        info = data[ticker]["info"]
        sc   = data[ticker]["scores"]
        lines.append(f"""
【{info.get('name', ticker)}（{ticker}）】
  株価: {_fmt(info.get('price'), '{:,.0f}')} {info.get('currency', '')}
  配当利回り: {_fmt(sc.get('dividend_yield'), '{:.2f}%')}  PER: {_fmt(sc.get('per'), '{:.1f}倍')}
  PBR: {_fmt(info.get('pbr'), '{:.2f}倍')}  ROE: {_fmt(sc.get('roe'), '{:.1f}%')}
  負債比率: {_fmt(info.get('debt_to_equity'), '{:.1f}')}
  売上成長率: {_fmt(info.get('revenue_growth'), '{:+.1f}%')}  利益成長率: {_fmt(info.get('earnings_growth'), '{:+.1f}%')}
  スコア 総合:{sc.get('total_score', '—')} 配当:{sc.get('dividend_score', '—')} 財務:{sc.get('financial_score', '—')} 成長:{sc.get('growth_score', '—')} 割安:{sc.get('value_score', '—')}
""".strip())

    profile_text = _STYLE_MAP.get(user_profile.get("investment_style", "balanced"), "中長期投資")
    risk_text    = _RISK_MAP.get(user_profile.get("risk_tolerance", "medium"), "中程度のリスク許容")
    horizon_text = _HORIZON_MAP.get(user_profile.get("time_horizon", "medium"), "中期（1〜5年）")

    prompt = f"""あなたは個人投資家向けの株式分析アシスタントです。
以下の複数銘柄データをもとに、比較分析レポートを日本語で作成してください。

【投資家プロフィール】
投資スタイル: {profile_text}
リスク許容度: {risk_text}
投資期間: {horizon_text}
{('補足: ' + user_profile['investment_memo']) if user_profile.get('investment_memo') else ''}

【比較銘柄データ】
{"=" * 40}
{chr(10).join(lines)}
{"=" * 40}

以下の構成で分析してください：

1. **各銘柄の特徴まとめ**
   各銘柄について「強み」「弱み」を各2〜3行で簡潔にまとめる

2. **指標別の横断比較**
   バリュエーション（PER・PBR）、収益性（ROE）、配当、成長性の観点から銘柄間の違いを説明する

3. **投資家プロフィールに最も合う銘柄の推薦**
   上記の投資スタイル・リスク許容度・投資期間を踏まえ、どの銘柄が最も適しているか、理由とともに述べる

4. **注意点・リスク**
   各銘柄または比較全体で気をつけるべき点

※ これは参考情報であり投資助言ではありません。最終的な投資判断はご自身でお願いしますと末尾に明記してください。"""

    with st.spinner("Claudeが分析中..."):
        try:
            client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            st.markdown(message.content[0].text)
        except Exception as e:
            st.error(f"AIレポートの生成に失敗しました: {e}")
