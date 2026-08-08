FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DAGSTER_HOME=/opt/dagster/dagster_home

COPY apps/normalizer/requirements.txt /tmp/normalizer-requirements.txt
COPY orchestration/requirements.txt /tmp/orchestration-requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir \
        -r /tmp/normalizer-requirements.txt \
        -r /tmp/orchestration-requirements.txt

COPY apps/normalizer/src /app/src
COPY orchestration /app/orchestration
COPY contracts /app/contracts
COPY orchestration/dagster.yaml ${DAGSTER_HOME}/dagster.yaml

EXPOSE 3000

CMD ["dagster", "dev", "--host", "0.0.0.0", "--port", "3000", "-m", "orchestration.definitions"]
