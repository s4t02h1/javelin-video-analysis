# ── Javelin Video Analysis — Dockerfile (Phase 8) ─────────────────────────────
#
# 使用例:
#   docker build -t jva .
#   docker run --rm -p 8000:8000 --env-file .env jva uvicorn server.app:app --host 0.0.0.0 --port 8000
#   docker run --rm -p 8501:8501 --env-file .env jva streamlit run admin_app.py --server.address=0.0.0.0 --server.port=8501
#   docker run --rm --env-file .env jva python worker.py
#
# ベースイメージ: python:3.11-slim
#   OpenCV の headless 版を使うため slim ベースを採用。
#   GUI 機能は不要なため opencv-python-headless に差し替える。
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# ── ビルド時引数 ──────────────────────────────────────────────────────────────
ARG DEBIAN_FRONTEND=noninteractive

# ── システム依存パッケージのインストール ──────────────────────────────────────
# OpenCV headless / MediaPipe の実行に最低限必要なライブラリ
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 作業ディレクトリ ──────────────────────────────────────────────────────────
WORKDIR /app

# ── Python 依存パッケージのインストール ──────────────────────────────────────
# requirements.txt を先にコピーしてキャッシュを有効活用する
COPY requirements.txt ./

# opencv-python の代わりに headless 版を使う（GUI 不要）
# requirements.txt の opencv-python を headless に置き換えてからインストール
RUN sed 's/^opencv-python>=/opencv-python-headless>=/g' requirements.txt \
        > /tmp/requirements-docker.txt \
    && pip install --no-cache-dir -r /tmp/requirements-docker.txt \
    && pip cache purge

# ── アプリケーションコードのコピー ────────────────────────────────────────────
COPY . .

# ── 永続化ボリューム用ディレクトリの作成 ──────────────────────────────────────
RUN mkdir -p /app/data /app/outputs /app/logs /app/uploads /app/jobs

# ── 非rootユーザー化 ──────────────────────────────────────────────────────────
RUN groupadd --gid 1001 jva \
    && useradd --uid 1001 --gid jva --no-create-home --shell /bin/bash jva \
    && chown -R jva:jva /app
USER jva

# ── デフォルト環境変数 ────────────────────────────────────────────────────────
ENV JVA_ENV=production \
    JVA_DATA_DIR=/app/data \
    JVA_OUTPUT_DIR=/app/outputs \
    JVA_LOG_DIR=/app/logs \
    JVA_UPLOAD_DIR=/app/uploads \
    JVA_QUEUE_DIR=/app/data/queue \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# ── デフォルトコマンド ────────────────────────────────────────────────────────
# docker-compose.yml または起動時に上書き可能
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]

# ── ポート ────────────────────────────────────────────────────────────────────
EXPOSE 8000 8501
