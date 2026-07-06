# stock-analyzer

個人・家族向けの株式投資情報収集・分析 Web アプリ。AWS 上に本番環境を構築・運用中。

**実稼働 URL:** https://app.kimura-stock.com（要ログイン）

---

## このプロジェクトについて

**「開発を生成 AI に委ねたらどこまでいけるか」という実験プロジェクトです。** AWS SAA 取得後に実務経験のないサービスを実際に動かすことで、ハンズオンの実践経験を積むことも目的に含んでいます。

コード生成・設定ファイル生成（nginx・systemd 等）は Claude に全面委任し、インフラ構成の選定も AI との相談を通じて決めました。自分は以下を担当しました：

- AWS 上での実際の操作・設定（EC2・SES・Route53 の設定、SES プロダクション申請等）
- Session Manager 経由の EC2 作業（コマンド実行・ファイル編集）
- 要件定義（何を作るか・どの機能が必要かの判断）
- AI への指示設計と生成物のレビュー・検証
- 本番環境でのトラブル対応と原因分析

この開発スタイルを通じて「どの作業を AI に委任できるか・できないか」を実際のサービス運用を通じて検証しました。コードの詳細より、**何を学び何を判断したか**に重点を置いたポートフォリオです。

---

## 目次

1. [このプロジェクトについて](#このプロジェクトについて)
2. [プロジェクト概要](#プロジェクト概要)
3. [アーキテクチャ](#アーキテクチャ)
4. [使用技術・AWS サービス](#使用技術aws-サービス)
5. [インフラ設計の意思決定](#インフラ設計の意思決定)
6. [デプロイ手順](#デプロイ手順)
7. [運用・監視](#運用監視)
8. [セキュリティ](#セキュリティ)
9. [今後の改善予定](#今後の改善予定)

---

## プロジェクト概要

日本株・米国株を対象とした投資情報の収集・分析・アラートを一元管理する Web アプリ。外部 API（J-Quants / Yahoo Finance）からデータを取得し、スコアリングと AI レポート生成（Claude API）を組み合わせた銘柄分析機能を持つ。

**主な機能:**

| ページ | 機能 |
|---|---|
| スクリーニング | 財務指標でフィルタ・スコアリング（並列取得・DB キャッシュ対応） |
| 銘柄詳細 | チャート・財務・AI レポート・ニュース |
| 銘柄比較 | 最大 5 銘柄の指標テーブル・正規化チャート・AI 横断レポート |
| ポートフォリオ | 損益計算・CSV インポート（開発中） |
| 配当カレンダー | 保有銘柄の配当スケジュール表示（権利確定日・支払日のデータ取得が困難なため未完成） |
| ウォッチリスト | 注目銘柄の登録・管理 |
| アラート | 株価条件を設定 → 条件合致でメール通知 |
| AI チャット | 銘柄・投資戦略に関する AI との対話（プロフィール情報をコンテキストとして反映） |
| プロフィール | 投資スタイル・リスク許容度等の設定（AI チャットのコンテキストに使用） |

---

## アーキテクチャ

```
  ユーザー
  (ブラウザ)
      │ HTTPS
      ▼
  Route 53（app.kimura-stock.com）
      │
      ▼
  ┌────────────────── AWS (ap-northeast-1) ──────────────────────┐
  │                                                              │
  │  ┌─────────────────── EC2 t3.micro ───────────────────────┐  │
  │  │                                                        │  │
  │  │  ┌──────────────────────────────────────────────────┐  │  │
  │  │  │ nginx                         ポート 80 / 443    │  │  │
  │  │  │  ・HTTP → HTTPS リダイレクト（301）              │  │  │
  │  │  │  ・SSL/TLS 終端（Let's Encrypt）                 │  │  │
  │  │  │  ・リバースプロキシ                              │  │  │
  │  │  └──────────────────────┬───────────────────────────┘  │  │
  │  │                         │ localhost:8501               │  │
  │  │  ┌──────────────────────▼───────────────────────────┐  │  │
  │  │  │ Streamlit（systemd 管理）                        │  │  │
  │  │  │  SQLite（ローカル DB）                           │  │  │
  │  │  └──────────────────────────────────────────────────┘  │  │
  │  │                                                        │  │
  │  │  cron（平日 9:05 / 12:30 / 15:35 JST）                  │  │
  │  │  └─► check_alerts.py                                  │  │
  │  │                  │                                     │  │
  │  └──────────────────┼─────────────────────────────────────┘  │
  │                     ▼                                        │
  │                 AWS SES ──────────────────────────────────────┼──► メール通知
  │                                                              │
  └──────────────────────────────────────────────────────────────┘

  操作端末 ──── AWS Session Manager ────► EC2（SSH ポート不要）

  外部 API: J-Quants（日本株）/ Yahoo Finance（米国株）/ Claude API（AI レポート）
```

---

## 使用技術・AWS サービス

### アプリケーション・ミドルウェア（EC2 上で動作）

| 技術 | 用途 |
|---|---|
| Python 3.11 | アプリケーション本体 |
| Streamlit | Web UI フレームワーク |
| SQLite | ユーザー・ポートフォリオ・アラートデータ永続化 |
| nginx | リバースプロキシ・HTTPS 終端・HTTP→HTTPS リダイレクト |
| J-Quants Light API | 日本株の財務・株価データ |
| Yahoo Finance API | 米国株の財務・株価データ |
| Claude API (claude-sonnet-4-6) | AI 銘柄レポート・投資チャット |

### AWS サービス

| サービス | 用途 | 選定理由 |
|---|---|---|
| EC2 (t3.micro) | アプリサーバー | SQLite 永続化・常時起動が必要 |
| Route 53 | DNS 管理 | カスタムドメイン（kimura-stock.com）の A レコード管理 |
| AWS SES | メール送信 | 認証メール・アラートメールの信頼性確保 |
| Systems Manager (Session Manager) | EC2 接続 | SSH ポート (22) 不要でセキュアな操作 |
| EventBridge | EC2 の自動起動・停止 | 稼働時間を 7:00〜21:00 に限定しコスト削減 |

---

## インフラ設計の意思決定

### EC2 を選んだ理由（Lambda / ECS ではなく）

SQLite をファイルとして EC2 ローカルに置くことで、外部 DB（RDS 等）なしにデータ永続化を実現した。個人用途で同時接続数が少ないため、RDS のコスト（~$15/月）を EC2 ローカル SQLite で削減している。

Lambda はステートレス・ファイルシステム非永続のため不採用。ECS を使う場合は SQLite の永続化に EFS 等のボリューム設定が必要になり複雑度が上がる。

**学び:** 規模感に応じたシンプルなアーキテクチャが保守性を高める。小規模なら「EC2 + ローカル SQLite」がコスト・複雑度ともに優位。

### SSH を使わず Session Manager で EC2 に接続する

セキュリティグループにポート 22 (SSH) を開放していない。代わりに AWS Systems Manager の Session Manager を使い、IAM 権限ベースで EC2 にアクセスする。

- SSH キーの紛失・漏洩リスクをゼロにできる
- CloudTrail に操作ログが自動記録される
- VPC 外からの直接アクセスを遮断できる

**学び:** Session Manager は「SSH の代替」ではなく「SSH よりセキュアな接続手段」。LPIC で SSH を学んでいたが、それよりも安全な選択肢が AWS にはある。

### AWS SES でメール送信する理由

AWS サービス内で完結させることを方針としたため SES を採用した。DKIM・SPF・DMARC・Custom MAIL FROM をすべて設定し、SES プロダクションモードを取得済み（2026-06-21 AWS 承認）。

**学び:** メール送信には SPF・DKIM・DMARC の DNS 設定が必要であることを実装を通じて初めて知った。

### nginx でリバースプロキシを構成する理由

Streamlit はデフォルトでポート 8501 で起動する。nginx をフロントに置くことで:

- ポート 443 (HTTPS) でのアクセスを可能にし、8501 への直接アクセスを不要にした
- Let's Encrypt の SSL 証明書を nginx で管理し、アプリ側は HTTP のみに集中できる
- HTTP アクセスは nginx で 301 リダイレクトし、HTTPS を強制

**学び:** Web サービスにおけるリバースプロキシの役割（SSL 終端・ポート変換・リダイレクト）を実際のサービス公開で習得した。

### systemd でアプリを管理する理由

`stock-analyzer.service` として登録することで:

- EC2 再起動後に自動で Streamlit が起動する
- `systemctl status` で状態確認、`journalctl -u stock-analyzer` でログ確認ができる
- cron よりもプロセス管理が確実（再起動・障害検知が容易）

**学び:** systemd のユニットファイル記述、`ExecStart` / `WorkingDirectory` / `Environment` の設定方法を実装した。LPIC で学んだ概念を実運用で確認できた。

### EventBridge で EC2 の稼働時間を制限する理由

個人・家族向けの用途であり不特定多数へのサービス展開を想定していないため、コスト削減を優先した。EventBridge スケジュールで EC2 を毎日 7:00 に自動起動・21:00 に自動停止し、深夜・早朝は停止状態を維持している。

---

## デプロイ手順

ローカルで変更を開発し、EC2 に反映する手順の概要。

```bash
# 1. ローカルで動作確認
conda run -n stock_analyzer streamlit run app.py --server.port 8502

# 2. GitHub に push
git push origin main

# 3. Session Manager で EC2 に接続し pull & 再起動
git -C /home/ssm-user/stock_analyzer pull
sudo systemctl restart stock-analyzer
sudo systemctl status stock-analyzer

# 4. ブラウザで動作確認
# https://app.kimura-stock.com
```

**環境変数:** `.env` ファイルで管理し、`.gitignore` に含めて Git 管理対象外にしている（`.env.example` でキー名のみ共有）。

---

## 運用・監視

### アラート通知（cron）

株価アラートチェックを EC2 の crontab で定義:

```
# 平日の取引時間帯に3回チェック（UTC 表記 / JST = UTC+9）
5  0 * * 1-5 /usr/bin/python3 /home/ssm-user/stock_analyzer/scripts/check_alerts.py >> /home/ssm-user/stock_analyzer/logs/alert.log 2>&1
30 3 * * 1-5 /usr/bin/python3 /home/ssm-user/stock_analyzer/scripts/check_alerts.py >> /home/ssm-user/stock_analyzer/logs/alert.log 2>&1
35 6 * * 1-5 /usr/bin/python3 /home/ssm-user/stock_analyzer/scripts/check_alerts.py >> /home/ssm-user/stock_analyzer/logs/alert.log 2>&1
```

条件（目標株価・下落率）に合致した銘柄は SES 経由でメール通知される。

### ログ確認

```bash
# アプリログ
journalctl -u stock-analyzer -n 100 --no-pager

# nginx アクセスログ
sudo tail -f /var/log/nginx/access.log
```

### 本番での実際のトラブル対応記録

**事例: SES メール認証リンクが壊れていた（2026-06-21）**

家族のアカウント登録時に、認証メールのリンクが `http://app.kimura-stock.com:8501` になっていることが判明。原因は `config.py` のデフォルト値と EC2 の `.env` の設定値が古いままだったこと。

対応手順:
1. `config.py` の `APP_URL` デフォルト値を `https://app.kimura-stock.com` に修正して push
2. Session Manager で EC2 に接続し、`sudo sed -i` で `.env` の値を修正
3. `systemctl restart stock-analyzer` でサービス再起動
4. テスト送信で HTTPS リンクになっていることを確認

**学び:** コードのデフォルト値と本番 `.env` の値が乖離していると、デプロイ後のデバッグが難しくなる。環境変数の変更はコードと `.env` の両方を確認するフローを作った。

---

## セキュリティ

| 対策 | 実装内容 |
|---|---|
| 秘密情報の管理 | APIキー・パスワードはすべて `.env` ファイルで管理。Git リポジトリに含めない |
| SSH 不使用 | セキュリティグループにポート 22 を開放せず Session Manager のみで接続 |
| HTTPS 強制 | nginx で HTTP → HTTPS 301 リダイレクト。SSL 証明書は Let's Encrypt |
| メール認証 | DKIM / SPF / DMARC / Custom MAIL FROM をすべて設定済み（SES プロダクションモード） |
| 認証・認可 | 全ページに `require_login()` を実装。管理者承認後のみログイン可能 |
| コードの静的検査 | `tests/` に pytest ベースの Checker を用意（ハードコード IP 検出等） |

---

## 今後の改善予定

- **IaC（Terraform）:** EC2・SES・Route53・IAM の構成をコードで再現可能にする
- **GitHub Actions CI:** push 時に静的チェック（pytest・flake8）を自動実行
- **CloudWatch メトリクス:** EC2 CPU/メモリの監視とアラームを設定する
- **RDS への移行評価:** 利用者増加時の SQLite の限界（同時書き込み）を認識しており、移行基準を事前に定義する
- **エラーハンドリング改善:** `email_sender.py` のサイレント失敗（`except ClientError: return False`）を適切なロギングに置き換える
