FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apk add --no-cache curl

COPY requirements.txt .
RUN python -m pip install -U pip setuptools wheel && \
    pip install -r requirements.txt

COPY . .
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s CMD curl -fsS http://127.0.0.1:8000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
