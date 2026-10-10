# ─────────────────────────────────────────────────────────────
# NHDIP API / worker / scheduler (동일 이미지, 커맨드로 역할 분기)
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev curl fonts-nanum \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY tests ./tests
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 비루트 실행
RUN useradd -m -u 10001 nhdip && chown -R nhdip:nhdip /app
USER nhdip

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["api"]
