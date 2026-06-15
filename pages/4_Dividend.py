import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from db.database import get_session, Portfolio, Watchlist

st.set_page_config(page_title="配当カレンダー", page_icon="📅", layout="wide")

from core.auth_check import require_login
user = require_login()

st.title("📅 配当カレンダー")
st.caption("保有銘柄・ウォッチリスト銘柄の配当情報をまとめて表示します")

session = get_session()
holdings = session.query(Portfolio).filter_by(user_id=user["id"]).all()
watches  = session.query(Watchlist).filter_by(user_id=user["id"]).all()
session.close()

ticker_names = {**{h.ticker: h.name for h in holdings}, **{w.ticker: w.name for w in watches}}
all_tickers  = list(ticker_names.keys())

if not all_tickers:
    st.info("保有銘柄またはウォッチリストに銘柄を登録すると、ここに配当情報が表示されます。")
    st.stop()


def _fmt_date(val):
    if not val:
        return "—"
    try:
        return str(pd.to_datetime(val))[:10]
    except Exception:
        return str(val)[:10]


def fetch_dividend_info(ticker: str) -> dict:
    base = {
        "ティッカー":    ticker,
        "銘柄名":        ticker_names.get(ticker, ticker),
        "配当利回り(%)": None,
        "権利確定日":    "取得失敗",
        "配当支払日":    "取得失敗",
        "年間配当(1株)": None,
    }
    try:
        if ticker.endswith(".T"):
            from core.jquants import (get_dividend, get_fin_summary,
                                       get_listed_info, _latest_annual)
            from core.yahoo_direct import get_current_price

            info = get_listed_info(ticker)
            name = info.get("CoNameEn") or info.get("CoName", "")
            if name:
                base["銘柄名"] = name

            divs = get_dividend(ticker)
            ex_date = pay_date = None
            if divs:
                latest_div = max(divs, key=lambda x: x.get("RecordDate") or "")
                ex_date  = latest_div.get("RecordDate")
                pay_date = latest_div.get("PayableDate")

            fins = get_fin_summary(ticker)
            latest_fin, _ = _latest_annual(fins)

            def _f(d, *keys):
                for k in keys:
                    v = d.get(k)
                    if v not in (None, "", "-"):
                        try:
                            return float(v)
                        except Exception:
                            pass
                return None

            div_ann   = _f(latest_fin, "DivAnn", "FDivAnn")
            price     = get_current_price(ticker)
            div_yield = (div_ann / price) if (div_ann and price and price > 0) else None

            base.update({
                "配当利回り(%)": round(div_yield * 100, 2) if div_yield else None,
                "権利確定日":    _fmt_date(ex_date),
                "配当支払日":    _fmt_date(pay_date),
                "年間配当(1株)": div_ann,
            })

        else:
            from core.yahoo_direct import get_fundamental_data

            fd = get_fundamental_data(ticker)
            if fd:
                dy = fd.get("dividend_yield")
                base.update({
                    "銘柄名":        fd.get("name", base["銘柄名"]),
                    "配当利回り(%)": round(dy * 100, 2) if dy else None,
                    "権利確定日":    fd.get("ex_date") or "—",
                    "配当支払日":    fd.get("pay_date") or "—",
                    "年間配当(1株)": fd.get("dividend_rate"),
                })

    except Exception:
        pass

    return base


with st.spinner("配当情報を取得中..."):
    rows = [fetch_dividend_info(t) for t in all_tickers]

df = pd.DataFrame(rows).sort_values("権利確定日").reset_index(drop=True)
df.index = df.index + 1

st.dataframe(
    df,
    use_container_width=True,
    column_config={
        "配当利回り(%)": st.column_config.NumberColumn("配当利回り(%)", format="%.2f%%"),
        "年間配当(1株)": st.column_config.NumberColumn("年間配当(1株)", format="%.1f"),
    }
)

st.divider()
st.subheader("配当利回り比較")
chart_df = df.dropna(subset=["配当利回り(%)"]).set_index("銘柄名")["配当利回り(%)"]
if not chart_df.empty:
    st.bar_chart(chart_df)
