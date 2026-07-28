from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from PIL import Image


SKIN_SIZE = 64


@dataclass(frozen=True)
class SkinValidation:
    status: str
    warnings: tuple[str, ...]

    def as_response(self) -> dict[str, str | list[str]]:
        return {"status": self.status, "warnings": list(self.warnings)}


def validate_classic_skin(image: Image.Image, *, model: str = "classic") -> SkinValidation:
    """Reject technically unusable skin PNGs without trying to judge aesthetics."""
    if image.size != (SKIN_SIZE, SKIN_SIZE):
        return SkinValidation("failed", ("Skin must be exactly 64×64 pixels.",))
    if image.mode != "RGBA":
        return SkinValidation("failed", ("Skin must use RGBA pixels.",))

    pixels = list(image.getdata())
    visible_pixels = [pixel for pixel in pixels if pixel[3] > 0]
    if not visible_pixels:
        return SkinValidation("failed", ("Skin is fully transparent.",))
    if len(Counter(visible_pixels)) < 12:
        return SkinValidation("failed", ("Skin has too little colour information.",))

    # Classic base-layer areas that must be present for the current editor and
    # Minecraft's standard player mesh to show a complete character.
    base_areas = ((0, 0, 32, 16), (16, 16, 40, 32), (0, 16, 16, 32), (40, 16, 56, 32), (32, 48, 48, 64))
    for left, top, right, bottom in base_areas:
        total = (right - left) * (bottom - top)
        opaque = sum(image.getpixel((x, y))[3] > 0 for x in range(left, right) for y in range(top, bottom))
        is_slim_arm = model == "slim" and (left, top, right, bottom) in {(40, 16, 56, 32), (32, 48, 48, 64)}
        if opaque / total < (0.7 if is_slim_arm else 0.8):
            return SkinValidation("failed", ("Skin is missing a required base-layer area.",))

    warnings: list[str] = []
    outer_layer_pixels = [
        image.getpixel((x, y))[3]
        for x in range(0, 64)
        for y in range(32, 64)
    ]
    if not any(alpha > 0 for alpha in outer_layer_pixels):
        warnings.append("No body outer layer was generated; this is still a playable base skin.")

    return SkinValidation("passed", tuple(warnings))
