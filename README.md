# Photo Grid API

FastAPI service that generates 1:1 product photo grids with Arabic text overlay (Cairo font).

Takes an array of photo URLs, arranges them in an optimal grid minimizing crop loss while targeting a square aspect ratio, and overlays the product name.

## Quick Start

```bash
# Local
pip install -r requirements.txt
uvicorn main:app --reload

# Docker
docker compose up --build

# Railway
railway up
```

## API Endpoints

### `GET /health`
Health check.

### `POST /generate`
Returns JPEG image directly.

```bash
curl -X POST http://localhost:8000/generate \
  -H "Content-Type: application/json" \
  -d '{
    "photos": [
      "https://example.com/photo1.jpg",
      "https://example.com/photo2.jpg"
    ],
    "chatid": "26428228773443927",
    "item_name": "كنبة ثلاثية فلوريدا"
  }' --output grid.jpg
```

### `POST /generate/json`
Returns JSON with base64-encoded image. Best for n8n / Make / webhook integrations.

```bash
curl -X POST http://localhost:8000/generate/json \
  -H "Content-Type: application/json" \
  -d '{
    "photos": ["https://example.com/photo1.jpg"],
    "chatid": "123",
    "item_name": "طاولة سفرة"
  }'
```

Response:
```json
{
  "chatid": "123",
  "item_name": "طاولة سفرة",
  "image_base64": "/9j/4AAQ...",
  "size_bytes": 142857,
  "processing_time": "1.23s"
}
```

### `POST /generate/batch`
Process multiple items. Returns JSON array with base64 images.

```bash
curl -X POST http://localhost:8000/generate/batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"photos": ["..."], "chatid": "1", "item_name": "كنبة"},
      {"photos": ["..."], "chatid": "2", "item_name": "طاولة"}
    ]
  }'
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `GRID_TARGET_SIZE` | `1200` | Output image size (px) |
| `GRID_JPEG_QUALITY` | `92` | JPEG quality (1-100) |
| `GRID_MAX_PHOTOS` | `10` | Max photos per request |
| `GRID_DOWNLOAD_TIMEOUT` | `30` | Image download timeout (s) |
| `GRID_FONT_PATH` | auto | Path to .ttf font file |

## Deployment

**Railway:** Push to GitHub → connect repo → Railway auto-detects `railway.toml`.

**Render:** Push to GitHub → connect repo → Render auto-detects `render.yaml`.

**Docker (any host):**
```bash
docker build -t photo-grid-api .
docker run -p 8000:8000 photo-grid-api
```

## Interactive Docs

Once running, visit `http://localhost:8000/docs` for Swagger UI.
