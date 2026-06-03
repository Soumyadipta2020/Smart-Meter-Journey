FROM python:3.11-slim

WORKDIR /app

ENV MALLOC_ARENA_MAX=2 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data directories exist
RUN mkdir -p data/inputs data/outputs

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "120", "--max-requests", "150", "--max-requests-jitter", "30", "app:app"]
