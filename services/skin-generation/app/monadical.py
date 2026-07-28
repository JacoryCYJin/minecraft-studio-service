from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image

from .validation import SkinValidation, validate_classic_skin


MODEL_ID = "monadical-labs/minecraft-skin-generator-sdxl"
RAW_SIZE = 768
SKIN_SIZE = 64


class SkinGenerationError(RuntimeError):
    """A recoverable POC generation error."""


@dataclass(frozen=True)
class SkinGenerationResult:
    request_id: str
    model: Literal["classic", "slim"]
    seed: int
    raw_width: int
    raw_height: int
    skin_png_path: str
    raw_preview_path: str
    validation: SkinValidation

    def as_response(self) -> dict[str, object]:
        return {
            "id": self.request_id,
            "model": self.model,
            "seed": self.seed,
            "raw_width": self.raw_width,
            "raw_height": self.raw_height,
            "skin_png_path": self.skin_png_path,
            "raw_preview_path": self.raw_preview_path,
            "validation": self.validation.as_response(),
        }


class MonadicalSkinGenerator:
    """Lazy local runner for the Monadical text-to-skin POC.

    The source model renders a 768×768 composite whose top half contains a
    legacy 64×32 skin atlas. The POC preserves the raw output, extracts that
    atlas, and deterministically expands it to the current 64×64 Minecraft
    format for review.
    """

    model_id = MODEL_ID

    def __init__(self, *, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self._pipeline = None
        self._torch = None
        self._device = None

    @property
    def loaded(self) -> bool:
        return self._pipeline is not None

    @property
    def device_name(self) -> str:
        if self._device is not None:
            return self._device
        return "unloaded"

    def _load_pipeline(self) -> None:
        if self._pipeline is not None:
            return

        try:
            import torch
            from diffusers import DiffusionPipeline
        except ImportError as error:
            raise SkinGenerationError("POC dependencies are missing. Run scripts/bootstrap.sh first.") from error

        if not torch.backends.mps.is_available():
            raise SkinGenerationError("This POC requires Apple Silicon MPS. CUDA/cloud support is not implemented yet.")

        # MPS is memory-constrained on this 18 GB development machine. float16,
        # attention slicing and serial requests are intentional POC constraints.
        try:
            pipeline = DiffusionPipeline.from_pretrained(MODEL_ID, torch_dtype=torch.float16)
            pipeline = pipeline.to("mps")
            pipeline.enable_attention_slicing()
            if hasattr(pipeline, "enable_vae_slicing"):
                pipeline.enable_vae_slicing()
        except Exception as error:  # pragma: no cover - model/provider runtime boundary
            raise SkinGenerationError(f"Unable to load {MODEL_ID}: {error}") from error

        self._torch = torch
        self._pipeline = pipeline
        self._device = "mps"

    @staticmethod
    def _build_prompt(prompt: str) -> str:
        # The model card's successful examples are concise English character
        # descriptions. Do not add UV-layout instructions: that made this
        # specialised model overfit to the presentation canvas in early tests.
        return prompt.strip()

    @staticmethod
    def _extract_legacy_atlas(raw: Image.Image) -> Image.Image:
        """Extract the model's legacy 64×32 atlas from its 768×768 composite."""
        if raw.size != (RAW_SIZE, RAW_SIZE):
            raise SkinGenerationError(f"Expected {RAW_SIZE}×{RAW_SIZE} model output, received {raw.width}×{raw.height}.")
        return raw.convert("RGBA").crop((0, 0, RAW_SIZE, RAW_SIZE // 2)).resize((SKIN_SIZE, 32), Image.Resampling.NEAREST)

    @staticmethod
    def _clear_legacy_overlay_background(legacy: Image.Image) -> Image.Image:
        """Restore transparent old-format head-overlay cells.

        Old 64×32 skins reserve six head-overlay cells. Generated images often
        fill them with the same flat background colour used by the two unused
        cells, which would otherwise become an opaque helmet in the editor.
        """
        skin = legacy.convert("RGBA").copy()
        reference_pixels = [
            skin.getpixel((x, y))[:3]
            for left in (32, 56)
            for x in range(left, left + 8)
            for y in range(0, 8)
        ]
        background = tuple(sum(pixel[channel] for pixel in reference_pixels) // len(reference_pixels) for channel in range(3))
        transparent_cells = (
            (40, 0, 48, 8), (48, 0, 56, 8),
            (32, 8, 40, 16), (40, 8, 48, 16), (48, 8, 56, 16), (56, 8, 64, 16),
        )

        for left, top, right, bottom in transparent_cells:
            for x in range(left, right):
                for y in range(top, bottom):
                    red, green, blue, alpha = skin.getpixel((x, y))
                    distance_squared = (red - background[0]) ** 2 + (green - background[1]) ** 2 + (blue - background[2]) ** 2
                    if distance_squared <= 2_500:
                        skin.putpixel((x, y), (red, green, blue, 0))

        return skin

    @staticmethod
    def _mirror_limb(source: Image.Image, destination: Image.Image, *, source_origin: tuple[int, int], destination_origin: tuple[int, int]) -> None:
        """Copy an old right limb into a modern left limb using Minecraft UV mirroring."""
        source_x, source_y = source_origin
        destination_x, destination_y = destination_origin
        faces = {
            "right": (0, 4, 4, 12),
            "front": (4, 4, 4, 12),
            "left": (8, 4, 4, 12),
            "back": (12, 4, 4, 12),
            "top": (4, 0, 4, 4),
            "bottom": (8, 0, 4, 4),
        }
        mirrored_face = {"right": "left", "left": "right", "front": "front", "back": "back", "top": "top", "bottom": "bottom"}

        for name, (left, top, width, height) in faces.items():
            source_box = (source_x + left, source_y + top, source_x + left + width, source_y + top + height)
            tile = source.crop(source_box).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            target_left, target_top, _, _ = faces[mirrored_face[name]]
            destination.alpha_composite(tile, (destination_x + target_left, destination_y + target_top))

    @classmethod
    def _legacy_to_modern_skin(cls, legacy: Image.Image) -> Image.Image:
        """Convert a valid classic 64×32 skin to a transparent modern 64×64 skin."""
        if legacy.size != (64, 32):
            raise SkinGenerationError(f"Expected a 64×32 legacy atlas, received {legacy.width}×{legacy.height}.")
        modern = Image.new("RGBA", (SKIN_SIZE, SKIN_SIZE), (0, 0, 0, 0))
        modern.alpha_composite(cls._clear_legacy_overlay_background(legacy), (0, 0))
        cls._mirror_limb(legacy, modern, source_origin=(0, 16), destination_origin=(16, 48))
        cls._mirror_limb(legacy, modern, source_origin=(40, 16), destination_origin=(32, 48))
        return modern

    @staticmethod
    def _copy_slim_face(source: Image.Image, target: Image.Image, *, source_box: tuple[int, int, int, int], destination: tuple[int, int], narrow: bool) -> None:
        """Copy one Classic arm face into its Minecraft Slim UV position."""
        face = source.crop(source_box)
        if narrow:
            narrowed = Image.new("RGBA", (3, face.height), (0, 0, 0, 0))
            narrowed.paste(face.crop((0, 0, 2, face.height)), (0, 0))
            narrowed.paste(face.crop((3, 0, 4, face.height)), (2, 0))
            face = narrowed
        target.alpha_composite(face, destination)

    @classmethod
    def _project_classic_arm_to_slim(cls, source: Image.Image, target: Image.Image, *, origin: tuple[int, int]) -> None:
        """Write one 4-pixel Classic arm as the standard 3-pixel Slim UV mesh."""
        origin_x, origin_y = origin
        classic_faces = {
            "top": (4, 0, 4, 4), "bottom": (8, 0, 4, 4),
            "right": (0, 4, 4, 12), "front": (4, 4, 4, 12),
            "left": (8, 4, 4, 12), "back": (12, 4, 4, 12),
        }
        slim_destinations = {
            "top": (4, 0), "bottom": (7, 0), "right": (0, 4),
            "front": (4, 4), "left": (7, 4), "back": (11, 4),
        }
        for name, (left, top, width, height) in classic_faces.items():
            cls._copy_slim_face(
                source,
                target,
                source_box=(origin_x + left, origin_y + top, origin_x + left + width, origin_y + top + height),
                destination=(origin_x + slim_destinations[name][0], origin_y + slim_destinations[name][1]),
                narrow=name in {"top", "bottom", "front", "back"},
            )

    @classmethod
    def _classic_to_slim_skin(cls, classic: Image.Image) -> Image.Image:
        """Create a technically valid Slim skin from the model's Classic output."""
        if classic.size != (SKIN_SIZE, SKIN_SIZE):
            raise SkinGenerationError(f"Expected a {SKIN_SIZE}×{SKIN_SIZE} Classic skin, received {classic.width}×{classic.height}.")
        slim = classic.convert("RGBA").copy()
        for left, top, right, bottom in ((40, 16, 56, 32), (40, 32, 56, 48), (32, 48, 48, 64), (48, 48, 64, 64)):
            slim.paste((0, 0, 0, 0), (left, top, right, bottom))
        for origin in ((40, 16), (40, 32), (32, 48), (48, 48)):
            cls._project_classic_arm_to_slim(classic, slim, origin=origin)
        return slim

    def generate(
        self,
        *,
        request_id: str,
        prompt: str,
        model: Literal["classic", "slim"],
        seed: int | None,
    ) -> SkinGenerationResult:
        self._load_pipeline()
        assert self._pipeline is not None and self._torch is not None

        actual_seed = seed if seed is not None else secrets.randbelow(2_147_483_648)
        generator = self._torch.Generator(device="mps").manual_seed(actual_seed)
        try:
            raw = self._pipeline(
                prompt=self._build_prompt(prompt),
                height=RAW_SIZE,
                width=RAW_SIZE,
                num_inference_steps=50,
                guidance_scale=7.5,
                generator=generator,
            ).images[0]
        except Exception as error:  # pragma: no cover - model/runtime boundary
            raise SkinGenerationError(f"Model inference failed: {error}") from error

        legacy = self._extract_legacy_atlas(raw)
        skin = self._legacy_to_modern_skin(legacy)
        if model == "slim":
            skin = self._classic_to_slim_skin(skin)
        validation = validate_classic_skin(skin, model=model)
        if model == "slim" and validation.status == "passed":
            validation = SkinValidation(
                validation.status,
                (*validation.warnings, "Slim arms were deterministically adapted from the Classic model output."),
            )
        if validation.status != "passed":
            raise SkinGenerationError("Generated result failed technical skin validation: " + " ".join(validation.warnings))
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        raw_name = f"{request_id}-raw.png"
        skin_name = f"{request_id}-skin.png"
        raw.convert("RGBA").save(self.artifacts_dir / raw_name)
        skin.save(self.artifacts_dir / skin_name)

        return SkinGenerationResult(
            request_id=request_id,
            model=model,
            seed=actual_seed,
            raw_width=raw.width,
            raw_height=raw.height,
            skin_png_path=f"/artifacts/{skin_name}",
            raw_preview_path=f"/artifacts/{raw_name}",
            validation=validation,
        )
