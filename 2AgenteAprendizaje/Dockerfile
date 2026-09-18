FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    CENTINELA_REPORTES_DIR=/centinela/reports \
    AGENTE2_DATA_DIR=/data/agente2

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --uid 10002 --no-create-home agente \
 && mkdir -p /data/agente2 && chown agente /data/agente2

COPY agente_aprendizaje ./agente_aprendizaje
COPY experimentos ./experimentos

USER agente
EXPOSE 8102
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8102/api/salud', timeout=2)"

CMD ["uvicorn", "--factory", "agente_aprendizaje.api:crear_app", "--host", "0.0.0.0", "--port", "8102"]
