import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from core.fetcher import get_stock_info, get_price_history, get_dividend_history, search_tickers
from core.scorer import calc_total_score, score_label
from core.technical import add_indicators, get_signal
from core.ai_report import generate_report
from core.news import get_stock_news
from db.database import get_session, Watchlist
from datetime import datetime

st.set_page_config(page_title="銘柄詳細", page_icon="📊", layout="wide")

from core.auth_check import require_login
from db.database import get_user_profile
user = require_login()
user_profile = get_user_profile(user["id"])

st.title("📊 銘柄詳細")

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.85rem !important; }
</style>
""", unsafe_allow_html=True)

# 銘柄入力（ウォッチリストページからの遷移時は自動入力）
_prefill = st.session_state.pop("prefill_ticker", "")
if _prefill:
    st.session_state["ticker_input"] = _prefill
col1, col2 = st.columns([3, 1])
with col1:
    ticker_input = st.text_input(
        "ティッカーシンボルを入力（例: 7203.T / AAPL）",
        placeholder="7203.T または AAPL",
        key="ticker_input",
    )
with col2:
    keyword = st.text_input("銘柄名で検索", placeholder="トヨタ / Apple")

if keyword:
    found = search_tickers(keyword)
    if found:
        options = {f"{s['name']} ({s['ticker']})": s["ticker"] for s in found}
        selected = st.selectbox("検索結果", list(options.keys()))
        if selected:
            ticker_input = options[selected]

if not ticker_input:
    st.info("ティッカーシンボルを入力するか、銘柄名で検索してください。")
    st.stop()

ticker = ticker_input.strip().upper()

# データ取得
with st.spinner(f"{ticker} のデータを取得中..."):
    info    = get_stock_info(ticker)
    period  = st.sidebar.selectbox("チャート期間", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "最大"], index=3)
    df_hist = get_price_history(ticker, period)
    df_div  = get_dividend_history(ticker)
    scores  = calc_total_score(info, weights=user_profile["weights"])

if "error" in info:
    st.error(f"データ取得エラー: {info['error']}")
    st.stop()

# ヘッダー
name = info.get("name", ticker)
st.header(f"{name}（{ticker}）")

# データソース表示
_info_src = info.get("_source", "yfinance")
_src_label = {
    "jquants":      ("✅", "J-Quants"),
    "yahoo_direct": ("✅", "Yahoo Finance 直接API"),
    "yfinance":     ("⚠️", "yfinance（レート制限リスクあり）"),
}
_ic, _il = _src_label.get(_info_src, ("✅", _info_src))
_price_src = "J-Quants" if ticker.endswith(".T") else "Yahoo Finance 直接API"
st.caption(f"{_ic} 財務データ: **{_il}**　｜　✅ 株価チャート: **{_price_src}**")
if info.get("_partial"):
    st.warning("⚠️ yfinanceのレート制限中のため財務データ（PER・配当・ROE等）は取得できていません。スコアはキャッシュ値を表示しています。", icon="⚠️")

col1, col2, col3, col4, col5 = st.columns(5)
currency = info.get("currency", "")
with col1:
    st.metric("現在株価", f"{info.get('price', '-'):,} {currency}")
with col2:
    dy = scores.get("dividend_yield")
    st.metric("配当利回り", f"{dy:.2f}%" if dy else "—")
with col3:
    per = scores.get("per")
    st.metric("PER", f"{per:.1f}倍" if per else "—")
with col4:
    roe = scores.get("roe")
    st.metric("ROE", f"{roe:.1f}%" if roe else "—")
with col5:
    st.metric("総合スコア", f"{scores['total_score']}点 {score_label(scores['total_score'])}")

# ウォッチリスト追加
session = get_session()
exists = session.query(Watchlist).filter_by(ticker=ticker, user_id=user["id"]).first()
if not exists:
    if st.button("⭐ ウォッチリストに追加"):
        w = Watchlist(ticker=ticker, name=name, market=info.get("market", ""),
                      added_at=datetime.utcnow(), user_id=user["id"])
        session.add(w)
        session.commit()
        st.success("ウォッチリストに追加しました")
        st.rerun()
else:
    if st.button("⭐ ウォッチリストから削除"):
        session.delete(exists)
        session.commit()
        st.success("ウォッチリストから削除しました")
        st.rerun()
session.close()

st.divider()

# タブ構成
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 チャート", "📋 財務", "🤖 AIレポート", "📅 配当履歴", "📰 ニュース"])

with tab1:
    if df_hist.empty:
        st.warning("株価データを取得できませんでした。")
    else:
        df_tech = add_indicators(df_hist)
        signals = get_signal(df_tech)

        # シグナル表示
        if signals:
            sig_cols = st.columns(len(signals))
            for i, (k, (direction, desc)) in enumerate(signals.items()):
                icon = "🟢" if "買い" in direction else ("🔴" if "売り" in direction else "⚪")
                with sig_cols[i]:
                    st.markdown(
                        f"<div style='font-size:0.75rem;color:#aaa;'>{k.upper()}</div>"
                        f"<div style='font-size:0.95rem;font-weight:bold;'>{icon} {direction}</div>"
                        f"<div style='font-size:0.78rem;color:#ccc;word-wrap:break-word;white-space:normal;'>{desc}</div>",
                        unsafe_allow_html=True,
                    )

        # ローソク足 + テクニカル
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            row_heights=[0.6, 0.2, 0.2],
                            vertical_spacing=0.03)

        fig.add_trace(go.Candlestick(
            x=df_tech.index, open=df_tech["Open"], high=df_tech["High"],
            low=df_tech["Low"], close=df_tech["Close"], name="株価"), row=1, col=1)

        for ma, color in [("MA25", "#f39c12"), ("MA75", "#3498db"), ("BB_upper", "#aaa"), ("BB_lower", "#aaa")]:
            if ma in df_tech.columns:
                fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech[ma], name=ma,
                                         line=dict(color=color, width=1)), row=1, col=1)

        if "RSI" in df_tech.columns:
            fig.add_trace(go.Scatter(x=df_tech.index, y=df_tech["RSI"], name="RSI",
                                     line=dict(color="#9b59b6")), row=2, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
            fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        fig.add_trace(go.Bar(x=df_tech.index, y=df_tech["Volume"], name="出来高",
                             marker_color="#2ecc71"), row=3, col=1)

        fig.update_layout(height=600, template="plotly_dark", showlegend=True,
                          xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    with st.expander("📖 チャート・テクニカル指標の説明"):
        st.markdown("""
#### チャートの見方

| 用語 | 意味 | 見方 |
|------|------|------|
| **ローソク足** | 始値・高値・安値・終値を1本のローソク型グラフで表す | 緑（白）＝上昇日、赤（黒）＝下落日 |
| **MA25 / MA75** | 移動平均線（25日・75日の平均終値） | 上向きならトレンド上昇。MA25がMA75を上抜けると「ゴールデンクロス」（買いサイン）、下抜けると「デッドクロス」（売りサイン） |
| **BB（ボリンジャーバンド）** | 移動平均線の上下に標準偏差×2を加えた帯 | 上限（BB upper）を超えると「買われすぎ」、下限（BB lower）を割ると「売られすぎ」の目安 |
| **RSI** | 相対力指数（Relative Strength Index）。0〜100で過熱感を示す | **70以上**＝買われすぎ（売りサイン候補）、**30以下**＝売られすぎ（買いサイン候補）、50が中立 |
| **出来高（Volume）** | その日に売買された株数 | 株価が大きく動く時に出来高が増加すると動きが本物の可能性が高い |

---

#### シグナルの見方

| シグナル | 内容 |
|----------|------|
| 🟢 **買いシグナル** | RSI30以下・ゴールデンクロス等の強気サインが出ている状態 |
| 🔴 **売りシグナル** | RSI70以上・デッドクロス等の弱気サインが出ている状態 |
| ⚪ **中立** | 明確なシグナルなし |

> ⚠️ テクニカル指標は過去データにもとづく参考情報です。投資判断はご自身でご確認ください。
""")

with tab2:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("スコア内訳")
        score_data = {
            "配当スコア":  scores["dividend_score"],
            "財務スコア":  scores["financial_score"],
            "成長スコア":  scores["growth_score"],
            "割安スコア":  scores["value_score"],
        }
        for label, val in score_data.items():
            st.metric(label, f"{val} / 100")
    with c2:
        st.subheader("主要財務指標")
        st.table({
            "指標": ["配当利回り", "PER", "PBR", "ROE", "負債比率", "流動比率"],
            "値": [
                f"{scores['dividend_yield']:.2f}%" if scores.get("dividend_yield") else "—",
                f"{scores['per']:.1f}倍" if scores.get("per") else "—",
                f"{info.get('pbr'):.2f}倍" if info.get("pbr") else "—",
                f"{scores['roe']:.1f}%" if scores.get("roe") else "—",
                f"{info.get('debt_to_equity'):.1f}" if info.get("debt_to_equity") else "—",
                f"{info.get('current_ratio'):.2f}" if info.get("current_ratio") else "—",
            ]
        })

    st.divider()
    with st.expander("📖 指標・用語の説明"):
        st.markdown("""
#### 財務指標

| 用語 | 正式名称 | 意味 | 目安 |
|------|----------|------|------|
| **配当利回り** | Dividend Yield | 株価に対して1年間に受け取れる配当の割合。年間配当金 ÷ 株価 × 100 で計算。 | 日本株の平均は約2〜3%。高いほど収入が多い |
| **PER** | 株価収益率（Price Earnings Ratio） | 株価が1株あたり利益の何倍かを示す。低いほど割安とされる。 | 日本株は目安15〜20倍。業種によって差が大きい |
| **PBR** | 株価純資産倍率（Price Book-value Ratio） | 株価が1株あたり純資産の何倍かを示す。1倍未満は解散価値より安い状態。 | 1倍前後が割安の目安 |
| **ROE** | 自己資本利益率（Return on Equity） | 株主から預かったお金をどれだけ効率よく使って利益を生んでいるかを示す。 | 10%以上が優良の目安 |
| **負債比率** | Debt to Equity Ratio | 自己資本に対する負債の割合。低いほど財務的に安定している。 | 100%以下が望ましい |
| **流動比率** | Current Ratio | 短期的な支払い能力を示す。流動資産 ÷ 流動負債 × 100 で計算。 | 150〜200%以上が安心 |

---

#### スコアの見方（本アプリ独自の評価）

| スコア | 何を評価しているか |
|--------|-------------------|
| **配当スコア** | 配当利回りの高さ・安定性。配当重視の投資家に重要 |
| **財務スコア** | ROE・負債比率・流動比率などから見た企業の財務健全性 |
| **成長スコア** | 売上高・利益の成長率。将来的な株価上昇が期待できるかの目安 |
| **割安スコア** | PER・PBRの低さ（市場での割安度） |
| **総合スコア** | 上記4スコアを「プロフィール」で設定した投資スタイルの重みで合算した総合評価 |

---

#### チャートのテクニカル指標

| 用語 | 意味 | 見方 |
|------|------|------|
| **MA25 / MA75** | 移動平均線（25日・75日） | 過去の株価の平均値を結んだ線。上向きならトレンド上昇 |
| **BB（ボリンジャーバンド）** | 株価の変動範囲を示す上下のバンド | 上限を超えると「買われすぎ」、下限を割ると「売られすぎ」の目安 |
| **RSI** | 相対力指数（Relative Strength Index） | 0〜100の値で過熱感を示す。70以上で買われすぎ・30以下で売られすぎのサイン |
""")


with tab3:
    st.subheader("🤖 AI投資参考レポート")
    st.caption("※ このレポートは参考情報です。投資判断はご自身でお願いします。")
    if st.button("レポートを生成する", type="primary"):
        df_temp = get_price_history(ticker, "6mo")
        df_tech_ai = add_indicators(df_temp) if not df_temp.empty else df_temp
        sigs = get_signal(df_tech_ai)
        with st.spinner("Claudeが分析中..."):
            report = generate_report(info, scores, sigs, user_profile=user_profile)
        st.markdown(report)

with tab4:
    if df_div.empty:
        st.info("配当データがありません（無配当、またはデータ未取得）。")
    else:
        st.dataframe(df_div, use_container_width=True)
        fig_div = go.Figure(go.Bar(x=df_div["date"].astype(str), y=df_div["dividend"],
                                    marker_color="#f39c12"))
        fig_div.update_layout(title="配当推移", template="plotly_dark", height=300)
        st.plotly_chart(fig_div, use_container_width=True)

with tab5:
    news = get_stock_news(ticker, name)
    if not news:
        st.info("ニュースを取得できませんでした。")
    else:
        for n in news:
            st.markdown(f"**[{n['title']}]({n['link']})**")
            st.caption(f"{n.get('source', '')}　{n.get('published', '')}")
            st.divider()
