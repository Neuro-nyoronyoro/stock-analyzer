# 株式投資ダッシュボード - プロジェクト情報

個人・家族用の株式投資情報収集・分析ウェブアプリ。

## 基本方針
- 対象市場: 日本株・米国株
- 投資スタイル: 中長期・配当重視
- 証券会社: 大和証券のみ（売買執行連携は断念、手動入力）
- AI: Claude API（`claude-sonnet-4-6`）で投資参考レポートを生成
- APIキーは絶対にチャットに貼らない。`.env` ファイルに直接記載する

## ローカル開発環境
- コードパス: `C:\Users\kimura-h-0\Desktop\株式投資ツール\`
- GitHub: `https://github.com/Neuro-nyoronyoro/stock-analyzer`
- `.env` はGit管理しない（`.gitignore` で除外済み）
- `.env.example` を参考に手動作成する

## AWS EC2環境
- URL: `https://app.kimura-stock.com`（旧: `http://13.114.149.93:8501`）
- インスタンス: t3.micro（東京リージョン ap-northeast-1）
- OS: Amazon Linux 2023
- **Elastic IP: `57.182.51.133`**（固定済み・停止してもIPが変わらない）
- **ユーザー: `ssm-user`**（ec2-user ではない）
- **サービス名: `stock-analyzer.service`**
- **アプリパス: `/home/ssm-user/stock_analyzer/`**（ハイフンなし）
- SSH: Session Manager経由（ポート22不可・会社ネットワーク制限のため）
- Python: 3.9.25。パッケージは `/home/ssm-user/.local/` 配下 → スクリプト実行は sudo なし

## ネットワーク・SSL構成
- **ドメイン**: `app.kimura-stock.com`（Route53 A レコードで `57.182.51.133` に紐付け済み）
- **nginx**: リバースプロキシとして動作（80→443リダイレクト・443→localhost:8501）
  - 設定ファイル: `/etc/nginx/conf.d/stock-analyzer.conf`
- **SSL証明書**: Let's Encrypt（Certbot で取得・自動更新設定済み）
  - 証明書パス: `/etc/letsencrypt/live/app.kimura-stock.com/`
  - 有効期限: 2026-09-13（自動更新されるため手動更新不要）
- **開放ポート**: 80（HTTP）・443（HTTPS）・8501（Streamlit直接）
- 会社ネットワークからはSSLインスペクションにより接続不可（自宅・モバイル回線からは正常接続できる）

## EC2へのファイル反映手順
```bash
# ファイルを編集後、EC2へ転送してサービス再起動
# ファイル書き込みは必ず sudo tee を使う（cat > は permission denied）
sudo tee /home/ssm-user/stock_analyzer/ファイル名 > /dev/null << 'PYEOF'
（ファイル内容）
PYEOF

# サービス再起動（必ず末尾に付ける）
sudo systemctl restart stock-analyzer.service
```

## ファイル構成
```
株式投資ツール/
├── app.py              # エントリポイント・認証UI・ダッシュボード
├── config.py           # 環境変数・スコア重み・モデル設定
├── requirements.txt
├── .env                # APIキー類（Git管理外）
├── .env.example        # キー名のテンプレート
├── CLAUDE.md           # このファイル
├── core/
│   ├── auth.py         # 登録・ログイン・パスワードリセット・プロフィール
│   ├── auth_check.py   # require_login() / require_admin()
│   ├── email_sender.py # SESメール送信
│   ├── fetcher.py      # 株価・財務データ取得（JP/US銘柄リスト含む）
│   ├── jquants.py      # J-Quants API v2（日本株）
│   ├── yahoo_direct.py # Yahoo Finance 直接HTTP（crumb方式）
│   ├── scorer.py       # 4軸スコアリング
│   ├── technical.py    # テクニカル指標（MA/RSI/MACD/BB）
│   ├── ai_report.py    # Claude による銘柄分析レポート生成
│   ├── ai_chat.py      # Claude との投資相談チャット
│   └── news.py         # Google News RSS / NewsAPI
├── db/
│   └── database.py     # SQLAlchemy モデル・マイグレーション
├── pages/
│   ├── 1_Screening.py  # スクリーニング（並列取得・DBキャッシュ）
│   ├── 2_Detail.py     # 銘柄詳細（チャート・財務・AIレポート・ニュース）
│   ├── 3_Portfolio.py  # ポートフォリオ（損益・配当シミュ・為替シミュ）
│   ├── 4_Dividend.py   # 配当カレンダー
│   ├── 5_Watchlist.py  # ウォッチリスト
│   ├── 6_Alert.py      # 株価アラート（指数・個別銘柄）
│   ├── 7_AIChat.py     # AIチャット（セッション管理・履歴DB保存）
│   ├── 8_Admin.py      # 管理者パネル（承認・削除、管理者は削除ボタン非表示）
│   └── 9_Profile.py    # アカウント設定・削除（管理者は削除不可）
└── scripts/
    └── check_alerts.py # cron用アラートチェック・SESメール送信
```

## DBテーブル（SQLite: stock_analyzer.db）
| テーブル | 内容 |
|---|---|
| User | 認証情報（id, email, password_hash, display_name, is_verified, is_approved, is_admin, verification_token, reset_token, reset_token_expires） |
| Portfolio | 保有銘柄（user_id, ticker, name, market, shares, avg_cost, manual_price, purchase_date, memo） |
| Watchlist | ウォッチリスト（user_id, ticker, name, market）unique制約: (user_id, ticker) |
| ScoreCache | スコアキャッシュ（24時間TTL） |
| AIReport | AIレポート履歴 |
| PriceAlert | 株価アラート設定（user_id, ticker, alert_type: above/below, threshold） |
| ChatSession | AIチャットセッション（最大10件、古いものは自動削除） |
| ChatMessage | チャットメッセージ（セッションあたり最大20件） |
| UserProfile | 投資プロフィール（user_id, investment_style, risk_tolerance, time_horizon, weight_dividend/financial/growth/value, investment_memo） |

- ローカルの `stock_analyzer.db` はテスト用。本番DBはEC2上にある
- `init_db()` が自動でテーブル作成・マイグレーションを実行する

## 認証システム
- 最初に登録したユーザー → 自動で管理者（is_admin=True）＋自動承認（is_approved=True）
- 2人目以降 → 管理者が8_Admin.pyから承認後にログイン可能
- 全ユーザーにメール認証（verification_token）が必要
- 未認証アドレスで再登録 → 新トークンを発行してメール再送（ブロックしない）
- 管理者アカウントは9_Profile.py・8_Admin.py いずれからも削除不可

## データソース
| 対象 | 財務データ | 株価チャート |
|---|---|---|
| 日本株（.T） | J-Quants Light API | J-Quants（最大5年） |
| 米国株 | Yahoo Finance 直接API（crumb方式） | Yahoo Finance 直接API |
| yfinance | EC2ではレート制限でほぼ使用不可（フォールバック用） | 同左 |

### J-Quants Light プラン
- 月額: 1,650円
- `fins/summary` の日付フィールドは `DiscDate`（`DisclosedDate` は存在しない）
- `fins/summary` は昇順 → `_latest_annual()` で DiscDate 降順ソート済み
- `fins/dividend`（配当情報）: Premium のみ → JP株配当カレンダーは取得不可

## スコアリング重み（config.py）
```python
SCORE_WEIGHTS = {
    "dividend": 0.30,   # 配当
    "financial": 0.35,  # 財務健全性
    "growth":    0.20,  # 成長性
    "value":     0.15,  # 割安度
}
```

## メール送信（AWS SES）
- 送信元: `noreply@kimura-stock.com`
- Custom MAIL FROM domain: `mail.kimura-stock.com`
- Route53・DKIM・SPF・DMARC すべて設定済み・Verified
- **現在: SANDBOXモード** → 検証済みアドレスにしか送れない
- SESプロダクションアクセス申請中（承認後に家族のアカウント登録作業を実施）

## EC2 自動停止・起動スケジュール（EventBridge Scheduler）
| スケジュール名 | Cron式 | タイムゾーン | 動作 |
|---|---|---|---|
| `ec2-stop-night` | `0 21 * * ? *` | Asia/Tokyo | 毎日 21:00 に EC2 停止 |
| `ec2-start-morning` | `0 7 * * ? *` | Asia/Tokyo | 毎日 07:00 に EC2 起動 |

- IAM ロール: `EventBridgeScheduler-EC2-StartStop`
- nginx・stock-analyzer.service は `enabled` 設定済み → EC2 再起動時に自動起動する
- Elastic IP により停止・起動後も IP アドレスは `57.182.51.133` で固定

## 株価アラート（cron）
- スクリプト: `/home/ssm-user/stock_analyzer/scripts/check_alerts.py`
- 平日 9:00 / 12:00 / 15:30 に3回実行（crontab設定済み）
- ユーザーごとにSES直接送信（ユーザー間でアラートが混在しない）

## 既知の課題
- SESプロダクション承認待ち（承認後、家族のYahoo/外部アドレスへの送信が可能になる）
- `email_sender.py` の `except ClientError: return False` がサイレント失敗（要改善）
