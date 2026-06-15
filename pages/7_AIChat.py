import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from core.ai_chat import build_context, chat_response
from core.fetcher import get_stock_info
from core.yahoo_direct import get_price_history_direct
from db.database import get_session, Portfolio, Watchlist, ChatSession, ChatMessage

st.set_page_config(page_title="AIチャット", page_icon="🤖", layout="wide")

from core.auth_check import require_login
user = require_login()
user_id = user["id"]

st.title("🤖 AI投資アドバイザー")
st.caption("ポートフォリオ・ウォッチリストの情報を参照しながら投資に関する質問に答えます。")

MAX_MESSAGES = 20
MAX_SESSIONS = 10

# アクティブセッションIDは session_state で管理（ユーザー別・ページ更新でも保持）
SESSION_KEY = f"chat_session_id_{user_id}"

# ── DB操作ヘルパー ────────────────────────────────────────────
def db_get_all_sessions():
    s = get_session()
    rows = s.query(ChatSession).filter_by(user_id=user_id).order_by(ChatSession.created_at.desc()).all()
    result = [{"id": r.id, "created_at": r.created_at} for r in rows]
    s.close()
    return result

def db_get_messages(session_id: int):
    s = get_session()
    rows = s.query(ChatMessage).filter_by(session_id=session_id).order_by(ChatMessage.created_at).all()
    result = [{"role": r.role, "content": r.content} for r in rows]
    s.close()
    return result

def db_session_title(session_id: int) -> str:
    s = get_session()
    first = (s.query(ChatMessage)
               .filter_by(session_id=session_id, role="user")
               .order_by(ChatMessage.created_at)
               .first())
    s.close()
    if not first:
        return "新しいチャット"
    title = first.content
    return (title[:22] + "…") if len(title) > 22 else title

def db_create_session() -> int:
    s = get_session()
    sess = ChatSession(user_id=user_id)
    s.add(sess)
    s.commit()
    new_id = sess.id
    s.close()
    all_sessions = db_get_all_sessions()
    if len(all_sessions) > MAX_SESSIONS:
        s = get_session()
        for old in all_sessions[MAX_SESSIONS:]:
            s.query(ChatMessage).filter_by(session_id=old["id"]).delete()
            s.query(ChatSession).filter_by(id=old["id"]).delete()
        s.commit()
        s.close()
    return new_id

def db_delete_session(session_id: int):
    s = get_session()
    s.query(ChatMessage).filter_by(session_id=session_id).delete()
    s.query(ChatSession).filter_by(id=session_id).delete()
    s.commit()
    s.close()

def db_save_message(session_id: int, role: str, content: str):
    s = get_session()
    s.add(ChatMessage(session_id=session_id, role=role, content=content))
    s.commit()
    msgs = s.query(ChatMessage).filter_by(session_id=session_id).order_by(ChatMessage.created_at).all()
    if len(msgs) > MAX_MESSAGES:
        for m in msgs[:-MAX_MESSAGES]:
            s.delete(m)
        s.commit()
    s.close()

# ── アクティブセッションの初期化 ─────────────────────────────
all_sessions = db_get_all_sessions()

if st.session_state.get(SESSION_KEY) is None or not any(s["id"] == st.session_state[SESSION_KEY] for s in all_sessions):
    if all_sessions:
        st.session_state[SESSION_KEY] = all_sessions[0]["id"]
    else:
        st.session_state[SESSION_KEY] = db_create_session()
        all_sessions = db_get_all_sessions()

# ── ポートフォリオコンテキスト取得（ユーザー別5分キャッシュ） ──
@st.cache_data(ttl=300, show_spinner=False)
def load_portfolio_context(uid: int):
    session = get_session()
    holdings = session.query(Portfolio).filter_by(user_id=uid).all()
    watchlist = session.query(Watchlist).filter_by(user_id=uid).all()
    session.close()

    holdings_data = []
    for h in holdings:
        info       = get_stock_info(h.ticker)
        auto_price = info.get("price") if "error" not in info else None
        price      = auto_price if auto_price else h.manual_price
        cost       = h.shares * h.avg_cost
        value      = h.shares * price if price else None
        gain       = (value - cost) if value is not None else None
        pct        = (gain / cost * 100) if (gain is not None and cost > 0) else None
        holdings_data.append({
            "name":     h.name,
            "ticker":   h.ticker,
            "shares":   h.shares,
            "avg_cost": h.avg_cost,
            "price":    f"{price:,.0f}円" if price else "取得不可",
            "value":    f"{value:,.0f}円" if value else "—",
            "gain":     gain,
            "pct":      pct,
        })

    watchlist_data = []
    for w in watchlist:
        info  = get_stock_info(w.ticker)
        price = info.get("price") if "error" not in info else None
        watchlist_data.append({
            "name":   w.name,
            "ticker": w.ticker,
            "price":  f"{price:,.0f}円" if price else None,
        })

    market_data = {}
    for name, ticker in [("日経平均", "^N225"), ("NYダウ", "^DJI"), ("USD/JPY", "JPY=X")]:
        try:
            df = get_price_history_direct(ticker, "5d")
            if len(df) >= 2:
                price = float(df["Close"].iloc[-1])
                pct   = (price - float(df["Close"].iloc[-2])) / float(df["Close"].iloc[-2]) * 100
                market_data[name] = {"price": price, "pct": pct}
        except Exception:
            pass

    return holdings_data, watchlist_data, market_data


with st.spinner("ポートフォリオ情報を取得中..."):
    holdings_data, watchlist_data, market_data = load_portfolio_context(user_id)

context = build_context(holdings_data, watchlist_data, market_data)

# ── サイドバー ────────────────────────────────────────────────
with st.sidebar:
    if st.button("➕ 新しいチャットを始める", type="primary", use_container_width=True):
        st.session_state[SESSION_KEY] = db_create_session()
        st.rerun()

    st.divider()
    st.caption("チャット履歴")
    all_sessions = db_get_all_sessions()
    for sess in all_sessions:
        title     = db_session_title(sess["id"])
        is_active = sess["id"] == st.session_state[SESSION_KEY]
        label     = f"▶ {title}" if is_active else title
        if st.button(label, key=f"sess_{sess['id']}", use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state[SESSION_KEY] = sess["id"]
            st.rerun()

    st.divider()
    st.caption("質問の例")
    examples = [
        "今のポートフォリオで最もリスクが高い点は？",
        "日経が55,000円まで下がったらどう動く？",
        "ポートフォリオの配当収入見込みを教えて",
        "ウォッチリストで注目すべき銘柄は？",
        "来年のNISA枠240万円どう使う？",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=f"ex_{ex[:8]}"):
            st.session_state["pending_example"] = ex

    st.divider()
    st.caption(f"保有銘柄: {len(holdings_data)}件　ウォッチリスト: {len(watchlist_data)}件")
    current_msgs = db_get_messages(st.session_state[SESSION_KEY])
    st.caption(f"現在の会話: {len(current_msgs)} / {MAX_MESSAGES} 件")

# ── メインエリア ──────────────────────────────────────────────
current_msgs = db_get_messages(st.session_state[SESSION_KEY])

if not current_msgs:
    st.info("質問を入力するか、左サイドバーの例を選んでください。")

for msg in current_msgs:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── 例文ボタンからの入力処理 ──────────────────────────────────
pending = st.session_state.pop("pending_example", None)
if pending:
    db_save_message(st.session_state[SESSION_KEY], "user", pending)
    with st.chat_message("user"):
        st.markdown(pending)
    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            msgs_for_api = db_get_messages(st.session_state[SESSION_KEY])
            reply = chat_response(msgs_for_api, context)
        st.markdown(reply)
    db_save_message(st.session_state[SESSION_KEY], "assistant", reply)
    st.rerun()

# ── 削除ボタン（メインエリア右下） ──────────────────────────────
if current_msgs:
    _, del_col = st.columns([5, 1])
    with del_col:
        if st.button("🗑 このチャット履歴を消す", type="secondary", use_container_width=True):
            del_id = st.session_state[SESSION_KEY]
            db_delete_session(del_id)
            remaining = db_get_all_sessions()
            if remaining:
                st.session_state[SESSION_KEY] = remaining[0]["id"]
            else:
                st.session_state[SESSION_KEY] = db_create_session()
            st.rerun()

# ── チャット入力 ──────────────────────────────────────────────
if prompt := st.chat_input("投資について何でも聞いてください..."):
    db_save_message(st.session_state[SESSION_KEY], "user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            msgs_for_api = db_get_messages(st.session_state[SESSION_KEY])
            reply = chat_response(msgs_for_api, context)
        st.markdown(reply)
    db_save_message(st.session_state[SESSION_KEY], "assistant", reply)
