import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from streamlit_cookies_controller import CookieController
from db.database import init_db, create_user_session, get_user_by_session_token, delete_user_session
from core.cookie_utils import COOKIE_NAME, COOKIE_DAYS
from core.yahoo_direct import get_price_history_direct

init_db()

st.set_page_config(
    page_title="株式投資ダッシュボード",
    page_icon="📈",
    layout="wide",
)

# ── クエリパラメータ処理（メール認証・パスワードリセット） ──────────
params = st.query_params

if "verify" in params:
    from core.auth import verify_email
    if verify_email(params["verify"]):
        st.query_params.clear()
        st.success("✅ メールアドレスの確認が完了しました。管理者の承認後にログインできます。")
        st.info("最初に登録したユーザーは管理者として即座にログインできます。")
    else:
        st.error("認証リンクが無効または期限切れです。再度登録をお試しください。")
    st.stop()

if "reset" in params:
    from core.auth import reset_password
    token = params["reset"]
    st.title("🔑 パスワード再設定")
    with st.form("reset_form"):
        new_pw  = st.text_input("新しいパスワード（8文字以上）", type="password")
        confirm = st.text_input("確認（再入力）", type="password")
        if st.form_submit_button("パスワードを変更する", type="primary"):
            if len(new_pw) < 8:
                st.error("パスワードは8文字以上で設定してください")
            elif new_pw != confirm:
                st.error("パスワードが一致しません")
            elif reset_password(token, new_pw):
                st.query_params.clear()
                st.success("パスワードを変更しました。ログインしてください。")
                st.rerun()
            else:
                st.error("リンクが無効または期限切れです（有効期限1時間）")
    st.stop()

# ── クッキーコントローラー（ログインチェックより前に生成）──────────
_cookie_ctrl = CookieController(key="_sc_ctrl")

# ログイン直後のクッキー書き込み（_pending_cookie フラグ経由）
if "_pending_cookie" in st.session_state:
    _pending = st.session_state.pop("_pending_cookie")
    try:
        _cookie_ctrl.set(COOKIE_NAME, _pending)  # max_age なし（セッションクッキー）
    except Exception as _e:
        st.sidebar.error(f"[DEBUG] cookie set error: {_e}")

# ── クッキーからの自動ログイン ────────────────────────────────────
_token = _cookie_ctrl.get(COOKIE_NAME)

# DEBUG: サイドバーにクッキー状態を表示（確認後に削除）
with st.sidebar:
    with st.expander("🔧 Cookie Debug（確認後に削除）", expanded=True):
        st.write("controller.get():", _token)
        st.write("Cookie header:", st.context.headers.get("Cookie", "(empty)"))
        st.write("session user_id:", st.session_state.get("user_id"))

if not st.session_state.get("user_id"):
    if _token:
        _u = get_user_by_session_token(_token)
        if _u:
            st.session_state["user_id"]        = _u["id"]
            st.session_state["user_email"]     = _u["email"]
            st.session_state["user_name"]      = _u["display_name"]
            st.session_state["is_admin"]       = _u["is_admin"]
            st.session_state["_session_token"] = _token

# ── 未ログイン：ログイン / 登録 / パスワード忘れ ──────────────────
if not st.session_state.get("user_id"):
    st.title("📈 株式投資ダッシュボード")
    tab1, tab2, tab3 = st.tabs(["🔑 ログイン", "📝 新規登録", "🔒 パスワードを忘れた方"])

    with tab1:
        with st.form("login_form"):
            email    = st.text_input("メールアドレス")
            password = st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン", type="primary"):
                from core.auth import login
                user, err = login(email, password)
                if user:
                    token = create_user_session(user["id"])
                    st.session_state["user_id"]        = user["id"]
                    st.session_state["user_email"]     = user["email"]
                    st.session_state["user_name"]      = user["display_name"]
                    st.session_state["is_admin"]       = user["is_admin"]
                    st.session_state["_session_token"] = token
                    # クッキーは次のレンダリングで書き込む（タイミング問題回避）
                    st.session_state["_pending_cookie"] = token
                    st.rerun()
                else:
                    st.error(err)

    with tab2:
        st.caption("登録後、確認メールが届きます。リンクをクリックして認証を完了してください。")
        with st.form("register_form"):
            name      = st.text_input("表示名")
            reg_email = st.text_input("メールアドレス")
            reg_pw    = st.text_input("パスワード（8文字以上）", type="password")
            reg_pw2   = st.text_input("パスワード（確認）", type="password")
            if st.form_submit_button("アカウント作成", type="primary"):
                if not name or not reg_email or not reg_pw:
                    st.error("全ての項目を入力してください")
                elif len(reg_pw) < 8:
                    st.error("パスワードは8文字以上で設定してください")
                elif reg_pw != reg_pw2:
                    st.error("パスワードが一致しません")
                else:
                    from core.auth import register_user
                    from core.email_sender import send_verification_email
                    user, token = register_user(reg_email, reg_pw, name)
                    if user:
                        send_verification_email(reg_email, name, token)
                        st.success("確認メールを送信しました。メールのリンクをクリックして認証を完了してください。")
                    else:
                        st.error(token)

    with tab3:
        with st.form("forgot_form"):
            forgot_email = st.text_input("登録済みメールアドレス")
            if st.form_submit_button("再設定メールを送信"):
                from core.auth import create_reset_token
                from core.email_sender import send_reset_email
                user_info, token = create_reset_token(forgot_email)
                if user_info and token:
                    send_reset_email(user_info["email"], user_info["display_name"], token)
                st.success("メールアドレスが登録されている場合、再設定メールを送信しました。")
    st.stop()

# ── ログイン済み：サイドバーにユーザー情報 ────────────────────────
with st.sidebar:
    st.caption(f"👤 {st.session_state['user_name']}")
    st.caption(f"📧 {st.session_state['user_email']}")
    if st.button("ログアウト", use_container_width=True, key="main_logout"):
        _t = st.session_state.get("_session_token")
        if _t:
            try:
                delete_user_session(_t)
            except Exception:
                pass
        try:
            _cookie_ctrl.remove(COOKIE_NAME)
        except Exception:
            pass
        st.session_state.clear()
        st.rerun()

# ── ダッシュボード ────────────────────────────────────────────────
st.title("📈 株式投資ダッシュボード")

_RATE_LIMIT_CACHE_KEY = "market_rate_limited"
is_rate_limited = st.session_state.get(_RATE_LIMIT_CACHE_KEY, False)

if not is_rate_limited:
    st_autorefresh(interval=5 * 60 * 1000, key="market_autorefresh")
    st.caption(f"最終更新: {datetime.now().strftime('%H:%M:%S')}　｜　5分ごとに自動更新")
else:
    st.caption(f"最終更新: {datetime.now().strftime('%H:%M:%S')}　｜　自動更新停止中（レート制限）")

st.subheader("市場概況")

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_market_overview():
    indices = {"日経平均": "^N225", "NYダウ": "^DJI", "NASDAQ": "^IXIC", "USD/JPY": "JPY=X"}
    result = {}
    for name, ticker in indices.items():
        try:
            df = get_price_history_direct(ticker, "5d")
            if len(df) >= 2:
                prev  = float(df["Close"].iloc[-2])
                close = float(df["Close"].iloc[-1])
                chg   = close - prev
                pct   = chg / prev * 100
                result[name] = {"price": close, "change": chg, "pct": pct}
            else:
                result[name] = None
        except Exception:
            result[name] = None
    return result, False

indices_labels = ["日経平均", "NYダウ", "NASDAQ", "USD/JPY"]
if is_rate_limited:
    st.warning("⚠️ yfinanceのレート制限中です。市場データの自動取得を停止しています。")
    cols = st.columns(4)
    for col, name in zip(cols, indices_labels):
        with col:
            st.metric(label=name, value="制限中")
else:
    with st.spinner("市場データを取得中..."):
        overview, rate_limited = fetch_market_overview()
    if rate_limited:
        st.session_state[_RATE_LIMIT_CACHE_KEY] = True
        fetch_market_overview.clear()
        st.rerun()
    cols = st.columns(4)
    for i, col in enumerate(cols):
        name = indices_labels[i]
        data = overview.get(name)
        with col:
            if data:
                sign = "+" if data["change"] >= 0 else ""
                st.metric(label=name, value=f"{data['price']:,.2f}",
                          delta=f"{sign}{data['change']:,.2f} ({sign}{data['pct']:.2f}%)")
            else:
                st.metric(label=name, value="—")

if is_rate_limited:
    if st.button("🔄 レート制限を解除して再試行"):
        st.session_state.pop(_RATE_LIMIT_CACHE_KEY, None)
        fetch_market_overview.clear()
        st.rerun()

st.divider()

user_id = st.session_state["user_id"]
with st.expander("💼 ポートフォリオ概要 / ⭐ ウォッチリスト　―　クリックして表示", expanded=False):
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("ポートフォリオ概要")
        from db.database import get_session, Portfolio
        session = get_session()
        holdings = session.query(Portfolio).filter_by(user_id=user_id).all()
        session.close()
        if not holdings:
            st.info("保有銘柄が登録されていません。「ポートフォリオ」ページから登録してください。")
        else:
            total_cost = sum(h.shares * h.avg_cost for h in holdings)
            st.metric("登録銘柄数", f"{len(holdings)} 銘柄")
            st.metric("投資総額（取得単価ベース）", f"¥{total_cost:,.0f}")
    with col2:
        st.subheader("ウォッチリスト（直近5件）")
        from db.database import Watchlist
        session = get_session()
        watches = session.query(Watchlist).filter_by(user_id=user_id).order_by(Watchlist.added_at.desc()).limit(5).all()
        session.close()
        if not watches:
            st.info("ウォッチリストが空です。「銘柄詳細」ページから追加できます。")
        else:
            for w in watches:
                st.write(f"・ **{w.name}**（{w.ticker}）")

st.divider()
st.subheader("使い方")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.info("**🔍 スクリーニング**\n\n条件を指定して投資候補銘柄を絞り込む")
with c2:
    st.info("**📊 銘柄詳細**\n\nチャート・財務・AIレポートを確認する")
with c3:
    st.info("**💼 ポートフォリオ**\n\n保有銘柄と損益を管理する")
with c4:
    st.info("**📅 配当カレンダー**\n\n配当の権利確定日・支払日を確認する")
