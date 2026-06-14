FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt /app/apps/api/requirements.txt
COPY ../../requirements.txt /app/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY . /app

# Create data directory
RUN mkdir -p /app/data

ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/arl.db

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
