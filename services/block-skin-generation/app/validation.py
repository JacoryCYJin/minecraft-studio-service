from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from PIL import Image


SKIN_SIZE = 64
OUTER_LAYER_BOXES = (
    (32, 0, 64, 16),   # hat / head outer layer
    (16, 32, 40, 48),  # jacket / torso outer layer
    (40, 32, 56, 48),  # right arm outer layer
    (0, 32, 16, 48),   # right leg outer layer
    (48, 48, 64, 64),  # left arm outer layer
    (0, 48, 16, 64),   # left leg outer layer
)
OUTER_WHITE_THRESHOLD = 245
SLIM_UNUSED_ARM_BOXES = (
    (50, 16, 52, 20),  # right arm top/bottom spare column
    (54, 20, 56, 32),  # right arm front/back spare column
    (42, 48, 44, 52),  # left arm top/bottom spare column
    (46, 52, 48, 64),  # left arm front/back spare column
)


@dataclass(frozen=True)
class SkinValidation:
    status: str
    warnings: tuple[str, ...]

    def as_response(self) -> dict[str, str | list[str]]:
        return {"status": self.status, "warnings": list(self.warnings)}


def clear_near_white_outer_pixels(image: Image.Image) -> tuple[Image.Image, int]:
    """Make only near-white pixels in native outer-layer UV slots transparent.

    BLOCK currently returns an opaque RGB atlas. This POC cleanup deliberately
    does not touch the base layer, and it keeps any outer pixel whose R, G or B
    channel is below the threshold (such as grey hair, skin tones or shading).
    """
    atlas = image.convert("RGBA")
    pixels = atlas.load()
    cleared = 0

    for left, top, right, bottom in OUTER_LAYER_BOXES:
        for y in range(top, bottom):
            for x in range(left, right):
                red, green, blue, alpha = pixels[x, y]
                if alpha > 0 and red >= OUTER_WHITE_THRESHOLD and green >= OUTER_WHITE_THRESHOLD and blue >= OUTER_WHITE_THRESHOLD:
                    pixels[x, y] = (red, green, blue, 0)
                    cleared += 1

    return atlas, cleared


def clear_slim_unused_arm_pixels(image: Image.Image) -> tuple[Image.Image, int]:
    """Clear only the UV slots that do not exist on the Java Slim arm mesh.

    A 64×64 PNG carries no separate model-type flag. Standard skin viewers
    infer Slim from transparency in these unused slots, so BLOCK's opaque
    image output must be normalized when the caller explicitly selected Slim.
    """
    atlas = image.convert("RGBA")
    pixels = atlas.load()
    cleared = 0

    for left, top, right, bottom in SLIM_UNUSED_ARM_BOXES:
        for y in range(top, bottom):
            for x in range(left, right):
                if pixels[x, y][3] > 0:
                    pixels[x, y] = (0, 0, 0, 0)
                    cleared += 1

    return atlas, cleared


def validate_skin(image: Image.Image) -> SkinValidation:
    """Check only whether a BLOCK result is technically reviewable as a skin."""
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

    return SkinValidation("passed", ())
