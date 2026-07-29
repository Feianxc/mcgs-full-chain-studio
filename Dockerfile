FROM python:3.11.6-slim-bookworm@sha256:cc758519481092eb5a4a5ab0c1b303e288880d59afc601958d19e95b300bc86b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PROTOCOL_STUDIO_RUNS_ROOT=/data/runs \
    PROTOCOL_STUDIO_SECURITY_DB=/data/security.sqlite3

WORKDIR /app

COPY pyproject.toml requirements.production.lock.txt ./
RUN python -m pip install \
    --no-cache-dir \
    --only-binary=:all: \
    --require-hashes \
    --requirement requirements.production.lock.txt \
    && python -m pip check

COPY protocol_studio ./protocol_studio
COPY mvp_generator ./mvp_generator
COPY assembly_studio ./assembly_studio
COPY resources ./resources
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md ./

RUN groupadd --gid 10001 studio \
    && useradd --uid 10001 --gid studio --no-create-home --shell /usr/sbin/nologin studio \
    && mkdir -p /data/runs \
    && chown -R studio:studio /data

USER 10001:10001
EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8123/api/health', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "protocol_studio.app:app", "--host", "0.0.0.0", "--port", "8123", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
