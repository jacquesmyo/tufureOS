FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "src.bot", "--config", "config.json"]
