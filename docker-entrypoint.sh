#!/bin/sh
set -e

# bind mountされたファイル・ディレクトリがroot所有のまま渡されると、
# 非rootユーザー(appuser)のアプリが書き込めずSQLiteが
# "attempt to write a readonly database" で失敗する
# (EC2再構築時にrootで復元したファイルをそのまま使うと発生。2026-08-07実際に発生)。
# コンテナ起動のたびに自動でappuser所有へ揃えることで、
# ホスト側の復元手順に依存せず恒久的に防ぐ。
for path in /app/stock_analyzer.db /app/yfinance_cache.sqlite; do
    if [ -e "$path" ]; then
        chown appuser:appuser "$path"
    fi
done
chown appuser:appuser /app

exec gosu appuser "$@"
