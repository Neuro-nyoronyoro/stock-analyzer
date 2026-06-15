import yfinance as yf
import pandas as pd
from typing import Optional
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin, LimiterSession
from requests import Session
import os

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "yfinance_cache")


class _CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    """キャッシュ＋レート制限付きHTTPセッション（yfinance公式推奨）"""


_session = _CachedLimiterSession(
    per_second=0.4,                                        # 2.5秒に1リクエスト
    backend=SQLiteCache(_CACHE_PATH, expire_after=3600),   # 1時間HTTPキャッシュ
    allowable_codes=[200],                                 # 成功レスポンスのみキャッシュ（429等はキャッシュしない）
    stale_if_error=False,                                  # エラー時に古いキャッシュを使わない
)


def _ticker(symbol: str) -> yf.Ticker:
    return yf.Ticker(symbol, session=_session)


def get_stock_info(ticker: str) -> dict:
    """銘柄の基本情報・財務データを取得する"""
    if ticker.endswith(".T"):
        # 日本株: J-Quantsをプライマリ（財務）+ yahoo_directで現在株価を補完
        from core.jquants import get_stock_info_jquants
        from core.yahoo_direct import get_current_price
        result = get_stock_info_jquants(ticker)
        if "error" not in result:
            current_price = get_current_price(ticker)
            if current_price:
                result["price"] = current_price
                # 現在株価でPER・PBR・配当利回りを再計算
                eps = result.get("_eps")
                bps = result.get("_bps")
                div_ann = result.get("_div_ann")
                if eps and eps > 0:
                    result["per"] = round(current_price / eps, 2)
                if bps and bps > 0:
                    result["pbr"] = round(current_price / bps, 2)
                if div_ann and current_price > 0:
                    result["dividend_yield"] = round(div_ann / current_price, 4)
            return result
        # J-Quants失敗時はyfinanceにフォールバック
        try:
            t = _ticker(ticker)
            info = t.info
            return {
                "ticker": ticker,
                "name": info.get("longName") or info.get("shortName", ticker),
                "market": "JP",
                "sector": info.get("sector", "不明"),
                "industry": info.get("industry", "不明"),
                "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
                "currency": "JPY",
                "market_cap": info.get("marketCap", 0),
                "per": info.get("trailingPE"),
                "pbr": info.get("priceToBook"),
                "roe": info.get("returnOnEquity"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "description": info.get("longBusinessSummary", ""),
                "_source": "yfinance",
            }
        except Exception as e:
            return {"ticker": ticker, "error": str(e)}
    else:
        # 米国株: yahoo_direct直接アクセス（crumb不要）→ yfinanceフォールバック
        from core.yahoo_direct import get_full_info_direct
        result = get_full_info_direct(ticker)
        if not result.get("_partial"):
            return result
        # yahoo_directで財務データが取れない場合はyfinanceを試みる
        try:
            t = _ticker(ticker)
            info = t.info
            return {
                "ticker": ticker,
                "name": info.get("longName") or info.get("shortName", ticker),
                "market": "US",
                "sector": info.get("sector", "不明"),
                "industry": info.get("industry", "不明"),
                "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
                "currency": info.get("currency", "USD"),
                "market_cap": info.get("marketCap", 0),
                "per": info.get("trailingPE"),
                "pbr": info.get("priceToBook"),
                "roe": info.get("returnOnEquity"),
                "dividend_yield": info.get("dividendYield"),
                "payout_ratio": info.get("payoutRatio"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "current_ratio": info.get("currentRatio"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
                "description": info.get("longBusinessSummary", ""),
                "_source": "yfinance",
            }
        except Exception:
            return result  # _partial=Trueのyahoo_direct結果を返す


def get_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """株価履歴を取得する（OHLCV）。yfinance失敗時は各種フォールバック"""
    try:
        t = _ticker(ticker)
        yf_period = "max" if period == "最大" else period
        df = t.history(period=yf_period)
        if df.empty:
            raise ValueError("empty dataframe")
        try:
            df.index = df.index.tz_localize(None)
        except TypeError:
            df.index = df.index.tz_convert(None)
        return df
    except Exception:
        if ticker.endswith(".T"):
            from core.jquants import get_price_history_jquants
            return get_price_history_jquants(ticker, period)
        else:
            from core.yahoo_direct import get_price_history_direct
            return get_price_history_direct(ticker, period)


def get_dividend_history(ticker: str) -> pd.DataFrame:
    """配当履歴を取得する"""
    try:
        t = _ticker(ticker)
        div = t.dividends
        if div.empty:
            return pd.DataFrame()
        df = div.reset_index()
        df.columns = ["date", "dividend"]
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        return df.sort_values("date", ascending=False)
    except Exception:
        return pd.DataFrame()


def get_financials(ticker: str) -> dict:
    """損益計算書・貸借対照表の主要指標を取得する"""
    try:
        t = _ticker(ticker)
        income = t.income_stmt
        balance = t.balance_sheet
        result = {}
        if not income.empty:
            if "Total Revenue" in income.index:
                result["revenue"] = income.loc["Total Revenue"].iloc[:4].to_dict()
            if "Net Income" in income.index:
                result["net_income"] = income.loc["Net Income"].iloc[:4].to_dict()
        if not balance.empty:
            if "Stockholders Equity" in balance.index:
                result["total_equity"] = balance.loc["Stockholders Equity"].iloc[:4].to_dict()
        return result
    except Exception:
        return {}


# ── 日本株リスト（約100銘柄）────────────────────────────────
MAJOR_JP = [
    # 自動車・輸送機器
    {"ticker": "7203.T", "name": "トヨタ自動車",       "sector": "自動車"},
    {"ticker": "7267.T", "name": "本田技研工業",       "sector": "自動車"},
    {"ticker": "7201.T", "name": "日産自動車",         "sector": "自動車"},
    {"ticker": "7269.T", "name": "スズキ",             "sector": "自動車"},
    {"ticker": "7270.T", "name": "SUBARU",             "sector": "自動車"},
    {"ticker": "7272.T", "name": "ヤマハ発動機",       "sector": "自動車"},
    {"ticker": "6902.T", "name": "デンソー",           "sector": "自動車部品"},
    {"ticker": "7259.T", "name": "アイシン",           "sector": "自動車部品"},
    # 電機・精密機器
    {"ticker": "6758.T", "name": "ソニーグループ",     "sector": "電機"},
    {"ticker": "6861.T", "name": "キーエンス",         "sector": "電機"},
    {"ticker": "8035.T", "name": "東京エレクトロン",   "sector": "電機"},
    {"ticker": "7974.T", "name": "任天堂",             "sector": "電機"},
    {"ticker": "6501.T", "name": "日立製作所",         "sector": "電機"},
    {"ticker": "6502.T", "name": "東芝",               "sector": "電機"},
    {"ticker": "6752.T", "name": "パナソニックHD",     "sector": "電機"},
    {"ticker": "6753.T", "name": "シャープ",           "sector": "電機"},
    {"ticker": "6701.T", "name": "NEC",                "sector": "電機"},
    {"ticker": "6702.T", "name": "富士通",             "sector": "電機"},
    {"ticker": "6971.T", "name": "京セラ",             "sector": "電機"},
    {"ticker": "6723.T", "name": "ルネサスエレクトロニクス", "sector": "電機"},
    {"ticker": "4543.T", "name": "テルモ",             "sector": "精密機器"},
    {"ticker": "7741.T", "name": "HOYA",               "sector": "精密機器"},
    {"ticker": "7832.T", "name": "バンダイナムコHD",   "sector": "電機"},
    # 機械
    {"ticker": "6367.T", "name": "ダイキン工業",       "sector": "機械"},
    {"ticker": "6954.T", "name": "ファナック",         "sector": "機械"},
    {"ticker": "6326.T", "name": "クボタ",             "sector": "機械"},
    {"ticker": "6273.T", "name": "SMC",                "sector": "機械"},
    {"ticker": "6146.T", "name": "ディスコ",           "sector": "機械"},
    {"ticker": "7733.T", "name": "オリンパス",         "sector": "機械"},
    # 情報通信
    {"ticker": "9984.T", "name": "ソフトバンクグループ","sector": "情報通信"},
    {"ticker": "9432.T", "name": "NTT",                "sector": "情報通信"},
    {"ticker": "9433.T", "name": "KDDI",               "sector": "情報通信"},
    {"ticker": "9434.T", "name": "ソフトバンク",       "sector": "情報通信"},
    {"ticker": "6098.T", "name": "リクルートHD",       "sector": "情報通信"},
    {"ticker": "4307.T", "name": "野村総合研究所",     "sector": "情報通信"},
    {"ticker": "9613.T", "name": "NTTデータグループ",  "sector": "情報通信"},
    {"ticker": "3659.T", "name": "ネクソン",           "sector": "情報通信"},
    {"ticker": "4689.T", "name": "LINEヤフー",         "sector": "情報通信"},
    # 銀行・金融
    {"ticker": "8306.T", "name": "三菱UFJフィナンシャルG","sector": "銀行"},
    {"ticker": "8316.T", "name": "三井住友FG",         "sector": "銀行"},
    {"ticker": "8411.T", "name": "みずほFG",           "sector": "銀行"},
    {"ticker": "8309.T", "name": "三井住友トラストHD", "sector": "銀行"},
    {"ticker": "7182.T", "name": "ゆうちょ銀行",       "sector": "銀行"},
    {"ticker": "8354.T", "name": "ふくおかFG",         "sector": "銀行"},
    # 保険
    {"ticker": "8766.T", "name": "東京海上HD",         "sector": "保険"},
    {"ticker": "8725.T", "name": "MS&ADインシュアランスG","sector": "保険"},
    {"ticker": "8750.T", "name": "第一生命HD",         "sector": "保険"},
    {"ticker": "8630.T", "name": "SOMPOホールディングス","sector": "保険"},
    # 証券・その他金融
    {"ticker": "8604.T", "name": "野村HD",             "sector": "証券"},
    {"ticker": "8601.T", "name": "大和証券グループ本社","sector": "証券"},
    # 卸売・商社
    {"ticker": "8058.T", "name": "三菱商事",           "sector": "卸売"},
    {"ticker": "8031.T", "name": "三井物産",           "sector": "卸売"},
    {"ticker": "8001.T", "name": "伊藤忠商事",         "sector": "卸売"},
    {"ticker": "8002.T", "name": "丸紅",               "sector": "卸売"},
    {"ticker": "8053.T", "name": "住友商事",           "sector": "卸売"},
    {"ticker": "8015.T", "name": "豊田通商",           "sector": "卸売"},
    # 医薬品
    {"ticker": "4502.T", "name": "武田薬品工業",       "sector": "医薬品"},
    {"ticker": "4519.T", "name": "中外製薬",           "sector": "医薬品"},
    {"ticker": "4568.T", "name": "第一三共",           "sector": "医薬品"},
    {"ticker": "4523.T", "name": "エーザイ",           "sector": "医薬品"},
    {"ticker": "4507.T", "name": "塩野義製薬",         "sector": "医薬品"},
    {"ticker": "4151.T", "name": "協和キリン",         "sector": "医薬品"},
    # 化学
    {"ticker": "4063.T", "name": "信越化学工業",       "sector": "化学"},
    {"ticker": "4188.T", "name": "三菱ケミカルG",      "sector": "化学"},
    {"ticker": "4183.T", "name": "三井化学",           "sector": "化学"},
    {"ticker": "4452.T", "name": "花王",               "sector": "化学"},
    {"ticker": "4901.T", "name": "富士フイルムHD",     "sector": "化学"},
    # 食品・飲料
    {"ticker": "2914.T", "name": "日本たばこ産業（JT）","sector": "食品"},
    {"ticker": "2503.T", "name": "キリンHD",           "sector": "食品"},
    {"ticker": "2502.T", "name": "アサヒグループHD",   "sector": "食品"},
    {"ticker": "2801.T", "name": "キッコーマン",       "sector": "食品"},
    {"ticker": "2802.T", "name": "味の素",             "sector": "食品"},
    {"ticker": "2269.T", "name": "明治HD",             "sector": "食品"},
    # 小売
    {"ticker": "9983.T", "name": "ファーストリテイリング","sector": "小売"},
    {"ticker": "8267.T", "name": "イオン",             "sector": "小売"},
    {"ticker": "3382.T", "name": "セブン&アイHD",      "sector": "小売"},
    {"ticker": "8233.T", "name": "高島屋",             "sector": "小売"},
    {"ticker": "9843.T", "name": "ニトリHD",           "sector": "小売"},
    # 不動産
    {"ticker": "8801.T", "name": "三井不動産",         "sector": "不動産"},
    {"ticker": "8802.T", "name": "三菱地所",           "sector": "不動産"},
    {"ticker": "8830.T", "name": "住友不動産",         "sector": "不動産"},
    # 建設
    {"ticker": "1925.T", "name": "大和ハウス工業",     "sector": "建設"},
    {"ticker": "1928.T", "name": "積水ハウス",         "sector": "建設"},
    {"ticker": "1801.T", "name": "大成建設",           "sector": "建設"},
    # 陸運・空運
    {"ticker": "9020.T", "name": "JR東日本",           "sector": "陸運"},
    {"ticker": "9022.T", "name": "JR東海",             "sector": "陸運"},
    {"ticker": "9001.T", "name": "東武鉄道",           "sector": "陸運"},
    {"ticker": "9064.T", "name": "ヤマトHD",           "sector": "陸運"},
    {"ticker": "9101.T", "name": "日本郵船",           "sector": "海運"},
    {"ticker": "9107.T", "name": "川崎汽船",           "sector": "海運"},
    # エネルギー・鉄鋼
    {"ticker": "5401.T", "name": "日本製鉄",           "sector": "鉄鋼"},
    {"ticker": "5411.T", "name": "JFEホールディングス","sector": "鉄鋼"},
    {"ticker": "5108.T", "name": "ブリヂストン",       "sector": "ゴム"},
    # サービス
    {"ticker": "4661.T", "name": "オリエンタルランド", "sector": "サービス"},
    {"ticker": "9602.T", "name": "東宝",               "sector": "サービス"},
    {"ticker": "2432.T", "name": "DeNA",               "sector": "サービス"},
]

# ── 米国株リスト（約80銘柄）────────────────────────────────
MAJOR_US = [
    # Technology
    {"ticker": "AAPL",  "name": "Apple",                   "sector": "Technology"},
    {"ticker": "MSFT",  "name": "Microsoft",               "sector": "Technology"},
    {"ticker": "GOOGL", "name": "Alphabet",                "sector": "Technology"},
    {"ticker": "NVDA",  "name": "NVIDIA",                  "sector": "Technology"},
    {"ticker": "META",  "name": "Meta Platforms",          "sector": "Technology"},
    {"ticker": "AVGO",  "name": "Broadcom",                "sector": "Technology"},
    {"ticker": "ORCL",  "name": "Oracle",                  "sector": "Technology"},
    {"ticker": "CRM",   "name": "Salesforce",              "sector": "Technology"},
    {"ticker": "ADBE",  "name": "Adobe",                   "sector": "Technology"},
    {"ticker": "AMD",   "name": "AMD",                     "sector": "Technology"},
    {"ticker": "INTC",  "name": "Intel",                   "sector": "Technology"},
    {"ticker": "QCOM",  "name": "Qualcomm",                "sector": "Technology"},
    {"ticker": "TXN",   "name": "Texas Instruments",       "sector": "Technology"},
    {"ticker": "IBM",   "name": "IBM",                     "sector": "Technology"},
    {"ticker": "NOW",   "name": "ServiceNow",              "sector": "Technology"},
    # Consumer Cyclical
    {"ticker": "AMZN",  "name": "Amazon",                  "sector": "Consumer Cyclical"},
    {"ticker": "TSLA",  "name": "Tesla",                   "sector": "Consumer Cyclical"},
    {"ticker": "HD",    "name": "Home Depot",              "sector": "Consumer Cyclical"},
    {"ticker": "MCD",   "name": "McDonald's",              "sector": "Consumer Cyclical"},
    {"ticker": "NKE",   "name": "Nike",                    "sector": "Consumer Cyclical"},
    {"ticker": "SBUX",  "name": "Starbucks",               "sector": "Consumer Cyclical"},
    {"ticker": "TGT",   "name": "Target",                  "sector": "Consumer Cyclical"},
    {"ticker": "LOW",   "name": "Lowe's",                  "sector": "Consumer Cyclical"},
    # Consumer Defensive
    {"ticker": "WMT",   "name": "Walmart",                 "sector": "Consumer Defensive"},
    {"ticker": "PG",    "name": "Procter & Gamble",        "sector": "Consumer Defensive"},
    {"ticker": "KO",    "name": "Coca-Cola",               "sector": "Consumer Defensive"},
    {"ticker": "PEP",   "name": "PepsiCo",                 "sector": "Consumer Defensive"},
    {"ticker": "COST",  "name": "Costco",                  "sector": "Consumer Defensive"},
    {"ticker": "PM",    "name": "Philip Morris",           "sector": "Consumer Defensive"},
    {"ticker": "MO",    "name": "Altria",                  "sector": "Consumer Defensive"},
    {"ticker": "CL",    "name": "Colgate-Palmolive",       "sector": "Consumer Defensive"},
    {"ticker": "KMB",   "name": "Kimberly-Clark",          "sector": "Consumer Defensive"},
    # Healthcare
    {"ticker": "JNJ",   "name": "Johnson & Johnson",       "sector": "Healthcare"},
    {"ticker": "UNH",   "name": "UnitedHealth Group",      "sector": "Healthcare"},
    {"ticker": "ABBV",  "name": "AbbVie",                  "sector": "Healthcare"},
    {"ticker": "MRK",   "name": "Merck",                   "sector": "Healthcare"},
    {"ticker": "LLY",   "name": "Eli Lilly",               "sector": "Healthcare"},
    {"ticker": "TMO",   "name": "Thermo Fisher",           "sector": "Healthcare"},
    {"ticker": "ABT",   "name": "Abbott Laboratories",     "sector": "Healthcare"},
    {"ticker": "BMY",   "name": "Bristol-Myers Squibb",    "sector": "Healthcare"},
    {"ticker": "PFE",   "name": "Pfizer",                  "sector": "Healthcare"},
    {"ticker": "AMGN",  "name": "Amgen",                   "sector": "Healthcare"},
    # Financial Services
    {"ticker": "JPM",   "name": "JPMorgan Chase",          "sector": "Financial Services"},
    {"ticker": "BAC",   "name": "Bank of America",         "sector": "Financial Services"},
    {"ticker": "WFC",   "name": "Wells Fargo",             "sector": "Financial Services"},
    {"ticker": "GS",    "name": "Goldman Sachs",           "sector": "Financial Services"},
    {"ticker": "MS",    "name": "Morgan Stanley",          "sector": "Financial Services"},
    {"ticker": "BLK",   "name": "BlackRock",               "sector": "Financial Services"},
    {"ticker": "V",     "name": "Visa",                    "sector": "Financial Services"},
    {"ticker": "MA",    "name": "Mastercard",              "sector": "Financial Services"},
    {"ticker": "AXP",   "name": "American Express",        "sector": "Financial Services"},
    {"ticker": "C",     "name": "Citigroup",               "sector": "Financial Services"},
    # Energy
    {"ticker": "XOM",   "name": "ExxonMobil",              "sector": "Energy"},
    {"ticker": "CVX",   "name": "Chevron",                 "sector": "Energy"},
    {"ticker": "COP",   "name": "ConocoPhillips",          "sector": "Energy"},
    {"ticker": "SLB",   "name": "Schlumberger",            "sector": "Energy"},
    # Communication Services
    {"ticker": "T",     "name": "AT&T",                    "sector": "Communication Services"},
    {"ticker": "VZ",    "name": "Verizon",                 "sector": "Communication Services"},
    {"ticker": "NFLX",  "name": "Netflix",                 "sector": "Communication Services"},
    {"ticker": "DIS",   "name": "Walt Disney",             "sector": "Communication Services"},
    {"ticker": "CMCSA", "name": "Comcast",                 "sector": "Communication Services"},
    # Industrials
    {"ticker": "HON",   "name": "Honeywell",               "sector": "Industrials"},
    {"ticker": "UPS",   "name": "UPS",                     "sector": "Industrials"},
    {"ticker": "CAT",   "name": "Caterpillar",             "sector": "Industrials"},
    {"ticker": "BA",    "name": "Boeing",                  "sector": "Industrials"},
    {"ticker": "GE",    "name": "GE Aerospace",            "sector": "Industrials"},
    {"ticker": "MMM",   "name": "3M",                      "sector": "Industrials"},
    {"ticker": "RTX",   "name": "RTX (Raytheon)",          "sector": "Industrials"},
    {"ticker": "LMT",   "name": "Lockheed Martin",         "sector": "Industrials"},
    # Utilities
    {"ticker": "NEE",   "name": "NextEra Energy",          "sector": "Utilities"},
    {"ticker": "DUK",   "name": "Duke Energy",             "sector": "Utilities"},
    {"ticker": "SO",    "name": "Southern Company",        "sector": "Utilities"},
    # Real Estate
    {"ticker": "PLD",   "name": "Prologis",                "sector": "Real Estate"},
    {"ticker": "AMT",   "name": "American Tower",          "sector": "Real Estate"},
    {"ticker": "O",     "name": "Realty Income",           "sector": "Real Estate"},
    # Materials
    {"ticker": "LIN",   "name": "Linde",                   "sector": "Materials"},
    {"ticker": "APD",   "name": "Air Products",            "sector": "Materials"},
    {"ticker": "NEM",   "name": "Newmont",                 "sector": "Materials"},
]


def search_tickers(keyword: str, market: str = "both") -> list[dict]:
    """銘柄を検索する"""
    kw = keyword.lower()
    results = []
    if market in ("JP", "both"):
        results += [s for s in MAJOR_JP if kw in s["name"].lower() or kw in s["ticker"].lower() or kw in s["sector"].lower()]
    if market in ("US", "both"):
        results += [s for s in MAJOR_US if kw in s["name"].lower() or kw in s["ticker"].lower() or kw in s["sector"].lower()]
    return results
