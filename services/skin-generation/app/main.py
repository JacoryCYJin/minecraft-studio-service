from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .monadical import MonadicalSkinGenerator, SkinGenerationError


ARTIFACTS_DIR = Path(os.getenv("MC_SKIN_POC_ARTIFACTS_DIR", ".artifacts"))
DEFAULT_DEV_ORIGINS = ("http://localhost:3001", "http://127.0.0.1:3001")
generator = MonadicalSkinGenerator(artifacts_dir=ARTIFACTS_DIR)
generation_lock = asyncio.Lock()

app = FastAPI(
    title="Minecraft Skin Generation POC",
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


class GenerationRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=800)
    model: Literal["classic", "slim"] = "classic"
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)


class GenerationResponse(BaseModel):
    id: str
    model: Literal["classic", "slim"]
    seed: int
    raw_width: int
    raw_height: int
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
async def generate(request: GenerationRequest) -> GenerationResponse:
    """Generate exactly one complete skin candidate.

    Apple Silicon MPS generation is intentionally serialized: Hugging Face notes
    that batching prompts on MPS can be unreliable and increases memory pressure.
    """

    request_id = uuid.uuid4().hex
    try:
        async with generation_lock:
            result = await asyncio.to_thread(
                generator.generate,
                request_id=request_id,
                prompt=request.prompt,
                model=request.model,
                seed=request.seed,
            )
    except SkinGenerationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:  # pragma: no cover - provider/runtime boundary
        raise HTTPException(status_code=500, detail="Local skin generation failed. Check the service log.") from error

    return GenerationResponse(**result.as_response())


@app.get("/artifacts/{artifact_name}")
def read_artifact(artifact_name: str) -> Response:
    """Expose only the flat POC artifact directory, never arbitrary local paths."""

    path = ARTIFACTS_DIR / Path(artifact_name).name
    if not path.is_file() or path.suffix.lower() != ".png":
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return Response(content=path.read_bytes(), media_type="image/png")
