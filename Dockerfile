# ── builder: 依存関係をvenvにインストール ──────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── final: 実行用イメージ ──────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    HOME="/home/appuser" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --chown=appuser:appuser . .
# WORKDIRはCOPYより前にrootで/appを作成するため、COPY --chownの対象に
# ディレクトリ自体(所有権)が含まれない。SQLiteがジャーナルファイルを
# 作成する際にディレクトリへの書き込み権限が必要なため明示的に直す。
RUN chown appuser:appuser /app

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# コンテナはrootで起動する（entrypointがbind mountの所有権をappuserへ揃えてから
# gosuでappuserに切り替えるため。ここでUSER appuserを指定すると、
# EC2再構築等でroot所有のまま復元されたDBファイルをchownできなくなる。2026-08-07の障害を踏まえた変更）。

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
