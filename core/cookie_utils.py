import streamlit as st

COOKIE_NAME = "stock_session"
COOKIE_DAYS = 30


def get_session_token() -> str:
    """WebSocketハンドシェイク時のCookieヘッダーからトークンを取得する。
    ページ更新後の新しいリクエストで有効になる。"""
    try:
        raw = st.context.headers.get("Cookie", "")
        for part in raw.split(";"):
            name, _, val = part.strip().partition("=")
            if name.strip() == COOKIE_NAME:
                return val.strip() if val.strip() else None
    except Exception:
        pass
    return None
