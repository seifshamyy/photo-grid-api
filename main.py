"""
Photo Grid API
FastAPI service for generating product photo grids.
"""

import os
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

from grid_engine import generate_grid

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TARGET_SIZE = int(os.getenv("GRID_TARGET_SIZE", "1200"))
JPEG_QUALITY = int(os.getenv("GRID_JPEG_QUALITY", "92"))
FONT_PATH = os.getenv("GRID_FONT_PATH", None)
MAX_PHOTOS = int(os.getenv("GRID_MAX_PHOTOS", "10"))
DOWNLOAD_TIMEOUT = int(os.getenv("GRID_DOWNLOAD_TIMEOUT", "30"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("photo-grid-api")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Photo Grid API starting | target_size={TARGET_SIZE} quality={JPEG_QUALITY}")
    yield
    logger.info("Photo Grid API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Photo Grid API",
    description="Generate product photo grids with optimal 1:1 layout and Arabic text overlay.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class GridItem(BaseModel):
    photos: list[str] = Field(..., min_length=1, max_length=10, description="List of photo URLs")
    chatid: str = Field(..., description="Unique chat/item identifier")
    item_name: str = Field(..., description="Product name to overlay (supports Arabic)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "photos": [
                        "https://drive.usercontent.google.com/download?id=EXAMPLE1&export=download",
                        "https://drive.usercontent.google.com/download?id=EXAMPLE2&export=download",
                    ],
                    "chatid": "26428228773443927",
                    "item_name": "كنبة ثلاثية فلوريدا",
                }
            ]
        }
    }


class BatchRequest(BaseModel):
    items: list[GridItem] = Field(..., min_length=1, max_length=50)


class BatchResultItem(BaseModel):
    chatid: str
    status: str
    error: str | None = None
    image_base64: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    config: dict


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version="1.0.0",
        config={
            "target_size": TARGET_SIZE,
            "jpeg_quality": JPEG_QUALITY,
            "max_photos": MAX_PHOTOS,
        },
    )


@app.post(
    "/generate",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}}, "description": "Generated grid image"},
        422: {"description": "Validation error"},
        500: {"description": "Processing error"},
    },
)
def generate_single(item: GridItem):
    """
    Generate a single photo grid. Returns the JPEG image directly.
    """
    if len(item.photos) > MAX_PHOTOS:
        raise HTTPException(400, f"Max {MAX_PHOTOS} photos per item")

    try:
        t0 = time.time()
        jpeg_bytes = generate_grid(
            photo_urls=item.photos,
            item_name=item.item_name,
            target_size=TARGET_SIZE,
            quality=JPEG_QUALITY,
            font_path=FONT_PATH,
        )
        elapsed = time.time() - t0
        logger.info(f"Generated grid for chatid={item.chatid} | {len(item.photos)} photos | {elapsed:.2f}s | {len(jpeg_bytes)} bytes")

        return Response(
            content=jpeg_bytes,
            media_type="image/jpeg",
            headers={
                "Content-Disposition": f'inline; filename="{item.chatid}.jpg"',
                "X-ChatID": item.chatid,
                "X-Processing-Time": f"{elapsed:.2f}s",
            },
        )
    except Exception as e:
        logger.error(f"Error generating grid for chatid={item.chatid}: {e}")
        raise HTTPException(500, detail=str(e))


@app.post("/generate/batch", response_model=list[BatchResultItem])
def generate_batch(req: BatchRequest):
    """
    Generate grids for multiple items. Returns JSON with base64-encoded images.
    """
    import base64

    results = []
    for item in req.items:
        try:
            if len(item.photos) > MAX_PHOTOS:
                raise ValueError(f"Max {MAX_PHOTOS} photos per item")

            jpeg_bytes = generate_grid(
                photo_urls=item.photos,
                item_name=item.item_name,
                target_size=TARGET_SIZE,
                quality=JPEG_QUALITY,
                font_path=FONT_PATH,
            )
            b64 = base64.b64encode(jpeg_bytes).decode()
            results.append(BatchResultItem(chatid=item.chatid, status="ok", image_base64=b64))
            logger.info(f"Batch: generated grid for chatid={item.chatid}")

        except Exception as e:
            logger.error(f"Batch: error for chatid={item.chatid}: {e}")
            results.append(BatchResultItem(chatid=item.chatid, status="error", error=str(e)))

    return results


@app.post(
    "/generate/json",
    responses={
        200: {"content": {"application/json": {}}, "description": "Generated grid as base64"},
    },
)
def generate_single_json(item: GridItem):
    """
    Generate a single photo grid. Returns JSON with base64-encoded image.
    Useful for n8n / Make / webhook integrations.
    """
    import base64

    if len(item.photos) > MAX_PHOTOS:
        raise HTTPException(400, f"Max {MAX_PHOTOS} photos per item")

    try:
        t0 = time.time()
        jpeg_bytes = generate_grid(
            photo_urls=item.photos,
            item_name=item.item_name,
            target_size=TARGET_SIZE,
            quality=JPEG_QUALITY,
            font_path=FONT_PATH,
        )
        elapsed = time.time() - t0
        b64 = base64.b64encode(jpeg_bytes).decode()

        return JSONResponse({
            "chatid": item.chatid,
            "item_name": item.item_name,
            "image_base64": b64,
            "size_bytes": len(jpeg_bytes),
            "processing_time": f"{elapsed:.2f}s",
        })

    except Exception as e:
        logger.error(f"Error generating grid for chatid={item.chatid}: {e}")
        raise HTTPException(500, detail=str(e))
