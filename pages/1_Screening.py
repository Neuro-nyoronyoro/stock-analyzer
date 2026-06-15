from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.fetcher import MAJOR_JP, MAJOR_US, get_stock_info
from core.scorer import calc_total_score, score_label, get_cached_score, save_score_cache
from config import DEFAULT_SCREEN

st.set_page_config(page_title="銘柄スクリーニング", page_icon="🔍", layout="wide")

from core.auth_check import require_login
require_login()

st.title("🔍 銘柄スクリーニング")
st.caption("条件を設定して投資候補銘柄を絞り込みます")

# サイドバー：フィルター条件
with st.sidebar:
    st.header("絞り込み条件")
    market    = st.radio("対象市場", ["日本株", "米国株", "両方"], index=2)
    min_dy    = st.slider("配当利回り（%）以上", 0.0, 8.0, DEFAULT_SCREEN["min_dividend_yield"], 0.5)
    max_per   = st.number_input("PER 上限（この値より高い銘柄を除外）",
                               min_value=1.0, max_value=300.0,
                               value=float(DEFAULT_SCREEN["max_per"]), step=1.0)
    min_roe   = st.slider("ROE（%）以上", 0.0, 30.0, DEFAULT_SCREEN["min_roe"], 1.0)
    min_score = st.slider("総合スコア以上", 0.0, 100.0, DEFAULT_SCREEN["min_score"], 5.0)
    max_workers = st.slider("並列取得数", 1, 5, 2, 1,
                            help="大きいほど速いが、レート制限に引っかかりやすくなります。通常は2推奨")

    st.divider()
    use_cache  = st.checkbox("キャッシュを使用する（高速）", value=True,
                             help="24時間以内に取得済みのデータを再利用します")
    cache_only = st.checkbox("キャッシュ済み銘柄のみ表示", value=False,
                             help="yfinanceへの通信を行わず、DB保存済みデータのみで即時表示します。レート制限中に便利です")
    clear_cache = st.button("🗑 キャッシュを削除して再取得", use_container_width=True)
    run         = st.button("🔍 スクリーニング実行", type="primary", use_container_width=True)

if clear_cache:
    try:
        from db.database import get_session, ScoreCache
        session = get_session()
        session.query(ScoreCache).delete()
        session.commit()
        session.close()
        st.sidebar.success("キャッシュを削除しました")
    except Exception as e:
        st.sidebar.error(f"削除失敗: {e}")


def fetch_one(stock: dict) -> dict | None:
    """1銘柄のデータを取得してスコアを返す（キャッシュ優先）"""
    ticker = stock["ticker"]

    if use_cache:
        cached = get_cached_score(ticker)
        if cached is not None:
            return {"ticker": ticker, "name": stock["name"], "sector": stock["sector"],
                    "from_cache": True, **cached}

    info = get_stock_info(ticker)
    if "error" in info:
        return None

    if info.get("_partial"):
        return None

    scores = calc_total_score(info)
    save_score_cache(ticker, scores)

    return {
        "ticker":   ticker,
        "name":     stock["name"],
        "sector":   info.get("sector", stock["sector"]),
        "price":    info.get("price", 0),
        "currency": info.get("currency", ""),
        "pbr":      info.get("pbr"),
        "from_cache": False,
        **scores,
    }


if not run:
    try:
        from db.database import get_session, ScoreCache
        session = get_session()
        cache_count = session.query(ScoreCache).count()
        session.close()
        if cache_count > 0:
            st.info(f"キャッシュ済み銘柄: {cache_count} 件（24時間有効）。「スクリーニング実行」を押すとキャッシュ分は瞬時に取得します。")
        else:
            st.info("左のサイドバーで条件を設定し「スクリーニング実行」を押してください。")
    except Exception:
        st.info("左のサイドバーで条件を設定し「スクリーニング実行」を押してください。")
    st.stop()

# ── キャッシュのみモード ──────────────────────────────────────
if cache_only:
    from db.database import get_session, ScoreCache
    ticker_map = {s["ticker"]: s for s in MAJOR_JP + MAJOR_US}
    db_session = get_session()
    rows = db_session.query(ScoreCache).all()
    db_session.close()

    results = []
    for row in rows:
        meta = ticker_map.get(row.ticker, {"name": row.ticker, "sector": "不明"})
        results.append({
            "ticker":         row.ticker,
            "name":           meta["name"],
            "sector":         meta["sector"],
            "total_score":    row.total_score,
            "dividend_score": row.dividend_score,
            "financial_score":row.financial_score,
            "growth_score":   row.growth_score,
            "value_score":    row.value_score,
            "dividend_yield": row.dividend_yield,
            "per":            row.per,
            "roe":            row.roe,
        })

    if not results:
        st.warning("キャッシュに銘柄データがありません。通常モードで一度スクリーニングを実行してください。")
        st.stop()

    st.info(f"キャッシュ済み銘柄: **{len(results)} 銘柄**を表示中（yfinance通信なし）")

# ── 通常モード（yfinance / J-Quants取得） ────────────────────
else:
    candidates = []
    if market in ("日本株", "両方"):
        candidates += MAJOR_JP
    if market in ("米国株", "両方"):
        candidates += MAJOR_US

    total = len(candidates)
    st.info(f"対象銘柄数: **{total} 銘柄**（日本株 {len(MAJOR_JP)} ・米国株 {len(MAJOR_US)}）")

    progress_bar = st.progress(0, text="準備中...")
    results      = []
    done_count   = 0
    cache_hits   = 0
    fetch_count  = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, s): s for s in candidates}
        for future in as_completed(futures):
            done_count += 1
            progress_bar.progress(done_count / total,
                                  text=f"取得中... {done_count}/{total} 銘柄")
            result = future.result()
            if result is None:
                continue
            if result.get("from_cache"):
                cache_hits += 1
            else:
                fetch_count += 1
            results.append(result)

    progress_bar.empty()

    if not results:
        st.error("データを取得できませんでした。yfinanceのレート制限中の可能性があります。"
                 "しばらく待ってから再試行するか、「キャッシュ済み銘柄のみ表示」をお試しください。")
        st.stop()

# フィルタリング（Noneはデータ未取得として条件を適用しない）
filtered = []
for r in results:
    dy    = r.get("dividend_yield")
    per   = r.get("per")
    roe   = r.get("roe")
    score = r.get("total_score") or 0

    if dy is not None and dy < min_dy:
        continue
    if per is not None and per > max_per:
        continue
    if roe is not None and roe < min_roe:
        continue
    if score < min_score:
        continue
    filtered.append(r)

if not filtered:
    st.warning("条件に合う銘柄が見つかりませんでした。条件を緩めてお試しください。")
    st.stop()

df = pd.DataFrame(filtered).sort_values("total_score", ascending=False).reset_index(drop=True)
df.index = df.index + 1

if cache_only:
    st.success(f"✅ {len(df)} 銘柄が条件に一致（キャッシュのみ表示）")
else:
    st.success(
        f"✅ {len(df)} 銘柄が条件に一致 　｜　"
        f"キャッシュ: {cache_hits} 件　新規取得: {fetch_count} 件"
    )

if not cache_only and market in ("米国株", "両方"):
    jp_count = sum(1 for r in filtered if not r.get("ticker", "").endswith(".T"))
    if jp_count == 0:
        st.info("ℹ️ 現在yfinanceのレート制限中のため米国株の財務データを取得できません。"
                "米国株はキャッシュ済みの銘柄のみ表示されます。"
                "日本株は J-Quants により正常取得されています。")

df_display = pd.DataFrame({
    "銘柄名":        df["name"],
    "ticker":       df["ticker"],
    "市場":         df["ticker"].apply(lambda t: "日本" if t.endswith(".T") else "米国"),
    "セクター":      df["sector"],
    "配当利回り(%)": df["dividend_yield"],
    "PER":          pd.to_numeric(df["per"], errors="coerce").round(1) if "per" in df.columns else None,
    "PBR":          pd.to_numeric(df["pbr"], errors="coerce").round(2) if "pbr" in df.columns else None,
    "ROE(%)":       df["roe"],
    "総合スコア":    df["total_score"],
    "評価":         df["total_score"].apply(score_label),
})

st.dataframe(
    df_display,
    use_container_width=True,
    height=520,
    column_config={
        "総合スコア":    st.column_config.ProgressColumn("総合スコア", min_value=0, max_value=100),
        "配当利回り(%)": st.column_config.NumberColumn("配当利回り(%)", format="%.2f%%"),
    }
)

st.divider()
st.subheader("スコア内訳（上位15銘柄）")
chart_df = pd.DataFrame({
    "銘柄名":   df["name"].head(15),
    "配当":     df["dividend_score"].head(15),
    "財務":     df["financial_score"].head(15),
    "成長":     df["growth_score"].head(15),
}).set_index("銘柄名")
st.bar_chart(chart_df)
