import streamlit as st


def require_login() -> dict:
    """ログインチェック。未ログイン時はメッセージを表示して stop する。
    ログイン済みの場合はサイドバーにユーザー情報とログアウトボタンを追加し、user dict を返す。"""
    if not st.session_state.get("user_id"):
        st.warning("ログインが必要です。")
        st.markdown("[← ログインページへ](/) ")
        st.stop()

    with st.sidebar:
        st.caption(f"👤 {st.session_state['user_name']}")
        if st.button("ログアウト", key="__logout__", use_container_width=True):
            st.session_state.clear()
            st.rerun()

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
