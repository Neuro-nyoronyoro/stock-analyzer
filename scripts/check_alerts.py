import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import boto3
from datetime import date, datetime
from core.fetcher import get_stock_info
from db.database import get_session, PriceAlert, User
from config import SES_SENDER_EMAIL, APP_URL

AWS_REGION    = "ap-northeast-1"
INDEX_TICKERS = {"^N225", "^DJI", "^IXIC"}


def _get_price(ticker: str):
    if ticker in INDEX_TICKERS or ticker.startswith("^"):
        from core.yahoo_direct import get_price_history_direct
        try:
            df = get_price_history_direct(ticker, "5d")
            if not df.empty:
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
        return None
    else:
        info = get_stock_info(ticker)
        if "error" in info or not info.get("price"):
            return None
        return info["price"]


def send_alert_email(to_email: str, triggered: list):
    client = boto3.client("ses", region_name=AWS_REGION)

    lines = []
    for t in triggered:
        is_index  = t["ticker"] in INDEX_TICKERS or t["ticker"].startswith("^")
        icon      = "📈" if t["alert_type"] == "above" else "📉"
        direction = "上昇" if t["alert_type"] == "above" else "下落"
        label     = "現在値" if is_index else "現在株価"
        lines.append(
            f"{icon} {t['name']}（{t['ticker']}）\n"
            f"   {label}: {t['current']:,.0f} / 閾値({direction}): {t['threshold']:,.0f}\n"
        )

    body = (
        f"【株価アラート】{datetime.now().strftime('%Y-%m-%d %H:%M')} 時点\n\n"
        + "\n".join(lines)
        + "\n\n株式投資ダッシュボードで詳細を確認してください。\n"
        APP_URL
    )

    client.send_email(
        Source=SES_SENDER_EMAIL,
        Destination={"ToAddresses": [to_email]},
        Message={
            "Subject": {"Data": f"株価アラート通知 ({len(triggered)}件)", "Charset": "UTF-8"},
            "Body":    {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    )


def main():
    session       = get_session()
    active_alerts = session.query(PriceAlert).filter_by(active=True).all()
    session.close()

    if not active_alerts:
        print(f"[{datetime.now()}] 有効なアラートなし")
        return

    today              = date.today()
    triggered_by_user  = {}

    for alert in active_alerts:
        if alert.last_notified == today:
            continue

        current = _get_price(alert.ticker)
        if current is None:
            continue

        hit = (
            (alert.alert_type == "above" and current >= alert.threshold) or
            (alert.alert_type == "below" and current <= alert.threshold)
        )

        if hit:
            uid = alert.user_id
            if uid not in triggered_by_user:
                triggered_by_user[uid] = []
            triggered_by_user[uid].append({
                "ticker":     alert.ticker,
                "name":       alert.name,
                "alert_type": alert.alert_type,
                "threshold":  alert.threshold,
                "current":    current,
                "alert_id":   alert.id,
            })

    if not triggered_by_user:
        print(f"[{datetime.now()}] 条件達成なし")
        return

    total = 0
    for user_id, triggered in triggered_by_user.items():
        s    = get_session()
        user = s.query(User).filter_by(id=user_id).first()
        s.close()
        if not user or not user.email:
            continue

        send_alert_email(user.email, triggered)

        upd = get_session()
        for t in triggered:
            obj = upd.query(PriceAlert).filter_by(id=t["alert_id"]).first()
            if obj:
                obj.last_notified = today
        upd.commit()
        upd.close()

        total += len(triggered)
        print(f"[{datetime.now()}] {user.email} に {len(triggered)} 件送信")

    print(f"[{datetime.now()}] 合計 {total} 件のアラートを送信しました")


if __name__ == "__main__":
    main()
