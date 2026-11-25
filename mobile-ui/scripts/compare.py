"""Put the Figma reference and a prototype screenshot side by side, in page-height strips.

Usage (from the project root):
    .venv/Scripts/python mobile-ui/scripts/compare.py design/compare/r1-proto-full.png r1
Writes design/compare/<tag>-compare-<n>.png (one per ~844 px of scroll) and <tag>-compare-full.png.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "design" / "nanovest-screens" / "01-us-stock-asset-page.png"
OUT = ROOT / "design" / "compare"
GAP, HEAD = 24, 36


def side_by_side(ref: Image.Image, proto: Image.Image) -> Image.Image:
    w = ref.width + proto.width + GAP * 3
    h = max(ref.height, proto.height) + HEAD + GAP
    im = Image.new("RGB", (w, h), (233, 237, 242))
    d = ImageDraw.Draw(im)
    d.text((GAP, 12), "Figma reference (375 px)", fill=(8, 47, 87))
    d.text((GAP * 2 + ref.width, 12), "Prototype (390 px)", fill=(8, 47, 87))
    im.paste(ref, (GAP, HEAD))
    im.paste(proto, (GAP * 2 + ref.width, HEAD))
    return im


def main(proto_path: str, tag: str) -> None:
    ref = Image.open(REF).convert("RGB")
    proto = Image.open(proto_path).convert("RGB")
    side_by_side(ref, proto).save(OUT / f"{tag}-compare-full.png")
    step = 844
    for i, y in enumerate(range(0, max(ref.height, proto.height), step), start=1):
        side_by_side(ref.crop((0, y, ref.width, min(y + step, ref.height))),
                     proto.crop((0, y, proto.width, min(y + step, proto.height)))
                     ).save(OUT / f"{tag}-compare-{i}.png")
        print("saved", OUT / f"{tag}-compare-{i}.png")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
