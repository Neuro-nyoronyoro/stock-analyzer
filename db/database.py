from sqlalchemy import create_engine, Column, String, Float, Integer, Date, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

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
