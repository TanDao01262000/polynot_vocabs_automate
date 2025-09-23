FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8001

# Start FastAPI app with auto-reload for development
CMD ["uvicorn", "vocab_api:app", "--host", "0.0.0.0", "--port", "8001", "--reload", "--reload-dir", "/app"]
