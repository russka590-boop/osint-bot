FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

ARG INSTALL_MAIGRET=0
RUN if [ "$INSTALL_MAIGRET" = "1" ]; then pip install maigret; fi

COPY . .

RUN mkdir -p reports data

CMD ["python", "run.py"]
