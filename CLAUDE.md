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
- URL: `https://app.kimura-stock.com`
- インスタンス: t3.micro（東京リージョン ap-northeast-1）、**Docker運用**（2026-07-08にDocker化+CDK化移行済み）
- OS: Amazon Linux 2023
- **Elastic IP: `54.178.98.12`**（固定済み・停止してもIPが変わらない。旧`57.182.51.133`は2026-08-05にrelease済み、記載が残っていたら誤り）
- **ユーザー: `ssm-user`**（ec2-user ではない）
- SSH: Session Manager経由（ポート22不可・会社ネットワーク制限のため）
- アプリはDockerコンテナとして稼働。ホスト側にPython/pipは無い（コンテナ内で完結）
- **アプリパス（ホスト側）: `/opt/stock-analyzer/`**（`docker-compose.yml`・`.env`・DBファイルを配置）
- **コンテナ名: `stock-analyzer-app`**、compose project名: `stock-analyzer`
- **ECRリポジトリ**: `600627320448.dkr.ecr.ap-northeast-1.amazonaws.com/stock-analyzer`（`:latest`タグ運用）
- IaC: `infra/`（Python CDK）が**現在デプロイされている実体**。`infra-ts/`はTypeScript書き換え中でまだ未デプロイ（cdk deployする前に必ずどちらが対象か確認すること）
- ルートボリューム: 18GB gp3（2026-08-05に8GB→18GBへ拡張）
- AMIは`compute_stack.py`で特定AMIにピン留め済み（`latest_amazon_linux2023()`は使わない）。理由: `AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>`型パラメータは毎回最新AMIを再解決するため、無関係な変更でも意図せずインスタンス置き換えが発生していた。OSセキュリティパッチは**手動でAMI IDを更新**して適用する運用

### ⚠️ インスタンス置き換え時の注意（2026-08-05に実際に事故発生・要対応）
- **DBデータはルートボリューム上（`/opt/stock-analyzer/*.db`等）にあり、インスタンス置き換えで消える**（ルートボリュームは`DeleteOnTermination=true`でAMIから毎回まっさらに作成される。旧ボリュームのコピーではない）。`cdk deploy`でインスタンス置き換えが発生する前に**必ずEBSスナップショットを取得**し、置き換え後は一時ボリュームとしてアタッチ→ファイルコピーで復元すること（XFSクローンをmountする際は`-o nouuid`が必須）
- **`monitoring_stack.py`のEventBridge Rule（Lambda起動停止用）は`instance.instance_id`をスタック間参照(`Fn::GetStackOutput`)で持っているが、ComputeStack側でインスタンスが置き換わっても`cdk deploy`で自動追従しないことを確認済み**（2回deployしても"no changes"のまま旧IDが残った）。インスタンス置き換え後は`aws events list-targets-by-rule`で実際の値を必ず確認し、ズレていたら`aws events put-targets`で手動修正すること。根本原因は未調査
- 恒久対策として、DBを専用の永続EBSボリューム（`ec2.Volume` + `RemovalPolicy.RETAIN`、ルートボリュームとは別リソース）に分離する改修を検討中（未着手）

## ネットワーク・SSL構成
- **ドメイン**: `app.kimura-stock.com`（Route53 A レコードで `54.178.98.12` に紐付け済み）
- **nginx**: リバースプロキシとして動作（80→443リダイレクト・443→localhost:8501、ホストOS側で稼働・コンテナ外）
  - 設定ファイル: `/etc/nginx/conf.d/stock-analyzer.conf`
- **SSL証明書**: Let's Encrypt（Certbot で取得・自動更新cron設定済み）
  - 証明書パス: `/etc/letsencrypt/live/app.kimura-stock.com/`
  - 有効期限: 2026-10-06（自動更新されるため手動更新不要）
- **開放ポート**: 80（HTTP）・443（HTTPS）・8501（Streamlit直接、コンテナからホストへport forward）
- 会社ネットワークからはSSLインスペクションにより接続不可（自宅・モバイル回線からは正常接続できる）

## EC2へのファイル反映手順（Docker運用）
アプリコードの変更は、ホストへの直接配置ではなく**Dockerイメージのビルド→ECR push→EC2でpull**の流れになる。

```bash
# 1. ローカルでビルド・ECRへpush
aws ecr get-login-password --region ap-northeast-1 | docker login --username AWS --password-stdin 600627320448.dkr.ecr.ap-northeast-1.amazonaws.com
docker build -t 600627320448.dkr.ecr.ap-northeast-1.amazonaws.com/stock-analyzer:latest .
docker push 600627320448.dkr.ecr.ap-northeast-1.amazonaws.com/stock-analyzer:latest

# 2. EC2側（Session Manager経由）で新イメージを反映
cd /opt/stock-analyzer
docker compose -p stock-analyzer pull
docker compose -p stock-analyzer up -d
```

`.env`など設定ファイルのみの変更の場合（書き込みは必ず `sudo tee`。`cat >` は permission denied）:
```bash
sudo tee /opt/stock-analyzer/.env > /dev/null << 'ENVEOF'
（ファイル内容）
ENVEOF
cd /opt/stock-analyzer && docker compose -p stock-analyzer up -d
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
├── Dockerfile          # 本番用アプリイメージ
├── docker-compose.prod.yml  # EC2上でのコンテナ起動定義（__ECR_IMAGE__はCDKがビルド時に置換）
├── infra/              # AWS CDK（Python）※現在デプロイされている実体
│   └── infra/
│       ├── network_stack.py     # VPC・セキュリティグループ・IAMロール
│       ├── compute_stack.py     # EC2・ECR・EIP（Docker運用のUserData含む）
│       ├── dns_stack.py         # Route53
│       └── monitoring_stack.py  # CloudWatchアラーム・SNS・EC2起動停止Lambda
├── infra-ts/            # AWS CDK（TypeScript書き換え中）※まだ未デプロイ、infra/と混同しないこと
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

## EC2 自動停止・起動スケジュール（EventBridge Rules + Lambda）
`infra/infra/monitoring_stack.py` でCDK管理。**旧EventBridge Scheduler方式（`ec2-stop-night`等、手動作成）は2026-08-05に廃止・削除済み**。現在は下記のEventBridge Rules→Lambda方式のみ。

| リソース | Cron式(UTC) | JST | 動作 |
|---|---|---|---|
| `StartRule` | `cron(0 22 * * ? *)` | 07:00 起動 | Lambda `StartStopFunction` に `{"action":"start"}` を渡して実行 |
| `StopRule` | `cron(0 12 * * ? *)` | 21:00 停止 | 同Lambdaに `{"action":"stop"}` を渡して実行 |

- Lambda（`StartStopFunction`）はboto3で`ec2:start_instances`/`stop_instances`を呼ぶだけの薄い実装
- インスタンスIDはCDKコードの`instance.instance_id`から自動参照 → **将来インスタンスが再作成されても自動追従する**（手動管理のEventBridge Schedulerで起きた「旧IDを指したまま1ヶ月放置」事故はこの方式なら起きない）
- nginx・docker・crondは `systemctl enable` 済み → EC2再起動時に自動起動。アプリコンテナは`docker-compose.yml`に`restart: unless-stopped`設定済みなのでdockerデーモン起動と共に自動起動
- Elastic IPにより停止・起動後もIPアドレスは `54.178.98.12` で固定

## 株価アラート（cron、コンテナ内実行）
- ホスト側cron（`/etc/cron.d/stock-analyzer`）から `docker compose exec -T app python scripts/check_alerts.py` を実行
- 平日 9:05 / 12:30 / 15:35 JST に3回実行
- ユーザーごとにSES直接送信（ユーザー間でアラートが混在しない）

## 既知の課題
- SESプロダクション承認待ち（承認後、家族のYahoo/外部アドレスへの送信が可能になる）
- `email_sender.py` の `except ClientError: return False` がサイレント失敗（要改善）
- `infra-ts/`（TypeScript CDK書き換え）は未完了・未デプロイ。`infra/`（Python）と内容が重複しているので、移行完了までは`infra/`側を正として扱うこと
