# BLOCK Skin Conversion POC

This local-only module keeps BLOCK v0.6 separate from the existing Monadical
text-to-skin POC. It converts one supplied Minecraft character double-view
preview into a 64×64 skin candidate.

## Input and output

- Input: one character preview image containing matched front and back views.
- Optional input: a short prompt and `classic` or `slim` model hint.
- Output: the original preview, raw BLOCK image and nearest-neighbour 64×64
  skin derivative in this module's `.artifacts/` directory. In the standard
  Minecraft outer-layer UV slots only, pixels with all RGB channels at least
  `245` are made transparent. The base layer and grey, skin-tone or coloured
  outer pixels are preserved.

The input preview is normally made with the long conversation prompt in
`docs/skin-preview-conversation-prompt.md`. This module does not generate that
preview from text and does not connect to the website editor in this POC.

## Run locally

```bash
cd minecraft-studio-service
bash scripts/dev.sh block
```

Then open <http://127.0.0.1:8012/docs>, or submit a preview manually:

```bash
curl -X POST http://127.0.0.1:8012/generate \
  -F 'preview=@/absolute/path/to/character-preview.png' \
  -F 'model=classic' \
  -F 'prompt=Keep the hair, outfit colours and front/back continuity.'
```

The first run downloads the BLOCK v0.6 weights into this module's `.cache/`.
It can require substantial unified memory on Apple Silicon. Requests are
serialized, and VAE slicing/tiling are enabled to reduce peak MPS usage.

## Keep the two POCs separate

```bash
bash scripts/dev.sh monadical  # text -> Skin, port 8011
bash scripts/dev.sh block      # preview -> Skin, port 8012
bash scripts/dev.sh all        # both, only when explicitly needed
```

`skin-generation` remains a compatible alias for `monadical`.

### Apple Silicon memory note

On this 16 GB development Mac, keep only one model loaded while generating.
The scripts stay independent; stopping a service only releases its local model
process and does not remove its environment or weights:

```bash
bash scripts/dev.sh stop monadical
bash scripts/dev.sh block
# submit one BLOCK preview conversion
bash scripts/dev.sh stop block
bash scripts/dev.sh monadical
```

## Reference

- [BLOCK v0.6 model card](https://huggingface.co/AliceKJ/BLOCKv0.6)
