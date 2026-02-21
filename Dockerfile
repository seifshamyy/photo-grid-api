FROM python:3.12-slim

# System deps + Cairo font
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        fonts-cairo \
        libgl1-mesa-glx \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY grid_engine.py .
COPY main.py .

# Create fonts symlink for easier access
RUN mkdir -p /app/fonts && \
    ln -sf /usr/share/fonts/truetype/cairo/* /app/fonts/ 2>/dev/null || true

# Env defaults
ENV GRID_TARGET_SIZE=1200
ENV GRID_JPEG_QUALITY=92
ENV GRID_MAX_PHOTOS=10
ENV GRID_DOWNLOAD_TIMEOUT=30
ENV GRID_FONT_PATH=""
ENV PORT=8000

EXPOSE ${PORT}

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
