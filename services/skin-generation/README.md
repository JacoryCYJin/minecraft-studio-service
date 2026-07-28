# Skin Generation POC

This is a local-only module for the `Monadical Minecraft Skin Generator XL`
model. It belongs to the standalone Minecraft Studio Service repository and has
no runtime dependency on the website or production deployment.

## Scope

- Runs on Apple Silicon MPS only in this first POC.
- Generates one complete skin candidate at a time; batching is disabled to limit
  MPS memory pressure.
- Saves the raw 768×768 model output and a deterministic modern 64×64 PNG to
  `.artifacts/` for quality review. The model's top half is first extracted as
  its legacy 64×32 classic-arm UV atlas, then converted to the modern layout.
- Does not yet connect to the Vue editor, create user accounts, persist uploads,
  or expose a non-local network endpoint.

## Run locally

```bash
cd minecraft-studio-service
bash scripts/dev.sh skin-generation
```

Then open `http://127.0.0.1:8011/docs` and submit a `POST /generate` request,
for example:

```json
{
  "model": "classic",
  "prompt": "A character with short brown hair, a loose burgundy jacket, black shirt and dark cuffs"
}
```

The first generation downloads the model and can take several minutes. The
result response contains paths for the raw output and 64×64 derivative. Review
both in a Minecraft 3D preview before judging the model.

This is a developer POC endpoint, not the future user-facing prompt interface.
The released model's examples are English; Chinese prompt normalization is a
separate P1 concern and is deliberately not hidden behind this quality test.

## Manual test prompts

Use the same prompt once with `classic` and once with `slim` to compare only
the arm format. Start with the baseline case:

```text
A character with short brown hair, a loose burgundy jacket, black shirt and dark cuffs
```

Then use these two cases to inspect front/back continuity and overlay detail:

```text
A character with short black hair, a green hoodie, light sneakers, and matching front and back clothing details
```

```text
A blue and silver astronaut suit with a dark helmet overlay and a small jetpack design on the back
```

Review the PNG in both the 2D UV view and a 3D Minecraft preview. For `slim`,
specifically inspect both shoulders, cuffs and arm seams because its arms are a
deterministic adaptation of the Classic model output in this POC.

## Why raw and 64×64 files are both kept

The model documentation requires a 768×768 inference output. That image also
includes presentation renders; it is not a direct skin PNG. This POC extracts
the model's legacy 64×32 UV area and performs the documented Minecraft-format
conversion to a modern 64×64 classic skin before any quality evaluation.

The endpoint accepts `classic` and `slim`, matching the editor model selector.
The released Monadical model produces Classic UVs. For `slim`, the service
projects only the two arm regions into the Minecraft Slim 3-pixel-arm layout,
then records an adaptation warning in the response. It is suitable for local
integration testing, but must be judged separately before being treated as
native Slim-model quality.

## Check an artifact

```bash
cd minecraft-studio-service/services/skin-generation
.venv/bin/python scripts/verify-artifact.py .artifacts/<candidate>-skin.png
```

The check rejects invalid image format, blank/near-monochrome output and missing
Classic base layers. It does not claim to judge whether a design matches a
prompt; that remains the P0 visual-review criterion.

## References

- [Monadical model card](https://huggingface.co/monadical-labs/minecraft-skin-generator-sdxl)
- [Hugging Face MPS guidance](https://huggingface.co/docs/diffusers/en/optimization/mps)
