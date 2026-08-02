FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# docker CLI + compose plugin so the console can spawn crawler/ocr-parser jobs
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
RUN mkdir -p /usr/local/libexec/docker/cli-plugins \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL \
        "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-$(uname -m)" \
        -o /usr/local/libexec/docker/cli-plugins/docker-compose \
    && chmod +x /usr/local/libexec/docker/cli-plugins/docker-compose \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

COPY apps/console/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/console/src /app/src

EXPOSE 8787

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8787"]
