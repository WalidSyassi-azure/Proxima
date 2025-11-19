FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    WKHTMLTOPDF_EXE=/usr/bin/wkhtmltopdf

# System deps for wkhtmltopdf
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wkhtmltopdf \
        libxrender1 libxext6 libfontconfig1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Render sets $PORT
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT}"]
