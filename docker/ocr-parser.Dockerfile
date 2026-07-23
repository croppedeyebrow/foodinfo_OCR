FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV FLAGS_use_mkldnn=0

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
       libgl1 \
       libglib2.0-0 \
       libgomp1 \
       libsm6 \
       libxext6 \
       libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY apps/ocr-parser/requirements.txt /tmp/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir \
       paddlepaddle==3.2.0 \
       --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/ \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY apps/ocr-parser/src /app/src
COPY contracts /app/contracts

CMD ["python", "-m", "src.cli", "health"]
