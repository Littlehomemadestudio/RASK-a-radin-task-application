#!/usr/bin/env python3
"""Generate PWA icons for Rask (gold ring + 'R' on matte black)."""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
os.makedirs(OUT, exist_ok=True)

def find_font():
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def make_icon(size, fname, maskable=False):
    img = Image.new("RGBA", (size, size), (14, 14, 16, 255))
    draw = ImageDraw.Draw(img)
    # For maskable, keep important content inside 80% safe zone
    inset = int(size * 0.15) if maskable else int(size * 0.08)
    # Gold filled circle (maskable) or just ring (any)
    if maskable:
        draw.ellipse((inset, inset, size - inset, size - inset),
                     fill=(212, 175, 55, 255))
        text_color = (14, 14, 16, 255)
    else:
        # Ring on transparent-look background
        line_w = max(4, size // 32)
        draw.ellipse((inset, inset, size - inset, size - inset),
                     outline=(212, 175, 55, 255), width=line_w)
        text_color = (212, 175, 55, 255)
    # 'R' glyph
    fpath = find_font()
    if fpath:
        font = ImageFont.truetype(fpath, int(size * 0.55))
    else:
        font = ImageFont.load_default()
    text = "R"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
              text, fill=text_color, font=font)
    img.save(os.path.join(OUT, fname), "PNG")
    print(f"  {fname} ({size}x{size})")

print("Generating Rask PWA icons...")
make_icon(192, "icon-192.png")
make_icon(512, "icon-512.png")
make_icon(192, "icon-maskable-192.png", maskable=True)
make_icon(512, "icon-maskable-512.png", maskable=True)
# Also a small favicon-ish one
make_icon(32, "icon-32.png")
make_icon(16, "icon-16.png")
print("Done.")
