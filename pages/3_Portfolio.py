import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
from streamlit_autorefresh import st_autorefresh
from core.fetcher import get_stock_info
from core.yahoo_direct import get_price_history_direct
from db.database import get_session, Portfolio

st.set_page_config(page_title="ポートフォリオ", page_icon="💼", layout="wide")

from core.auth_check import require_login
user = require_login()
user_id = user["id"]

st.title("💼 ポートフォリオ管理")

# 5分ごとに自動更新（長時間表示時のエラー防止）
st_autorefresh(interval=5 * 60 * 1000, key="portfolio_autorefresh")

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.1rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.85rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.85rem !important; }
</style>
""", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["📋 保有銘柄一覧", "➕ 銘柄を追加", "✏️ 編集・更新"])

# ── 保有銘柄一覧 ────────────────────────────────────────────
with tab1:
    session = get_session()
    holdings = session.query(Portfolio).filter_by(user_id=user_id).all()
    session.close()

    if not holdings:
        st.info("保有銘柄がありません。「銘柄を追加」タブから登録してください。")
    else:
        rows     = []
        sim_data = []  # シミュレーター用（表示列に含めない）

        for h in holdings:
            info        = get_stock_info(h.ticker)
            auto_price  = info.get("price") if "error" not in info else None
            price       = auto_price if auto_price else (h.manual_price if h.manual_price else None)
            price_label = "手動" if (not auto_price and h.manual_price) else ""
            cost  = h.shares * h.avg_cost
            value = h.shares * price if price else None
            gain  = (value - cost) if value is not None else None
            pct   = (gain / cost * 100) if (gain is not None and cost > 0) else None

            rows.append({
                "id":        h.id,
                "銘柄名":    h.name,
                "ティッカー": h.ticker,
                "市場":      h.market,
                "保有株数":  h.shares,
                "取得単価":  h.avg_cost,
                "現在株価":  (f"{price:,.0f} {price_label}".strip() if price else "取得不可"),
                "投資額":    round(cost),
                "評価額":    round(value) if value is not None else "—",
                "損益(円)":  round(gain) if gain is not None else "—",
                "損益(%)":   round(pct, 2) if pct is not None else "—",
            })

            # 配当・為替シミュレーター用データ
            dy         = info.get("dividend_yield") if "error" not in info else None
            annual_div = (h.shares * price * dy) if (price and dy and isinstance(price, (int, float))) else None
            sim_data.append({
                "name":       h.name,
                "market":     h.market,
                "shares":     h.shares,
                "price":      price,
                "dy":         dy,
                "annual_div": annual_div,
            })

        df = pd.DataFrame(rows)

        valid       = df[df["評価額"] != "—"]
        total_cost  = valid["投資額"].sum()
        total_value = pd.to_numeric(valid["評価額"], errors="coerce").sum()
        total_gain  = total_value - total_cost
        total_pct   = total_gain / total_cost * 100 if total_cost > 0 else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("投資総額",   f"¥{total_cost:,.0f}")
        m2.metric("評価総額",   f"¥{total_value:,.0f}")
        m3.metric("含み損益",   f"¥{total_gain:,.0f}", delta=f"{total_pct:+.2f}%")
        m4.metric("銘柄数",     f"{len(df)} 銘柄")

        st.divider()

        def _color_pnl(val):
            if isinstance(val, (int, float)):
                if val > 0:
                    return "color: #2ecc71"
                elif val < 0:
                    return "color: #e74c3c"
            return ""

        styled = (df.drop(columns=["id"])
                  .style.map(_color_pnl, subset=["損益(円)", "損益(%)"])
                  .format({
                      "保有株数":  "{:,.2f}",
                      "取得単価":  "{:,.2f}",
                      "損益(円)": "{:,.0f}",
                      "損益(%)":  "{:.2f}%",
                  }, na_rep="—"))
        st.dataframe(styled, use_container_width=True)

        if not valid.empty:
            fig = px.pie(valid, names="銘柄名", values="投資額", title="銘柄別投資比率",
                         template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

        # ── 配当収入シミュレーター ─────────────────────────────────
        div_data = [s for s in sim_data if s.get("annual_div") is not None]
        if div_data:
            st.divider()
            st.subheader("💴 年間配当収入シミュレーター")
            st.caption("配当利回りと現在株価から推計した参考値です。実際の受取額と異なる場合があります。")

            div_rows = []
            for s in div_data:
                after_tax = s["annual_div"] * 0.7969  # 20.315% 源泉徴収後
                div_rows.append({
                    "銘柄名":           s["name"],
                    "保有株数":         s["shares"],
                    "配当利回り(%)":    round(s["dy"] * 100, 2),
                    "年間配当収入(円)":  round(s["annual_div"]),
                    "税引後(約20.3%)":  round(after_tax),
                })

            total_div     = sum(s["annual_div"] for s in div_data)
            total_div_tax = total_div * 0.7969

            st.dataframe(pd.DataFrame(div_rows), use_container_width=True, hide_index=True)

            d1, d2 = st.columns(2)
            d1.metric("年間配当収入合計（税引前）", f"¥{total_div:,.0f}")
            d2.metric("年間配当収入合計（税引後）", f"¥{total_div_tax:,.0f}")

        # ── 為替影響シミュレーター（米国株のみ） ──────────────────
        us_data = [s for s in sim_data if s["market"] == "US" and s.get("price")]
        if us_data:
            st.divider()
            st.subheader("💱 為替影響シミュレーター（米国株）")

            try:
                df_fx      = get_price_history_direct("JPY=X", "5d")
                current_fx = float(df_fx["Close"].iloc[-1]) if not df_fx.empty else 150.0
            except Exception:
                current_fx = 150.0

            st.caption(f"現在レート: **{current_fx:.1f}円/ドル**　｜　各レートにおける評価額の参考値です。")

            fx_rows = []
            for s in us_data:
                p = s["price"]
                n = s["shares"]
                fx_rows.append({
                    "銘柄名":    s["name"],
                    "保有株数":  n,
                    "現在評価額": f"¥{n * p * current_fx:,.0f}",
                    "160円/$":   f"¥{n * p * 160:,.0f}",
                    "155円/$":   f"¥{n * p * 155:,.0f}",
                    "150円/$":   f"¥{n * p * 150:,.0f}",
                    "145円/$":   f"¥{n * p * 145:,.0f}",
                    "140円/$":   f"¥{n * p * 140:,.0f}",
                })

            st.dataframe(pd.DataFrame(fx_rows), use_container_width=True, hide_index=True)

# ── 銘柄を追加 ──────────────────────────────────────────────
with tab2:
    st.subheader("保有銘柄を登録")
    with st.form("add_holding"):
        c1, c2 = st.columns(2)
        with c1:
            ticker   = st.text_input("ティッカー（例: 7203.T / AAPL）")
            shares   = st.number_input("保有株数", min_value=0.0, step=1.0)
        with c2:
            avg_cost = st.number_input("取得単価（円）", min_value=0.0, step=1.0)
            purchase = st.date_input("取得日", value=date.today())
        manual_price_in = st.number_input(
            "現在価値（手動・任意）― 国債など自動取得できない資産の場合に入力",
            min_value=0.0, step=1.0, value=0.0,
        )
        memo      = st.text_area("メモ（任意）")
        submitted = st.form_submit_button("登録する", type="primary")

    if submitted:
        if not ticker:
            st.error("ティッカーシンボルを入力してください。")
        elif shares <= 0 or avg_cost <= 0:
            st.error("保有株数・取得単価は0より大きい値を入力してください。")
        else:
            t = ticker.strip().upper()
            manual_p = manual_price_in if manual_price_in > 0 else None
            with st.spinner(f"{t} を確認中..."):
                info = get_stock_info(t)
            if "error" in info or not info.get("price"):
                if manual_p is None:
                    st.error(
                        f"⚠️ ティッカー「{t}」の株価データを取得できませんでした。\n\n"
                        "ティッカーシンボルの形式を確認してください（例: `1547.T` / `AAPL`）。"
                        "国債など自動取得できない資産は「現在価値（手動）」を入力してください。"
                    )
                else:
                    name = t
                    add_session = get_session()
                    add_session.add(Portfolio(
                        ticker=t,
                        name=name,
                        market="OTHER",
                        shares=shares,
                        avg_cost=avg_cost,
                        manual_price=manual_p,
                        purchase_date=purchase,
                        memo=memo,
                        user_id=user_id,
                    ))
                    add_session.commit()
                    add_session.close()
                    st.success(f"✅ {t} を登録しました（手動価格: {manual_p:,.0f}円）")
                    st.rerun()
            else:
                name = info.get("name", t)
                add_session = get_session()
                add_session.add(Portfolio(
                    ticker=t,
                    name=name,
                    market="JP" if t.endswith(".T") else "US",
                    shares=shares,
                    avg_cost=avg_cost,
                    manual_price=manual_p,
                    purchase_date=purchase,
                    memo=memo,
                    user_id=user_id,
                ))
                add_session.commit()
                add_session.close()
                st.success(f"✅ {name}（{t}）を登録しました")
                st.rerun()

# ── 編集・更新 ──────────────────────────────────────────────
with tab3:
    session3  = get_session()
    holdings3 = session3.query(Portfolio).filter_by(user_id=user_id).all()
    session3.close()

    if not holdings3:
        st.info("保有銘柄がありません。「銘柄を追加」タブから登録してください。")
    else:
        # 編集
        st.subheader("銘柄情報を更新")
        edit_options   = {f"{h.name}（{h.ticker}）": h.id for h in holdings3}
        selected_label = st.selectbox("更新する銘柄", list(edit_options.keys()), key="edit_select")
        selected_id    = edit_options[selected_label]
        h_edit         = next(x for x in holdings3 if x.id == selected_id)

        with st.form("edit_holding"):
            c1, c2 = st.columns(2)
            with c1:
                new_shares   = st.number_input("保有株数", min_value=0.0, step=1.0,
                                               value=float(h_edit.shares))
            with c2:
                new_avg_cost = st.number_input("取得単価（円）", min_value=0.0, step=1.0,
                                               value=float(h_edit.avg_cost))
            new_manual_price = st.number_input(
                "現在価値（手動・任意）",
                min_value=0.0, step=1.0,
                value=float(h_edit.manual_price) if h_edit.manual_price else 0.0,
            )
            new_purchase = st.date_input("取得日", value=h_edit.purchase_date)
            new_memo     = st.text_area("メモ", value=h_edit.memo or "")
            update_ok    = st.form_submit_button("更新する", type="primary")

        if update_ok:
            upd = get_session()
            obj = upd.query(Portfolio).filter_by(id=selected_id).first()
            if obj:
                obj.shares        = new_shares
                obj.avg_cost      = new_avg_cost
                obj.manual_price  = new_manual_price if new_manual_price > 0 else None
                obj.purchase_date = new_purchase
                obj.memo          = new_memo
                upd.commit()
            upd.close()
            st.success("更新しました")
            st.rerun()

        # 削除
        st.divider()
        st.subheader("銘柄を削除")
        del_options = {f"{h.name}（{h.ticker}）": h.id for h in holdings3}
        del_target  = st.selectbox("削除する銘柄", list(del_options.keys()), key="del_select")
        if st.button("削除する", type="secondary"):
            del_s = get_session()
            obj   = del_s.query(Portfolio).filter_by(id=del_options[del_target]).first()
            if obj:
                del_s.delete(obj)
                del_s.commit()
            del_s.close()
            st.success("削除しました")
            st.rerun()
