# syntax=docker/dockerfile:1
#
# Helix Core — the quiz/scoring service, containerised.
#
# This image deliberately contains only `helix_core/`, not the rest of the
# Helix Education package. The core imports nothing outside the standard
# library plus FastAPI, Pydantic and Uvicorn, so the image stays small and
# does not drag in the Ollama client or the HTML scraper.
#
# Once `helix_core` ships as its own distribution this becomes:
#   RUN pip install --no-cache-dir "helix-core==2.1.0"
# and the COPY line goes away.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HELIX_CORE_DB=/data/core.db

# Unprivileged runtime user. The UID is fixed because the Kubernetes
# securityContext pins runAsUser to the same value.
RUN groupadd --gid 10001 helix \
 && useradd --uid 10001 --gid helix --no-create-home --shell /usr/sbin/nologin helix

WORKDIR /app

RUN pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn>=0.30" \
        "pydantic>=2.0"

COPY --chown=root:root helix_core ./helix_core

# The SQLite database lives on a mounted volume; /data must exist and be
# writable by the runtime user even before the volume is attached.
RUN mkdir -p /data && chown 10001:10001 /data

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health', timeout=2).status == 200 else 1)"

# Binds 0.0.0.0 inside the container; the cluster network policy and the
# Service are what restrict reachability. Locally, publish to 127.0.0.1 only.
CMD ["python", "-m", "helix_core", "--host", "0.0.0.0", "--port", "8000"]
