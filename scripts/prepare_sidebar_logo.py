"""Prepare anti-aliased sidebar assets; Pillow is needed only to regenerate them."""
from pathlib import Path

from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[1] / "pulpo" / "assets"
    with Image.open(assets / "pulpo-badge.png") as original:
        for size in (96, 128):
            display = original.convert("RGBA")
            display.thumbnail((size, size), Image.Resampling.LANCZOS)
            display.save(assets / f"pulpo-badge-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
