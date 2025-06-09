FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Añadir la ruta base al PYTHONPATH para que se puedan importar los módulos locales
ENV PYTHONPATH=/app

COPY docker/scraper/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY scripts /app/scripts
COPY utils /app/utils

CMD ["python", "scripts/scraping/fbref_scraper.py"]
