"""
J-Quants API v2 クライアント（日本株専用フォールバック）
認証: x-api-key ヘッダーにAPIキーを渡す方式
"""
import requests
import pandas as pd
from datetime import datetime, timedelta
from config import JQUANTS_REFRESH_TOKEN

_BASE = "https://api.jquants.com/v2"
_API_KEY = JQUANTS_REFRESH_TOKEN   # v2ではリフレッシュトークンではなくAPIキーとして使用


def _headers() -> dict:
    if not _API_KEY:
        return {}
    return {"x-api-key": _API_KEY}


def _code(ticker: str) -> str:
    """'7203.T' → '7203' に変換する"""
    return ticker.replace(".T", "").replace(".t", "")


def get_listed_info(ticker: str) -> dict:
    """銘柄の基本情報を取得する"""
    try:
        code = _code(ticker)
        r = requests.get(f"{_BASE}/equities/master",
                         params={"code": code},
                         headers=_headers(), timeout=10)
        if r.status_code != 200:
            return {}
        items = r.json().get("data", [])
        return items[0] if items else {}
    except Exception:
        return {}


def get_daily_quote(ticker: str) -> dict:
    """最新の日次株価を取得する（直近7日間に絞って取得）"""
    try:
        code = _code(ticker)
        date_from = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.get(
            f"{_BASE}/equities/bars/daily",
            params={"code": code, "from": date_from},
            headers=_headers(), timeout=10,
        )
        if r.status_code != 200:
            return {}
        quotes = r.json().get("data", [])
        return quotes[-1] if quotes else {}
    except Exception:
        return {}


def get_price_history_jquants(ticker: str, period: str = "1y") -> pd.DataFrame:
    """J-Quants APIで株価履歴を取得してDataFrameで返す"""
    try:
        code = _code(ticker)
        from datetime import datetime, timedelta
        period_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825, "10y": 1825}
        days = 1825 if period == "最大" else period_days.get(period, 365)
        date_from = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

        r = requests.get(
            f"{_BASE}/equities/bars/daily",
            params={"code": code, "from": date_from},
            headers=_headers(), timeout=15,
        )
        if r.status_code != 200:
            return pd.DataFrame()

        data = r.json().get("data", [])
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()

        # yfinance互換の列名に変換（調整済み優先）
        # J-Quants v2: AdjustmentOpen/High/Low/Close/Volume または AdjO/AdjH/AdjL/AdjC/AdjVo
        # 非調整フォールバック: Open/High/Low/Close/Volume または O/H/L/C/Vo
        adjusted_mappings = [
            ("AdjustmentOpen",   "Open"),
            ("AdjustmentHigh",   "High"),
            ("AdjustmentLow",    "Low"),
            ("AdjustmentClose",  "Close"),
            ("AdjustmentVolume", "Volume"),
            ("AdjO",  "Open"),
            ("AdjH",  "High"),
            ("AdjL",  "Low"),
            ("AdjC",  "Close"),
            ("AdjVo", "Volume"),
        ]
        fallback_mappings = [
            ("Open",   "Open"),
            ("High",   "High"),
            ("Low",    "Low"),
            ("Close",  "Close"),
            ("Volume", "Volume"),
            ("O",  "Open"),
            ("H",  "High"),
            ("L",  "Low"),
            ("C",  "Close"),
            ("Vo", "Volume"),
        ]
        for src, dst in adjusted_mappings:
            if src in df.columns and dst not in df.columns:
                df[dst] = pd.to_numeric(df[src], errors="coerce")
        for src, dst in fallback_mappings:
            if src in df.columns and dst not in df.columns:
                df[dst] = pd.to_numeric(df[src], errors="coerce")

        cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]
        return df[cols].dropna(how="all")
    except Exception:
        return pd.DataFrame()


def get_fin_summary(ticker: str) -> list[dict]:
    """財務サマリーを取得する"""
    try:
        code = _code(ticker)
        r = requests.get(f"{_BASE}/fins/summary",
                         params={"code": code},
                         headers=_headers(), timeout=15)
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    except Exception:
        return []


def get_dividend(ticker: str) -> list[dict]:
    """配当情報を取得する"""
    try:
        code = _code(ticker)
        r = requests.get(f"{_BASE}/fins/dividend",
                         params={"code": code},
                         headers=_headers(), timeout=10)
        if r.status_code != 200:
            return []
        return r.json().get("data", [])
    except Exception:
        return []


def _latest_annual(fins: list[dict]) -> tuple[dict, dict]:
    """財務サマリーから直近2期の年次データを抽出する"""
    def _is_fy(f):
        # J-Quants v2: TypeOfCurrentPeriod / 旧フィールド: CurPerType
        t = f.get("TypeOfCurrentPeriod") or f.get("CurPerType") or ""
        return t == "FY"

    def _has_profit(f):
        v = f.get("Profit") or f.get("NP")
        return v not in (None, "")

    annual = [f for f in fins if _is_fy(f) and _has_profit(f)]
    if not annual:
        annual = [f for f in fins if _is_fy(f)]

    def _sort_key(f):
        return f.get("DisclosedDate") or f.get("DiscDate") or f.get("CurPerEn") or ""

    annual = sorted(annual, key=_sort_key, reverse=True)
    return (annual[0] if annual else {}), (annual[1] if len(annual) > 1 else {})


def get_stock_info_jquants(ticker: str) -> dict:
    """J-Quants API v2で銘柄情報を取得しfetcher互換の形式で返す"""
    if not _API_KEY:
        return {"ticker": ticker, "error": "J-Quants APIキーが未設定です（.envのJQUANTS_REFRESH_TOKENを確認）"}

    info  = get_listed_info(ticker)
    quote = get_daily_quote(ticker)
    fins  = get_fin_summary(ticker)

    latest, prev = _latest_annual(fins)

    def _f(d, *keys):
        for k in keys:
            v = d.get(k)
            if v not in (None, "", "-"):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return None

    # 株価: J-Quants v2 = AdjustmentClose / 旧 = AdjC / 非調整 = Close
    price = _f(quote, "AdjustmentClose", "AdjC", "AdjClose", "Close", "C")

    # 財務指標 — J-Quants v2の正式フィールド名と旧フィールド名の両方を試みる
    np_     = _f(latest, "Profit",            "NP")            # 当期純利益
    sales   = _f(latest, "NetSales",          "Sales")         # 売上高
    eq      = _f(latest, "Equity",            "NetAssets", "Eq")  # 純資産
    ta      = _f(latest, "TotalAssets",       "TA")            # 総資産
    eps     = _f(latest, "EarningsPerShare",  "EPS")           # 1株当たり純利益
    bps     = _f(latest, "BookValuePerShare", "BPS")           # 1株当たり純資産
    prev_np = _f(prev,   "Profit",            "NP")
    prev_s  = _f(prev,   "NetSales",          "Sales")

    # 配当: 予想年間配当 → 実績年間配当の順で取得
    div_ann = _f(
        latest,
        "ForecastDividendPerShareAnnual",
        "ResultDividendPerShareAnnual",
        "FDivAnn", "DivAnn",
    )
    payout_ann = _f(latest, "PayoutRatioAnn", "FPayoutRatioAnn")

    # 各指標を計算
    roe        = (np_ / eq)             if np_ and eq and eq > 0  else None
    de         = ((ta - eq) / eq * 100) if ta  and eq and eq > 0  else None
    rev_growth = ((sales - prev_s) / abs(prev_s))   if sales and prev_s and prev_s != 0 else None
    ni_growth  = ((np_ - prev_np) / abs(prev_np))   if np_   and prev_np and prev_np != 0 else None
    per        = (price / eps)          if price and eps and eps > 0 else None
    pbr        = (price / bps)          if price and bps and bps > 0 else None
    div_yield  = (div_ann / price)      if div_ann and price and price > 0 else None
    payout     = (payout_ann / 100)     if payout_ann else None

    return {
        "ticker":          ticker,
        "name":            info.get("CoNameEn") or info.get("CoName", ticker),
        "market":          "JP",
        "sector":          info.get("S17Nm") or info.get("S33Nm", "不明"),
        "industry":        info.get("S33Nm", "不明"),
        "price":           price or 0,
        "currency":        "JPY",
        "market_cap":      None,
        "per":             per,
        "pbr":             pbr,
        "roe":             roe,
        "dividend_yield":  div_yield,
        "payout_ratio":    payout,
        "revenue_growth":  rev_growth,
        "earnings_growth": ni_growth,
        "debt_to_equity":  de,
        "current_ratio":   None,
        "52w_high":        None,
        "52w_low":         None,
        "description":     "",
        "_source":         "jquants",
        # 現在株価での再計算用（fetcher.pyで使用）
        "_eps":            eps,
        "_bps":            bps,
        "_div_ann":        div_ann,
    }


def is_available() -> bool:
    """J-Quants APIが利用可能か確認する"""
    if not _API_KEY:
        return False
    try:
        r = requests.get(f"{_BASE}/equities/master",
                         params={"code": "9433"},
                         headers=_headers(), timeout=8)
        return r.status_code == 200
    except Exception:
        return False
