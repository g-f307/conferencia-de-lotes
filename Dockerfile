FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN addgroup --system botcity \
    && adduser --system --ingroup botcity --home /app botcity

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt \
    && python -m playwright install --with-deps chromium

COPY --chown=botcity:botcity bot.py ./
COPY --chown=botcity:botcity src/ ./src/
COPY --chown=botcity:botcity dados_entrada/ ./dados_entrada/
COPY --chown=botcity:botcity docs/index-lotes/ ./docs/index-lotes/

RUN mkdir -p logs relatorios artefatos /ms-playwright \
    && chown -R botcity:botcity logs relatorios artefatos /ms-playwright \
    && chmod -R a+rX /ms-playwright

USER botcity

CMD ["python", "bot.py"]
