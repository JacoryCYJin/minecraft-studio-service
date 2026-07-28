from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .block import BlockGenerationError, BlockSkinGenerator


ARTIFACTS_DIR = Path(os.getenv("MC_BLOCK_POC_ARTIFACTS_DIR", ".artifacts"))
DEFAULT_DEV_ORIGINS = ("http://localhost:3001", "http://127.0.0.1:3001")
generator = BlockSkinGenerator(artifacts_dir=ARTIFACTS_DIR)
generation_lock = asyncio.Lock()

app = FastAPI(
    title="Minecraft BLOCK Skin Conversion POC",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

allowed_origins = tuple(
    origin.strip()
    for origin in os.getenv("MC_STUDIO_ALLOWED_ORIGINS", ",".join(DEFAULT_DEV_ORIGINS)).split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class GenerationResponse(BaseModel):
    id: str
    model: Literal["classic", "slim"]
    raw_width: int
    raw_height: int
    preview_input_path: str
    skin_png_path: str
    raw_preview_path: str
    validation: dict[str, str | list[str]]


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "model": generator.model_id,
        "loaded": generator.loaded,
        "device": generator.device_name,
    }


@app.post("/generate", response_model=GenerationResponse)
async def generate(
    preview: UploadFile = File(...),
    prompt: str = Form(default=""),
    model: Literal["classic", "slim"] = Form(default="classic"),
) -> GenerationResponse:
    """Convert one supplied Minecraft front/back preview into a 64×64 skin candidate."""
    request_id = uuid.uuid4().hex
    try:
        preview_content = await preview.read()
        async with generation_lock:
            result = await asyncio.to_thread(
                generator.generate,
                request_id=request_id,
                preview_content=preview_content,
                prompt=prompt,
                model=model,
            )
    except BlockGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - provider/runtime boundary
        raise HTTPException(status_code=500, detail="Local BLOCK generation failed. Check the service log.") from error
    finally:
        await preview.close()

    return GenerationResponse(**result.as_response())


@app.get("/artifacts/{artifact_name}")
def read_artifact(artifact_name: str) -> Response:
    """Expose only generated local artifacts, never arbitrary filesystem paths."""
    path = ARTIFACTS_DIR / Path(artifact_name).name
    if not path.is_file() or path.suffix.lower() != ".png":
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return Response(content=path.read_bytes(), media_type="image/png")
