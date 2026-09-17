FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    AGENTE1_DATA_DIR=/data/agente1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --uid 10001 --no-create-home agente \
 && mkdir -p /data/agente1 && chown agente /data/agente1

COPY agente_identidad ./agente_identidad

USER agente
EXPOSE 8101
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8101/salud', timeout=2)"

CMD ["uvicorn", "--factory", "agente_identidad.api:crear_app", "--host", "0.0.0.0", "--port", "8101"]
