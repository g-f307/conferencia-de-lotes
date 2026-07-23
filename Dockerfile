FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system botcity \
    && adduser --system --ingroup botcity --home /app botcity

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY --chown=botcity:botcity bot.py ./
COPY --chown=botcity:botcity src/ ./src/
COPY --chown=botcity:botcity dados_entrada/ ./dados_entrada/

RUN mkdir -p logs relatorios \
    && chown -R botcity:botcity logs relatorios

USER botcity

CMD ["python", "bot.py"]
