FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ML_MODEL_PATH=/app/models/classificador_lotes.pkl

WORKDIR /app

RUN addgroup --system mlapi \
    && adduser --system --ingroup mlapi --home /app mlapi

COPY api_ml/requirements.txt ./api_ml/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement api_ml/requirements.txt

COPY --chown=mlapi:mlapi api_ml/ ./api_ml/
COPY --chown=mlapi:mlapi models/ ./models/

USER mlapi

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)"]

CMD ["uvicorn", "api_ml.main:app", "--host", "0.0.0.0", "--port", "8000"]

