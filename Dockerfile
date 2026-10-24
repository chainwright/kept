FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY kept kept
COPY web web
ENV KEPT_DATA_DIR=/data KEPT_DEMO=1
EXPOSE 8000
CMD ["uvicorn", "kept.web:app", "--host", "0.0.0.0", "--port", "8000"]
