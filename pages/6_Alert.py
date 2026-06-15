import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from db.database import get_session, Watchlist, PriceAlert
from core.fetcher import get_stock_info
from core.yahoo_direct import get_price_history_direct

st.set_page_config(page_title="価格アラート", page_icon="🔔", layout="wide")

from core.auth_check import require_login
user = require_login()
user_id = user["id"]

st.title("🔔 価格アラート設定")
st.caption("1日3回（9:05 / 12:30 / 15:35）チェックし、条件達成時にメールで通知します。")

if st.session_state.pop("alert_saved", False):
    st.markdown(
        """<div style="position:fixed;top:3.5rem;left:50%;transform:translateX(-50%);background:#d4edda;color:#155724;padding:.6rem 1.8rem;border-radius:.5rem;border:1px solid #c3e6cb;z-index:9999;font-size:1rem;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.2);">✅ アラート設定を保存しました</div>""",
        unsafe_allow_html=True,
    )


session = get_session()
watches = session.query(Watchlist).filter_by(user_id=user_id).order_by(Watchlist.added_at.desc()).all()
alerts  = session.query(PriceAlert).filter_by(user_id=user_id).all()
session.close()

# ── 指数アラート ──────────────────────────────────────────────
INDICES = [
    {"ticker": "^N225", "name": "日経平均"},
    {"ticker": "^DJI",  "name": "NYダウ"},
    {"ticker": "^IXIC", "name": "NASDAQ"},
]
index_tickers = [i["ticker"] for i in INDICES]

st.subheader("📊 指数アラート（下落通知）")
st.caption("設定した水準を下回ったら通知します。「買い場の目安」として活用できます。")

index_alert_map = {
    a.ticker: a for a in alerts
    if a.ticker in index_tickers and a.alert_type == "below"
}

for idx in INDICES:
    ticker   = idx["ticker"]
    name     = idx["name"]
    existing = index_alert_map.get(ticker)

    try:
        df_idx  = get_price_history_direct(ticker, "5d")
        current = float(df_idx["Close"].iloc[-1]) if not df_idx.empty else None
    except Exception:
        current = None

    with st.expander(
        f"{'🟢' if (existing and existing.active) else '⚪'} {name}（{ticker}）",
        expanded=bool(existing and existing.active),
    ):
        if current:
            st.caption(f"現在値: **{current:,.0f}**")

        enabled   = st.checkbox("有効", value=existing.active if existing else False,
                                key=f"idx_en_{ticker}")
        threshold = st.number_input(
            "下限閾値（この値を下回ったら通知）",
            min_value=0.0, step=100.0,
            value=float(existing.threshold) if existing else (float(round(current, -2)) if current else 0.0),
            key=f"idx_th_{ticker}",
        )

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("保存", key=f"idx_save_{ticker}", type="primary"):
                s  = get_session()
                ex = s.query(PriceAlert).filter_by(ticker=ticker, alert_type="below", user_id=user_id).first()
                if threshold <= 0:
                    if ex:
                        s.delete(ex)
                elif ex:
                    ex.threshold = threshold
                    ex.active    = enabled
                else:
                    s.add(PriceAlert(
                        ticker=ticker, name=name,
                        alert_type="below", threshold=threshold,
                        active=enabled, user_id=user_id,
                    ))
                s.commit()
                s.close()
                st.session_state["alert_saved"] = True
                st.rerun()
        with c2:
            if existing:
                if st.button("削除", key=f"idx_del_{ticker}", type="secondary"):
                    s  = get_session()
                    ex = s.query(PriceAlert).filter_by(ticker=ticker, alert_type="below", user_id=user_id).first()
                    if ex:
                        s.delete(ex)
                    s.commit()
                    s.close()
                    st.rerun()

st.divider()

# ── 銘柄アラート（ウォッチリスト） ────────────────────────────
st.subheader("📈📉 銘柄アラート（ウォッチリスト）")

if not watches:
    st.info("ウォッチリストに銘柄が登録されていません。「銘柄詳細」ページから追加してください。")
else:
    def get_stock_alerts(ticker):
        return [a for a in alerts if a.ticker == ticker]

    for w in watches:
        w_alerts = get_stock_alerts(w.ticker)
        above    = next((a for a in w_alerts if a.alert_type == "above"), None)
        below    = next((a for a in w_alerts if a.alert_type == "below"), None)

        with st.expander(
            f"{'🟢' if w_alerts else '⚪'} {w.name}（{w.ticker}）",
            expanded=bool(w_alerts),
        ):
            info    = get_stock_info(w.ticker)
            current = info.get("price") if "error" not in info else None
            if current:
                st.caption(f"現在株価: **{current:,.0f}** {info.get('currency', '')}")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**📈 上昇アラート**（この価格以上になったら通知）")
                above_enabled   = st.checkbox("有効", value=above.active if above else False,
                                              key=f"above_en_{w.ticker}")
                above_threshold = st.number_input(
                    "閾値", min_value=0.0, step=1.0,
                    value=float(above.threshold) if above else (float(current) if current else 0.0),
                    key=f"above_th_{w.ticker}",
                )

            with col2:
                st.markdown("**📉 下落アラート**（この価格以下になったら通知）")
                below_enabled   = st.checkbox("有効", value=below.active if below else False,
                                              key=f"below_en_{w.ticker}")
                below_threshold = st.number_input(
                    "閾値", min_value=0.0, step=1.0,
                    value=float(below.threshold) if below else (float(current) if current else 0.0),
                    key=f"below_th_{w.ticker}",
                )

            if st.button("保存", key=f"save_{w.ticker}", type="primary"):
                s = get_session()
                for alert_type, enabled, threshold in [
                    ("above", above_enabled, above_threshold),
                    ("below", below_enabled, below_threshold),
                ]:
                    existing = s.query(PriceAlert).filter_by(
                        ticker=w.ticker, alert_type=alert_type, user_id=user_id
                    ).first()
                    if threshold <= 0:
                        if existing:
                            s.delete(existing)
                    elif existing:
                        existing.threshold = threshold
                        existing.active    = enabled
                    else:
                        s.add(PriceAlert(
                            ticker=w.ticker, name=w.name,
                            alert_type=alert_type, threshold=threshold,
                            active=enabled, user_id=user_id,
                        ))
                s.commit()
                s.close()
                st.session_state["alert_saved"] = True
                st.rerun()

            if w_alerts:
                if st.button("このアラートをすべて削除", key=f"del_{w.ticker}", type="secondary"):
                    s = get_session()
                    for a in s.query(PriceAlert).filter_by(ticker=w.ticker, user_id=user_id).all():
                        s.delete(a)
                    s.commit()
                    s.close()
                    st.rerun()

st.divider()

# ── 有効なアラート一覧 ─────────────────────────────────────────
st.subheader("現在の有効アラート一覧")
active_alerts = [a for a in alerts if a.active]
if not active_alerts:
    st.info("有効なアラートはありません。")
else:
    rows = []
    for a in active_alerts:
        category = "📊 指数" if a.ticker in index_tickers else "💹 銘柄"
        rows.append({
            "区分":      category,
            "名称":      a.name,
            "ティッカー": a.ticker,
            "種別":      "📈 上昇" if a.alert_type == "above" else "📉 下落",
            "閾値":      f"{a.threshold:,.0f}",
            "最終通知":  str(a.last_notified) if a.last_notified else "未通知",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
