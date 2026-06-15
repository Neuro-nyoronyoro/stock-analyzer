"""
Yahoo Finance 直接HTTPアクセス（自前cookie/crumb取得方式）
"""
import requests
import pandas as pd
import threading
import datetime

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

_RANGE_MAP = {
    "1mo": "1mo", "3mo": "3mo", "6mo": "6mo",
    "1y":  "1y",  "2y":  "2y",  "5y":  "5y",
    "10y": "10y", "最大": "max",
}

# crumbセッション管理（スレッドセーフ）
_crumb_lock    = threading.Lock()
_crumb_value   = None
_crumb_session = None


def _get_crumb_session():
    """cookie+crumbを取得してセッションを返す（キャッシュあり）"""
    global _crumb_value, _crumb_session
    with _crumb_lock:
        if _crumb_value and _crumb_session:
            return _crumb_session, _crumb_value
        session = requests.Session()
        session.headers.update({
            "User-Agent": _HEADERS["User-Agent"],
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        try:
            session.get("https://finance.yahoo.com/", timeout=10)
            cr = session.get("https://query2.finance.yahoo.com/v1/test/getcrumb", timeout=10)
            if cr.status_code == 200 and cr.text:
                _crumb_value  = cr.text.strip()
                _crumb_session = session
                return _crumb_session, _crumb_value
        except Exception:
            pass
        return session, ""


def _reset_crumb():
    """crumbキャッシュをリセット（401エラー時に再取得させる）"""
    global _crumb_value, _crumb_session
    with _crumb_lock:
        _crumb_value  = None
        _crumb_session = None


def get_chart_data(ticker: str, period: str = "1y") -> dict:
    """v8 chart APIから株価データを取得する（crumb不要）"""
    range_ = _RANGE_MAP.get(period, "1y")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    try:
        r = requests.get(url, params={"interval": "1d", "range": range_},
                         headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return {}
        return r.json().get("chart", {}).get("result", [{}])[0]
    except Exception:
        return {}


def get_current_price(ticker: str):
    """現在株価のみを取得する"""
    data = get_chart_data(ticker, "5d")
    if not data:
        return None
    return data.get("meta", {}).get("regularMarketPrice")


def get_fundamental_data(ticker: str) -> dict:
    """cookie+crumbを使ってYahoo Finance v10から財務データを取得する"""
    url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    modules = "financialData,summaryDetail,defaultKeyStatistics,assetProfile"

    for attempt in range(2):
        try:
            session, crumb = _get_crumb_session()
            if not crumb:
                return {}
            params = {"modules": modules, "formatted": "false", "crumb": crumb}
            r = session.get(url, params=params, timeout=15)
            if r.status_code == 401:
                _reset_crumb()
                continue
            if r.status_code != 200:
                return {}
            result = r.json().get("quoteSummary", {}).get("result", [])
            if not result:
                return {}
            data = result[0]
            fd = data.get("financialData", {})
            sd = data.get("summaryDetail", {})
            ks = data.get("defaultKeyStatistics", {})
            ap = data.get("assetProfile", {})

            def _v(d, key):
                val = d.get(key)
                if isinstance(val, dict):
                    return val.get("raw")
                return val

            def _ts(val):
                if val is None:
                    return None
                try:
                    ts = int(val) if not isinstance(val, dict) else int(val.get("raw", 0))
                    if ts > 0:
                        return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
                except Exception:
                    pass
                return None

            return {
                "name":            ap.get("longName") or ap.get("shortName", ticker),
                "sector":          ap.get("sector", "不明"),
                "industry":        ap.get("industry", "不明"),
                "price":           _v(fd, "currentPrice") or _v(sd, "regularMarketPrice"),
                "currency":        sd.get("currency", "USD"),
                "market_cap":      _v(sd, "marketCap"),
                "per":             _v(sd, "trailingPE"),
                "pbr":             _v(ks, "priceToBook"),
                "roe":             _v(fd, "returnOnEquity"),
                "dividend_yield":  _v(sd, "dividendYield"),
                "dividend_rate":   _v(sd, "dividendRate"),
                "ex_date":         _ts(_v(sd, "exDividendDate")),
                "pay_date":        _ts(_v(sd, "dividendDate")),
                "payout_ratio":    _v(sd, "payoutRatio"),
                "revenue_growth":  _v(fd, "revenueGrowth"),
                "earnings_growth": _v(fd, "earningsGrowth"),
                "debt_to_equity":  _v(fd, "debtToEquity"),
                "current_ratio":   _v(fd, "currentRatio"),
                "52w_high":        _v(sd, "fiftyTwoWeekHigh"),
                "52w_low":         _v(sd, "fiftyTwoWeekLow"),
                "description":     ap.get("longBusinessSummary", ""),
            }
        except Exception:
            _reset_crumb()
    return {}


def get_price_history_direct(ticker: str, period: str = "1y") -> pd.DataFrame:
    """直接HTTPで株価履歴をDataFrameとして返す"""
    data = get_chart_data(ticker, period)
    if not data:
        return pd.DataFrame()
    try:
        timestamps = data.get("timestamp", [])
        quotes     = data.get("indicators", {}).get("quote", [{}])[0]
        adj_close  = data.get("indicators", {}).get("adjclose", [{}])
        adj_close  = adj_close[0].get("adjclose", []) if adj_close else []
        if not timestamps or not quotes.get("close"):
            return pd.DataFrame()
        df = pd.DataFrame({
            "Open":   quotes.get("open",   [None] * len(timestamps)),
            "High":   quotes.get("high",   [None] * len(timestamps)),
            "Low":    quotes.get("low",    [None] * len(timestamps)),
            "Close":  quotes.get("close",  [None] * len(timestamps)),
            "Volume": quotes.get("volume", [None] * len(timestamps)),
        }, index=pd.to_datetime(timestamps, unit="s").tz_localize("UTC").tz_convert("Asia/Tokyo").tz_localize(None))
        if adj_close:
            df["Adj Close"] = adj_close
        return df.dropna(subset=["Close"])
    except Exception:
        return pd.DataFrame()


def get_full_info_direct(ticker: str) -> dict:
    """米国株の完全情報を取得する（crumb付きv10 → 失敗時は価格のみ）"""
    fd = get_fundamental_data(ticker)
    price = get_current_price(ticker)

    if fd:
        if price:
            fd["price"] = price
        return {
            "ticker":   ticker,
            "market":   "US",
            "_source":  "yahoo_direct",
            "_partial": False,
            **fd,
        }

    data = get_chart_data(ticker, "5d")
    meta = data.get("meta", {}) if data else {}
    return {
        "ticker":          ticker,
        "name":            meta.get("longName") or meta.get("shortName", ticker),
        "market":          "US",
        "sector":          "不明",
        "industry":        "不明",
        "price":           price or meta.get("regularMarketPrice", 0),
        "currency":        meta.get("currency", "USD"),
        "market_cap":      None,
        "per":             None,
        "pbr":             None,
        "roe":             None,
        "dividend_yield":  None,
        "payout_ratio":    None,
        "revenue_growth":  None,
        "earnings_growth": None,
        "debt_to_equity":  None,
        "current_ratio":   None,
        "52w_high":        meta.get("fiftyTwoWeekHigh"),
        "52w_low":         meta.get("fiftyTwoWeekLow"),
        "description":     "",
        "_source":         "yahoo_direct",
        "_partial":        True,
    }


def get_basic_info_direct(ticker: str) -> dict:
    return get_full_info_direct(ticker)
