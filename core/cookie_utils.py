import streamlit as st
import streamlit.components.v1 as components

COOKIE_NAME = "stock_session"
COOKIE_DAYS = 30
_MAX_AGE    = COOKIE_DAYS * 24 * 3600


def get_session_token() -> str:
    """WebSocketハンドシェイク時のCookieヘッダーからトークンを取得する。
    ブラウザ更新後の新しいリクエストで有効になる。"""
    try:
        raw = st.context.headers.get("Cookie", "")
        for part in raw.split(";"):
            name, _, val = part.strip().partition("=")
            if name == COOKIE_NAME:
                return val if val else None
    except Exception:
        pass
    return None


def set_session_cookie(token: str):
    """JavaScriptで親ウィンドウにセッションクッキーをセットする"""
    components.html(
        f"""<script>
        window.parent.document.cookie =
            "{COOKIE_NAME}={token}; max-age={_MAX_AGE}; path=/; SameSite=Lax";
        </script>""",
        height=0,
    )


def clear_session_cookie():
    """JavaScriptでセッションクッキーを削除する"""
    components.html(
        f"""<script>
        window.parent.document.cookie =
            "{COOKIE_NAME}=; max-age=0; path=/; SameSite=Lax";
        </script>""",
        height=0,
    )
