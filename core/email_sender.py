import sys

import boto3
from botocore.exceptions import ClientError
from config import SES_SENDER_EMAIL, APP_URL


def _client():
    return boto3.client("ses", region_name="ap-northeast-1")


def _send(to_email: str, subject: str, body: str) -> bool:
    if not SES_SENDER_EMAIL:
        print("[email_sender] SES_SENDER_EMAIL not set, skipping send", file=sys.stderr, flush=True)
        return False
    try:
        _client().send_email(
            Source=SES_SENDER_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body":    {"Text": {"Data": body,    "Charset": "UTF-8"}},
            },
        )
        return True
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        message = e.response.get("Error", {}).get("Message", str(e))
        print(f"[email_sender] SES send failed to={to_email} code={code} message={message}", file=sys.stderr, flush=True)
        return False


def send_verification_email(to_email: str, display_name: str, token: str) -> bool:
    url = f"{APP_URL}/?verify={token}"
    subject = "【株式投資アプリ】メールアドレスの確認"
    body = f"""{display_name} さん

アカウント登録ありがとうございます。
以下のリンクをクリックしてメールアドレスを確認してください。

{url}

このリンクは24時間有効です。
心当たりがない場合は無視してください。
"""
    return _send(to_email, subject, body)


def send_reset_email(to_email: str, display_name: str, token: str) -> bool:
    url = f"{APP_URL}/?reset={token}"
    subject = "【株式投資アプリ】パスワード再設定"
    body = f"""{display_name} さん

パスワード再設定のリクエストを受け付けました。
以下のリンクをクリックしてパスワードを再設定してください。

{url}

このリンクは1時間有効です。
心当たりがない場合は無視してください。
"""
    return _send(to_email, subject, body)
