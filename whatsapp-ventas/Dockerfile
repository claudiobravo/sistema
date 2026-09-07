FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# poppler-utils = pdftoppm, lo que usa pdf2image para rasterizar etiquetas escaneadas.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY tools ./tools

RUN useradd --create-home --uid 10001 bot \
 && mkdir -p /datos \
 && chown -R bot:bot /datos /srv
USER bot

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/salud || exit 1

CMD ["uvicorn", "app.main:obtener_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
