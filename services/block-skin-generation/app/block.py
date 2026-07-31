from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from .validation import SkinValidation, clear_near_white_outer_pixels, clear_slim_unused_arm_pixels, validate_skin


MODEL_ID = "AliceKJ/BLOCKv0.6"
PREVIEW_SIZE = 512
SKIN_SIZE = 64
MAX_PREVIEW_BYTES = 20 * 1024 * 1024


class BlockGenerationError(RuntimeError):
    """A recoverable local BLOCK runtime error."""


@dataclass(frozen=True)
class BlockGenerationResult:
    request_id: str
    model: Literal["classic", "slim"]
    raw_width: int
    raw_height: int
    preview_input_path: str
    skin_png_path: str
    raw_preview_path: str
    validation: SkinValidation

    def as_response(self) -> dict[str, object]:
        return {
            "id": self.request_id,
            "model": self.model,
            "raw_width": self.raw_width,
            "raw_height": self.raw_height,
            "preview_input_path": self.preview_input_path,
            "skin_png_path": self.skin_png_path,
            "raw_preview_path": self.raw_preview_path,
            "validation": self.validation.as_response(),
        }


class BlockSkinGenerator:
    """Lazy BLOCK v0.6 runner for preview-image-to-skin testing on MPS."""

    model_id = MODEL_ID

    def __init__(self, *, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self._pipeline = None
        self._device = None

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def device_name(self) -> str:
        return self._device or "unloaded"

    def _load_pipeline(self) -> None:
        if self._pipeline is not None:
            return

        try:
            import torch
            from diffusers import Flux2KleinPipeline
        except ImportError as error:
            raise BlockGenerationError("BLOCK dependencies are missing. Run scripts/bootstrap.sh first.") from error

        if not torch.backends.mps.is_available():
            raise BlockGenerationError("The local BLOCK test currently requires Apple Silicon MPS.")

        try:
            pipeline = Flux2KleinPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.bfloat16)
            pipeline = pipeline.to("mps")
            pipeline.enable_attention_slicing()
            if hasattr(pipeline, "enable_vae_slicing"):
                pipeline.enable_vae_slicing()
            if hasattr(pipeline, "enable_vae_tiling"):
                pipeline.enable_vae_tiling()
        except Exception as error:  # pragma: no cover - model/runtime boundary
            raise BlockGenerationError(f"Unable to load {MODEL_ID}: {error}") from error

        self._pipeline = pipeline
        self._device = "mps"

    @staticmethod
    def _prepare_preview(content: bytes) -> Image.Image:
        if not content:
            raise BlockGenerationError("A preview image is required.")
        if len(content) > MAX_PREVIEW_BYTES:
            raise BlockGenerationError("Preview image exceeds the 20 MB local POC limit.")
        try:
            with Image.open(BytesIO(content)) as source:
                source.load()
                return source.convert("RGB").resize((PREVIEW_SIZE, PREVIEW_SIZE), Image.Resampling.LANCZOS)
        except (UnidentifiedImageError, OSError) as error:
            raise BlockGenerationError("Preview must be a readable image file.") from error

    @staticmethod
    def _build_prompt(*, prompt: str, model: Literal["classic", "slim"]) -> str:
        direction = prompt.strip()
        base = (
            "Image-to-image translation using the reference image. The reference shows the same 3D Minecraft "
            "character with front and back views in a single image. Generate the corresponding Minecraft skin UV "
            "atlas in 64x64 pixel-art UV layout. Flat shading, sharp pixel edges, no blur, no anti-aliasing. "
            "Keep consistent UV placement and mapping; match the same character design from the reference."
        )
        slim_instruction = (
            " Use the Java Slim 3-pixel arm UV layout and leave its unused arm slots transparent."
            if model == "slim"
            else ""
        )
        return f"{base}{slim_instruction} Additional direction: {direction}" if direction else f"{base}{slim_instruction}"

    @staticmethod
    def _to_skin_atlas(raw: Image.Image) -> Image.Image:
        """Convert BLOCK's square UV presentation into the editable 64×64 atlas."""
        return raw.convert("RGBA").resize((SKIN_SIZE, SKIN_SIZE), Image.Resampling.NEAREST)

    def generate(
        self,
        *,
        request_id: str,
        preview_content: bytes,
        prompt: str,
        model: Literal["classic", "slim"],
    ) -> BlockGenerationResult:
        self._load_pipeline()
        assert self._pipeline is not None

        preview = self._prepare_preview(preview_content)
        try:
            raw = self._pipeline(
                prompt=self._build_prompt(prompt=prompt, model=model),
                image=preview,
                num_inference_steps=30,
                guidance_scale=4.0,
            ).images[0]
        except Exception as error:  # pragma: no cover - model/runtime boundary
            raise BlockGenerationError(f"BLOCK inference failed: {error}") from error

        skin, cleared_outer_pixels = clear_near_white_outer_pixels(self._to_skin_atlas(raw))
        cleared_slim_pixels = 0
        if model == "slim":
            skin, cleared_slim_pixels = clear_slim_unused_arm_pixels(skin)
        validation = validate_skin(skin)
        if cleared_outer_pixels:
            validation = SkinValidation(
                validation.status,
                (*validation.warnings, f"Cleared {cleared_outer_pixels} near-white outer-layer pixels to transparency (RGB ≥ 245)."),
            )
        if model == "slim":
            validation = SkinValidation(
                validation.status,
                (
                    *validation.warnings,
                    f"Cleared {cleared_slim_pixels} unused Slim arm UV pixels for standard model detection; inspect Slim arm seams in a 3D preview.",
                ),
            )

        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        input_name = f"{request_id}-preview-input.png"
        raw_name = f"{request_id}-raw.png"
        skin_name = f"{request_id}-skin.png"
        preview.save(self.artifacts_dir / input_name)
        raw.convert("RGBA").save(self.artifacts_dir / raw_name)
        skin.save(self.artifacts_dir / skin_name)

        return BlockGenerationResult(
            request_id=request_id,
            model=model,
            raw_width=raw.width,
            raw_height=raw.height,
            preview_input_path=f"/artifacts/{input_name}",
            skin_png_path=f"/artifacts/{skin_name}",
            raw_preview_path=f"/artifacts/{raw_name}",
            validation=validation,
        )
