import pandas as pd
import ta


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """株価DataFrameにテクニカル指標を追加する"""
    if df.empty or len(df) < 20:
        return df

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    vol   = df["Volume"]

    df = df.copy()
    df["MA25"]  = ta.trend.sma_indicator(close, window=25)
    df["MA75"]  = ta.trend.sma_indicator(close, window=75)
    df["MA200"] = ta.trend.sma_indicator(close, window=200)
    df["EMA25"] = ta.trend.ema_indicator(close, window=25)

    df["RSI"] = ta.momentum.rsi(close, window=14)

    macd = ta.trend.MACD(close)
    df["MACD"]        = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["MACD_diff"]   = macd.macd_diff()

    bb = ta.volatility.BollingerBands(close, window=20)
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_mid"]   = bb.bollinger_mavg()
    df["BB_lower"] = bb.bollinger_lband()

    df["ATR"] = ta.volatility.average_true_range(high, low, close, window=14)

    return df


def get_signal(df: pd.DataFrame) -> dict:
    """最新データから売買シグナルを判定する"""
    if df.empty:
        return {}

    last = df.iloc[-1]
    signals = {}

    # ゴールデンクロス・デッドクロス
    if pd.notna(last.get("MA25")) and pd.notna(last.get("MA75")):
        if last["MA25"] > last["MA75"]:
            signals["ma_cross"] = ("買い寄り", "MA25がMA75を上回っている（ゴールデンクロス状態）")
        else:
            signals["ma_cross"] = ("売り寄り", "MA25がMA75を下回っている（デッドクロス状態）")

    # RSI
    rsi = last.get("RSI")
    if pd.notna(rsi):
        if rsi <= 30:
            signals["rsi"] = ("買い寄り", f"RSI {rsi:.1f}：売られすぎゾーン")
        elif rsi >= 70:
            signals["rsi"] = ("売り寄り", f"RSI {rsi:.1f}：買われすぎゾーン")
        else:
            signals["rsi"] = ("中立", f"RSI {rsi:.1f}：中立ゾーン")

    # MACD
    macd_diff = last.get("MACD_diff")
    if pd.notna(macd_diff):
        if macd_diff > 0:
            signals["macd"] = ("買い寄り", "MACDがシグナルラインを上回っている")
        else:
            signals["macd"] = ("売り寄り", "MACDがシグナルラインを下回っている")

    # ボリンジャーバンド
    close = last.get("Close")
    bb_upper = last.get("BB_upper")
    bb_lower = last.get("BB_lower")
    if pd.notna(close) and pd.notna(bb_upper) and pd.notna(bb_lower):
        if close >= bb_upper:
            signals["bb"] = ("売り寄り", "株価がボリンジャーバンド上限に到達")
        elif close <= bb_lower:
            signals["bb"] = ("買い寄り", "株価がボリンジャーバンド下限に到達")
        else:
            signals["bb"] = ("中立", "株価がバンド内で推移中")

    return signals
