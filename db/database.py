from __future__ import annotations
from sqlalchemy import create_engine, Column, String, Float, Integer, Date, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timedelta
import os
import secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "stock_analyzer.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "user"
    id                  = Column(Integer, primary_key=True, autoincrement=True)
    email               = Column(String, nullable=False, unique=True)
    password_hash       = Column(String, nullable=False)
    display_name        = Column(String, nullable=False)
    is_verified         = Column(Boolean, default=False)
    is_approved         = Column(Boolean, default=False)
    is_admin            = Column(Boolean, default=False)
    verification_token  = Column(String, nullable=True)
    reset_token         = Column(String, nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)


class Portfolio(Base):
    __tablename__ = "portfolio"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, nullable=True)
    ticker        = Column(String, nullable=False)
    name          = Column(String)
    market        = Column(String)
    shares        = Column(Float)
    avg_cost      = Column(Float)
    manual_price  = Column(Float, nullable=True)
    purchase_date = Column(Date)
    memo          = Column(Text)


class Watchlist(Base):
    __tablename__ = "watchlist"
    id       = Column(Integer, primary_key=True, autoincrement=True)
    user_id  = Column(Integer, nullable=True)
    ticker   = Column(String, nullable=False)
    name     = Column(String)
    market   = Column(String)
    added_at = Column(DateTime, default=datetime.utcnow)
    memo     = Column(Text)


class ScoreCache(Base):
    __tablename__ = "score_cache"
    ticker           = Column(String, primary_key=True)
    total_score      = Column(Float)
    dividend_score   = Column(Float)
    financial_score  = Column(Float)
    growth_score     = Column(Float)
    value_score      = Column(Float)
    dividend_yield   = Column(Float)
    per              = Column(Float)
    roe              = Column(Float)
    updated_at       = Column(DateTime, default=datetime.utcnow)


class AIReport(Base):
    __tablename__ = "ai_report"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    ticker     = Column(String, nullable=False)
    report_text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class PriceAlert(Base):
    __tablename__ = "price_alert"
    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, nullable=True)
    ticker        = Column(String, nullable=False)
    name          = Column(String)
    alert_type    = Column(String, nullable=False)
    threshold     = Column(Float, nullable=False)
    active        = Column(Boolean, default=True)
    last_notified = Column(Date, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_session"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, nullable=False)
    role       = Column(String, nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    __tablename__ = "user_session"
    token      = Column(String, primary_key=True)
    user_id    = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profile"
    user_id          = Column(Integer, primary_key=True)
    investment_style = Column(String, default="balanced")  # dividend/growth/value/balanced/custom
    risk_tolerance   = Column(String, default="medium")    # low/medium/high
    time_horizon     = Column(String, default="long")      # short/medium/long
    weight_dividend  = Column(Float, default=0.30)
    weight_financial = Column(Float, default=0.35)
    weight_growth    = Column(Float, default=0.20)
    weight_value     = Column(Float, default=0.15)
    investment_memo  = Column(Text, default="")
    updated_at       = Column(DateTime, default=datetime.utcnow)


def _migrate():
    """既存テーブルへの user_id カラム追加・watchlist の unique 制約修正"""
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    with engine.connect() as conn:
        # portfolio / price_alert / chat_session: user_id を追加
        for table in ["portfolio", "price_alert", "chat_session"]:
            try:
                existing_cols = [c["name"] for c in inspector.get_columns(table)]
                if "user_id" not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER"))
                    conn.commit()
            except Exception:
                pass

        # watchlist: ticker の UNIQUE 制約を (user_id, ticker) に変更するためテーブル再作成
        try:
            existing_cols = [c["name"] for c in inspector.get_columns("watchlist")]
            if "user_id" not in existing_cols:
                conn.execute(text("""
                    CREATE TABLE watchlist_new (
                        id       INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id  INTEGER,
                        ticker   VARCHAR NOT NULL,
                        name     VARCHAR,
                        market   VARCHAR,
                        added_at DATETIME,
                        memo     TEXT
                    )
                """))
                conn.execute(text("""
                    INSERT INTO watchlist_new (id, ticker, name, market, added_at, memo)
                    SELECT id, ticker, name, market, added_at, memo FROM watchlist
                """))
                conn.execute(text("DROP TABLE watchlist"))
                conn.execute(text("ALTER TABLE watchlist_new RENAME TO watchlist"))
                conn.commit()
        except Exception:
            pass


def init_db():
    Base.metadata.create_all(engine)
    _migrate()


def get_session():
    return SessionLocal()


def get_user_profile(user_id: int) -> dict:
    """ユーザーの投資プロフィールを返す。未設定の場合は config.py のデフォルト重みを使う。"""
    s = get_session()
    try:
        p = s.query(UserProfile).filter_by(user_id=user_id).first()
        if not p:
            return {
                "investment_style": "balanced",
                "risk_tolerance":   "medium",
                "time_horizon":     "long",
                "weights": {"dividend": 0.30, "financial": 0.35, "growth": 0.20, "value": 0.15},
                "investment_memo": "",
                "is_set": False,
            }
        return {
            "investment_style": p.investment_style,
            "risk_tolerance":   p.risk_tolerance,
            "time_horizon":     p.time_horizon,
            "weights": {
                "dividend":  p.weight_dividend,
                "financial": p.weight_financial,
                "growth":    p.weight_growth,
                "value":     p.weight_value,
            },
            "investment_memo": p.investment_memo or "",
            "is_set": True,
        }
    finally:
        s.close()


SESSION_DAYS = 30


def create_user_session(user_id: int) -> str:
    """セッショントークンを生成してDBに保存し、トークン文字列を返す"""
    s = get_session()
    try:
        token = secrets.token_urlsafe(32)
        s.add(UserSession(
            token=token,
            user_id=user_id,
            expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
        ))
        s.commit()
        return token
    finally:
        s.close()


def get_user_by_session_token(token: str) -> dict | None:
    """トークンが有効なら対応するユーザー情報を返す。無効・期限切れは None"""
    s = get_session()
    try:
        sess = s.query(UserSession).filter_by(token=token).first()
        if not sess or sess.expires_at < datetime.utcnow():
            return None
        user = s.query(User).filter_by(id=sess.user_id).first()
        if not user or not user.is_approved or not user.is_verified:
            return None
        return {
            "id":           user.id,
            "email":        user.email,
            "display_name": user.display_name,
            "is_admin":     user.is_admin,
        }
    finally:
        s.close()


def delete_user_session(token: str):
    s = get_session()
    try:
        s.query(UserSession).filter_by(token=token).delete()
        s.commit()
    finally:
        s.close()


def delete_all_user_sessions(user_id: int):
    s = get_session()
    try:
        s.query(UserSession).filter_by(user_id=user_id).delete()
        s.commit()
    finally:
        s.close()


def save_user_profile(user_id: int, investment_style: str, risk_tolerance: str,
                      time_horizon: str, weights: dict, investment_memo: str):
    s = get_session()
    try:
        p = s.query(UserProfile).filter_by(user_id=user_id).first()
        if not p:
            p = UserProfile(user_id=user_id)
            s.add(p)
        p.investment_style  = investment_style
        p.risk_tolerance    = risk_tolerance
        p.time_horizon      = time_horizon
        p.weight_dividend   = weights["dividend"]
        p.weight_financial  = weights["financial"]
        p.weight_growth     = weights["growth"]
        p.weight_value      = weights["value"]
        p.investment_memo   = investment_memo
        p.updated_at        = datetime.utcnow()
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
