import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from db.database import get_session, Watchlist
from core.fetcher import get_stock_info
from core.scorer import calc_total_score, score_label

st.set_page_config(page_title="ウォッチリスト", page_icon="⭐", layout="wide")

from core.auth_check import require_login
user = require_login()

session = get_session()
watches = session.query(Watchlist).filter_by(user_id=user["id"]).order_by(Watchlist.added_at.desc()).all()
session.close()

st.title("⭐ ウォッチリスト")

if not watches:
    st.info("ウォッチリストに銘柄が登録されていません。「銘柄詳細」ページから追加してください。")
    st.stop()

st.caption(f"登録銘柄: {len(watches)} 件　｜　銘柄名をクリックすると詳細画面へ移動します")


def fetch_watch(w) -> dict:
    info = get_stock_info(w.ticker)
    if "error" in info:
        return {"ticker": w.ticker, "name": w.name, "price": None, "currency": "",
                "dividend_yield": None, "per": None, "pbr": None, "roe": None, "total_score": None}
    scores = calc_total_score(info)
    return {
        "ticker":         w.ticker,
        "name":           w.name,
        "price":          info.get("price"),
        "currency":       info.get("currency", ""),
        "dividend_yield": scores.get("dividend_yield"),
        "per":            scores.get("per"),
        "pbr":            info.get("pbr"),
        "roe":            scores.get("roe"),
        "total_score":    scores.get("total_score"),
    }


with st.spinner("データ取得中..."):
    rows = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(fetch_watch, w): w for w in watches}
        for future in as_completed(futures):
            rows.append(future.result())

rows.sort(key=lambda x: x.get("total_score") or 0, reverse=True)

# ヘッダー行
hcols = st.columns([3, 1.5, 2, 1.8, 1.5, 1.5, 2.5])
for col, label in zip(hcols, ["銘柄名", "ティッカー", "株価", "配当利回り(%)", "PER", "ROE(%)", "スコア"]):
    col.markdown(f"<span style='color:#aaa;font-size:0.85rem'>{label}</span>", unsafe_allow_html=True)
st.divider()

# データ行
for row in rows:
    dcols = st.columns([3, 1.5, 2, 1.8, 1.5, 1.5, 2.5])
    with dcols[0]:
        if st.button(f"📊 {row['name']}", key=f"d_{row['ticker']}", use_container_width=True):
            st.session_state["prefill_ticker"] = row["ticker"]
            st.switch_page("pages/2_Detail.py")
    dcols[1].write(row["ticker"])
    p = row.get("price")
    dcols[2].write(f"{p:,.0f} {row['currency']}" if p else "—")
    dy = row.get("dividend_yield")
    dcols[3].write(f"{dy:.2f}%" if dy else "—")
    per = row.get("per")
    dcols[4].write(f"{per:.1f}" if per else "—")
    roe = row.get("roe")
    dcols[5].write(f"{roe:.1f}%" if roe else "—")
    sc = row.get("total_score")
    dcols[6].write(f"{sc:.0f}点 {score_label(sc)}" if sc is not None else "—")

st.divider()

# 削除セクション
with st.expander("🗑 ウォッチリストから削除"):
    del_options = {f"{w.name} ({w.ticker})": w.ticker for w in watches}
    del_target = st.selectbox("削除する銘柄", list(del_options.keys()))
    if st.button("削除する", type="secondary"):
        ticker_to_del = del_options[del_target]
        del_session = get_session()
        obj = del_session.query(Watchlist).filter_by(ticker=ticker_to_del, user_id=user["id"]).first()
        if obj:
            del_session.delete(obj)
            del_session.commit()
        del_session.close()
        st.success("削除しました")
        st.rerun()
