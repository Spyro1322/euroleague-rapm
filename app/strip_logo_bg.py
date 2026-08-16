#!/usr/bin/env python3
"""
Strip the solid background from the Canva logo export and write the three assets
the dashboard needs.

Canva's free plan blocks transparent-background PNG export, so the exported file
has the navy ground baked in. This samples the actual corner colour rather than
assuming white, knocks out everything within tolerance of it, trims the dead
margin, and writes the sizes app/landing.py and set_page_config expect.

USAGE
    python3 strip_logo_bg.py atb_logo_1024.png app/assets

    # wider tolerance if a halo survives around the mark
    python3 strip_logo_bg.py atb_logo_1024.png app/assets --tolerance 70

OUTPUTS
    app/assets/atb_lockup.png     full lockup, trimmed, transparent
    app/assets/atb_mark_512.png   512px square, for page_icon
    app/assets/atb_icon_64.png    64px square, favicon scale

CHECK BEFORE COMMITTING
    If the mark itself contains strokes close to the background colour, they will
    be punched through along with the background. Open atb_lockup.png over both
    a white and a dark ground before you push. The script prints how many pixels
    it removed — if that number is above ~85% of the image, the tolerance is too
    wide and you are eating the artwork.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def strip(src_path: Path, tolerance: float) -> Image.Image:
    src = Image.open(src_path).convert("RGBA")
    arr = np.array(src).astype(np.int16)

    # Sample the four corners and take the median, so a stray antialiased pixel
    # in any one corner cannot define the background colour.
    h, w = arr.shape[:2]
    corners = np.stack([
        arr[2, 2, :3], arr[2, w - 3, :3],
        arr[h - 3, 2, :3], arr[h - 3, w - 3, :3],
    ])
    bg = np.median(corners, axis=0)

    dist = np.sqrt(((arr[:, :, :3] - bg) ** 2).sum(axis=2))
    mask = dist < tolerance
    arr[mask, 3] = 0

    removed = mask.mean()
    print(f"background rgb{tuple(int(c) for c in bg)}  "
          f"tolerance {tolerance}  removed {removed:.1%} of pixels")
    if removed > 0.85:
        print("WARNING: over 85% removed — tolerance is probably eating the "
              "artwork. Inspect the output before committing.", file=sys.stderr)

    out = Image.fromarray(arr.astype(np.uint8))

    box = out.getbbox()          # bounding box of non-transparent pixels
    if box is None:
        sys.exit("ERROR: everything was removed. Lower --tolerance.")
    return out.crop(box)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path, help="Canva PNG export")
    ap.add_argument("outdir", type=Path, help="destination, e.g. app/assets")
    ap.add_argument("--tolerance", type=float, default=45.0,
                    help="euclidean RGB distance treated as background (default 45)")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"ERROR: {args.source} not found")

    args.outdir.mkdir(parents=True, exist_ok=True)
    lockup = strip(args.source, args.tolerance)

    lockup.save(args.outdir / "atb_lockup.png")

    # Square variants: paste the trimmed lockup onto a transparent square so the
    # aspect ratio is not distorted by a straight resize.
    side = max(lockup.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(lockup, ((side - lockup.width) // 2, (side - lockup.height) // 2))

    square.resize((512, 512), Image.LANCZOS).save(args.outdir / "atb_mark_512.png")
    square.resize((64, 64), Image.LANCZOS).save(args.outdir / "atb_icon_64.png")

    print(f"wrote atb_lockup.png {lockup.size[0]}x{lockup.size[1]}, "
          f"atb_mark_512.png, atb_icon_64.png -> {args.outdir}")


if __name__ == "__main__":
    main()
