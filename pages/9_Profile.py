import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

st.set_page_config(page_title="アカウント設定", page_icon="⚙️", layout="wide")

from core.auth_check import require_login
user = require_login()

st.title("⚙️ アカウント設定")

# ── プロフィール編集 ──────────────────────────────────────────
st.subheader("プロフィール編集")
with st.form("profile_form"):
    new_name  = st.text_input("表示名", value=user["display_name"])
    new_email = st.text_input("メールアドレス", value=user["email"])
    if st.form_submit_button("更新する", type="primary"):
        from core.auth import update_profile
        ok, err = update_profile(user["id"], display_name=new_name, email=new_email)
        if ok:
            st.session_state["user_name"]  = new_name
            st.session_state["user_email"] = new_email
            st.success("プロフィールを更新しました")
            st.rerun()
        else:
            st.error(err)

st.divider()

# ── パスワード変更 ─────────────────────────────────────────────
st.subheader("パスワード変更")
with st.form("password_form"):
    current_pw = st.text_input("現在のパスワード", type="password")
    new_pw     = st.text_input("新しいパスワード（8文字以上）", type="password")
    confirm_pw = st.text_input("新しいパスワード（確認）", type="password")
    if st.form_submit_button("パスワードを変更する"):
        if len(new_pw) < 8:
            st.error("パスワードは8文字以上で設定してください")
        elif new_pw != confirm_pw:
            st.error("新しいパスワードが一致しません")
        else:
            from core.auth import change_password
            ok, err = change_password(user["id"], current_pw, new_pw)
            if ok:
                st.success("パスワードを変更しました")
            else:
                st.error(err)

st.divider()

# ── アカウント削除 ─────────────────────────────────────────────
st.subheader("アカウント削除")
st.warning("アカウントを削除すると、ポートフォリオ・ウォッチリスト・アラート・チャット履歴がすべて削除されます。この操作は元に戻せません。")

if user["is_admin"]:
    st.error("管理者アカウントは削除できません。")
    st.stop()

with st.expander("アカウントを削除する"):
    confirm_text = st.text_input('確認のため「削除する」と入力してください')
    if st.button("アカウントを完全に削除する", type="secondary"):
        if confirm_text != "削除する":
            st.error('「削除する」と入力してください')
        else:
            from db.database import get_session, User, Portfolio, Watchlist, PriceAlert, ChatSession, ChatMessage
            uid = user["id"]
            s = get_session()
            # 関連データをすべて削除
            sessions = s.query(ChatSession).filter_by(user_id=uid).all()
            for sess in sessions:
                s.query(ChatMessage).filter_by(session_id=sess.id).delete()
            s.query(ChatSession).filter_by(user_id=uid).delete()
            s.query(Portfolio).filter_by(user_id=uid).delete()
            s.query(Watchlist).filter_by(user_id=uid).delete()
            s.query(PriceAlert).filter_by(user_id=uid).delete()
            s.query(User).filter_by(id=uid).delete()
            s.commit()
            s.close()
            st.session_state.clear()
            st.rerun()
