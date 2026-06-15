import streamlit as st
from streamlit_cookies_controller import CookieController
from core.cookie_utils import COOKIE_NAME
from db.database import get_user_by_session_token, delete_user_session


def require_login() -> dict:
    """ログインチェック。未ログイン時はCookieからの自動ログインを試みる。
    CookieController はここで生成するため、未ログイン状態でもコンポーネントが
    レンダリングされ、ブラウザのクッキーを受信→リランで自動ログインが機能する。"""
    controller = CookieController(key="_sc_ctrl")

    if not st.session_state.get("user_id"):
        token = controller.get(COOKIE_NAME)
        if token:
            user = get_user_by_session_token(token)
            if user:
                st.session_state["user_id"]        = user["id"]
                st.session_state["user_email"]     = user["email"]
                st.session_state["user_name"]      = user["display_name"]
                st.session_state["is_admin"]       = user["is_admin"]
                st.session_state["_session_token"] = token

    if not st.session_state.get("user_id"):
        st.warning("ログインが必要です。")
        st.markdown("[← ログインページへ](/) ")
        st.stop()

    _render_sidebar(controller)
    return _user_dict()


def _render_sidebar(controller: CookieController):
    with st.sidebar:
        st.caption(f"👤 {st.session_state['user_name']}")
        if st.button("ログアウト", key="__logout__", use_container_width=True):
            token = st.session_state.get("_session_token")
            if token:
                try:
                    delete_user_session(token)
                except Exception:
                    pass
            try:
                controller.remove(COOKIE_NAME)
            except Exception:
                pass
            st.session_state.clear()
            st.rerun()


def _user_dict() -> dict:
    return {
        "id":           st.session_state["user_id"],
        "email":        st.session_state["user_email"],
        "display_name": st.session_state["user_name"],
        "is_admin":     st.session_state.get("is_admin", False),
    }


def require_admin() -> dict:
    """管理者専用ページのチェック。管理者でない場合は stop する。"""
    user = require_login()
    if not user["is_admin"]:
        st.error("管理者専用ページです。")
        st.stop()
    return user
