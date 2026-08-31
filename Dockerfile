FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN addgroup --system neria && adduser --system --ingroup neria neria

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini main.py ./

USER neria

EXPOSE 8000

CMD ["/bin/sh", "-c", "exec uvicorn app.application:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
