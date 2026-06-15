import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st

st.set_page_config(page_title="アカウント設定", page_icon="⚙️", layout="wide")

from core.auth_check import require_login
user = require_login()

st.title("⚙️ アカウント設定")

if st.session_state.pop("profile_saved", False):
    st.markdown("""
<style>
@keyframes _banner_fade {
    0%,65%{opacity:1} 100%{opacity:0;pointer-events:none}
}
._save_banner{
    position:fixed;top:3.5rem;left:50%;transform:translateX(-50%);
    background:#d4edda;color:#155724;padding:.6rem 1.8rem;
    border-radius:.5rem;border:1px solid #c3e6cb;z-index:9999;
    font-size:1rem;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.2);
    animation:_banner_fade 3s forwards;
}
</style>
<div class="_save_banner">✅ 設定を保存しました</div>
""", unsafe_allow_html=True)

# ── 投資プロフィール設定 ─────────────────────────────────────
from db.database import get_user_profile, save_user_profile

st.subheader("📊 投資プロフィール設定")
st.caption("スクリーニングのスコアリング重みとAIの分析傾向がこの設定に合わせて変わります。")


STYLE_PRESETS = {
    "dividend": {
        "label": "💰 配当重視",
        "desc":  "高配当・安定配当を優先。インカムゲイン重視。",
        "weights": {"dividend": 0.45, "financial": 0.30, "growth": 0.10, "value": 0.15},
    },
    "growth": {
        "label": "📈 成長重視",
        "desc":  "売上・利益成長率を優先。キャピタルゲイン重視。",
        "weights": {"dividend": 0.10, "financial": 0.25, "growth": 0.45, "value": 0.20},
    },
    "value": {
        "label": "🏷️ 割安重視",
        "desc":  "PER・PBRが低い割安銘柄を優先。",
        "weights": {"dividend": 0.15, "financial": 0.25, "growth": 0.25, "value": 0.35},
    },
    "balanced": {
        "label": "⚖️ バランス（デフォルト）",
        "desc":  "配当・成長・割安をバランスよく評価。",
        "weights": {"dividend": 0.30, "financial": 0.35, "growth": 0.20, "value": 0.15},
    },
    "custom": {
        "label": "🔧 カスタム",
        "desc":  "重みを自分で設定する。",
        "weights": None,
    },
}

profile = get_user_profile(user["id"])

if not profile["is_set"]:
    st.info("投資プロフィールが未設定です。設定するとスクリーニングとAIがあなたの投資スタイルに最適化されます。")

with st.form("invest_profile_form"):
    style_keys = list(STYLE_PRESETS.keys())
    cur_style  = profile["investment_style"] if profile["investment_style"] in style_keys else "balanced"

    style = st.radio(
        "投資スタイル",
        options=style_keys,
        format_func=lambda x: STYLE_PRESETS[x]["label"],
        index=style_keys.index(cur_style),
        horizontal=True,
    )
    st.caption(STYLE_PRESETS[style]["desc"])

    if style == "custom":
        st.markdown("**スコアリング重み（合計が1.0になるように設定）**")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            w_div = st.slider("配当", 0.0, 1.0, float(profile["weights"]["dividend"]), 0.05)
        with c2:
            w_fin = st.slider("財務健全性", 0.0, 1.0, float(profile["weights"]["financial"]), 0.05)
        with c3:
            w_gro = st.slider("成長性", 0.0, 1.0, float(profile["weights"]["growth"]), 0.05)
        with c4:
            w_val = st.slider("割安度", 0.0, 1.0, float(profile["weights"]["value"]), 0.05)
        total_w = w_div + w_fin + w_gro + w_val
        ok_msg = "✅" if abs(total_w - 1.0) < 0.011 else "⚠️ 合計を1.0に合わせてください"
        st.caption(f"合計: {total_w:.2f}　{ok_msg}")
        selected_weights = {"dividend": w_div, "financial": w_fin, "growth": w_gro, "value": w_val}
    else:
        pw = STYLE_PRESETS[style]["weights"]
        st.caption(
            f"重み → 配当: {pw['dividend']:.0%} / 財務健全性: {pw['financial']:.0%}"
            f" / 成長性: {pw['growth']:.0%} / 割安度: {pw['value']:.0%}"
        )
        selected_weights = pw

    risk = st.select_slider(
        "リスク許容度",
        options=["low", "medium", "high"],
        format_func=lambda x: {"low": "低（安定重視）", "medium": "中（標準）", "high": "高（積極的）"}[x],
        value=profile["risk_tolerance"],
    )

    horizon = st.select_slider(
        "投資期間",
        options=["short", "medium", "long"],
        format_func=lambda x: {"short": "短期（1年未満）", "medium": "中期（1〜5年）", "long": "長期（5年以上）"}[x],
        value=profile["time_horizon"],
    )

    memo = st.text_area(
        "補足メモ（任意）― AIへの追加指示として使われます",
        value=profile["investment_memo"],
        placeholder="例：NISAでの長期運用が目的。高配当ETFにも興味あり。",
        max_chars=200,
    )

    if st.form_submit_button("投資プロフィールを保存", type="primary"):
        if style == "custom" and abs(sum(selected_weights.values()) - 1.0) >= 0.011:
            st.error("重みの合計を1.0にしてください")
        else:
            save_user_profile(
                user_id=user["id"],
                investment_style=style,
                risk_tolerance=risk,
                time_horizon=horizon,
                weights=selected_weights,
                investment_memo=memo,
            )
            st.session_state["profile_saved"] = True
            st.rerun()

st.divider()

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
            st.session_state["profile_saved"] = True
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
                st.session_state["profile_saved"] = True
                st.rerun()
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
            from db.database import get_session, User, Portfolio, Watchlist, PriceAlert, ChatSession, ChatMessage, delete_all_user_sessions
            uid = user["id"]
            delete_all_user_sessions(uid)
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
