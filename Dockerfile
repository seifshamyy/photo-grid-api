FROM python:3.12-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    unzip \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Download Cairo font directly
RUN mkdir -p /app/fonts && \
    curl -sL -o /app/fonts/Cairo-Regular.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/cairo/Cairo%5Bslnt%2Cwght%5D.ttf" && \
    cp /app/fonts/Cairo-Regular.ttf /app/fonts/Cairo-Bold.ttf

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY grid_engine.py .
COPY main.py .

# Env defaults
ENV GRID_TARGET_SIZE=1200
ENV GRID_JPEG_QUALITY=92
ENV GRID_MAX_PHOTOS=10
ENV GRID_DOWNLOAD_TIMEOUT=30
ENV GRID_FONT_PATH=""
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
