import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from db.database import get_session, User

st.set_page_config(page_title="管理者パネル", page_icon="🔧", layout="wide")

from core.auth_check import require_admin
require_admin()

st.title("🔧 管理者パネル")

session = get_session()
users = session.query(User).order_by(User.created_at).all()
session.close()

# ── 承認待ちユーザー ──────────────────────────────────────────
pending = [u for u in users if u.is_verified and not u.is_approved]

st.subheader(f"承認待ちユーザー（{len(pending)} 件）")
if not pending:
    st.info("承認待ちのユーザーはいません。")
else:
    for u in pending:
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"**{u.display_name}**　{u.email}　登録日: {str(u.created_at)[:10]}")
        with col2:
            if st.button("✅ 承認", key=f"approve_{u.id}", type="primary"):
                s = get_session()
                obj = s.query(User).filter_by(id=u.id).first()
                if obj:
                    obj.is_approved = True
                    s.commit()
                s.close()
                st.success(f"{u.display_name} を承認しました")
                st.rerun()
        with col3:
            if st.button("🗑 拒否・削除", key=f"reject_{u.id}", type="secondary"):
                s = get_session()
                obj = s.query(User).filter_by(id=u.id).first()
                if obj:
                    s.delete(obj)
                    s.commit()
                s.close()
                st.warning(f"{u.display_name} を削除しました")
                st.rerun()

st.divider()

# ── 全ユーザー一覧 ─────────────────────────────────────────────
st.subheader(f"全ユーザー（{len(users)} 件）")

for u in users:
    status = []
    if u.is_admin:     status.append("👑 管理者")
    if u.is_verified:  status.append("✅ 認証済")
    if u.is_approved:  status.append("🟢 承認済")
    if not u.is_verified: status.append("⏳ 認証待ち")
    if u.is_verified and not u.is_approved: status.append("🔴 未承認")

    col1, col2 = st.columns([4, 1])
    with col1:
        st.write(f"**{u.display_name}**　{u.email}　{'　'.join(status)}　登録: {str(u.created_at)[:10]}")
    with col2:
        if not u.is_admin:
            if st.button("削除", key=f"del_user_{u.id}", type="secondary"):
                s = get_session()
                obj = s.query(User).filter_by(id=u.id).first()
                if obj:
                    s.delete(obj)
                    s.commit()
                s.close()
                st.warning(f"{u.display_name} を削除しました")
                st.rerun()
        else:
            st.caption("（管理者）")
