FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY kept kept
COPY web web
COPY skills skills
COPY demo_media demo_media
COPY demo_snapshot demo_snapshot
ENV KEPT_DATA_DIR=/tmp/kept-data KEPT_DEMO=1 KEPT_DAILY_BUDGET_USD=1.00 PYTHONUNBUFFERED=1
EXPOSE 8000
# hosts like Render pass the port in $PORT; locally it defaults to 8000
CMD ["sh", "-c", "uvicorn kept.web:app --host 0.0.0.0 --port ${PORT:-8000}"]
