FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY live_collector.py cloud_server.py index.html .
COPY data ./data

ENV PYTHONUNBUFFERED=1

CMD ["python", "cloud_server.py"]
