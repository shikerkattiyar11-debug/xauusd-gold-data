FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY live_collector.py .

ENV PYTHONUNBUFFERED=1

CMD ["python", "live_collector.py", "--output-dir", "/app/data"]
