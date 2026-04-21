from pathlib import Path

from PIL import Image, ImageDraw

from app.services.front_split_service import create_front_split_assets


def _make_white_bg_subject(path: Path) -> None:
    img = Image.new("RGB", (220, 220), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((45, 20, 175, 210), fill=(40, 50, 70))
    draw.ellipse((80, 95, 140, 125), fill=(255, 255, 255))
    draw.ellipse((92, 70, 108, 86), fill=(255, 255, 255))
    draw.ellipse((112, 70, 128, 86), fill=(255, 255, 255))
    img.save(path)


def test_create_front_split_assets_removes_white_background_and_keeps_inner_whites(tmp_path: Path) -> None:
    source = tmp_path / "hero.png"
    _make_white_bg_subject(source)

    split_assets = create_front_split_assets(source, tmp_path)

    full = Image.open(split_assets["full"]).convert("RGBA")
    left = Image.open(split_assets["left"]).convert("RGBA")
    right = Image.open(split_assets["right"]).convert("RGBA")
    mask = Image.open(tmp_path / "assets" / "theme_front_mask.png").convert("L")
    debug_overlay = Image.open(tmp_path / "assets" / "theme_front_debug_overlay.png").convert("RGBA")

    assert full.getchannel("A").getbbox() is not None
    assert full.getpixel((0, 0))[3] == 0
    assert left.getchannel("A").getbbox() is not None
    assert right.getchannel("A").getbbox() is not None
    assert mask.getbbox() is not None
    assert debug_overlay.size == (220, 220)

    pixels = full.load()
    inner_white_pixels = []
    for y in range(full.height):
        for x in range(full.width):
            r, g, b, a = pixels[x, y]
            if a > 220 and min((r, g, b)) >= 245:
                inner_white_pixels.append((r, g, b, a))
    assert inner_white_pixels, "expected preserved internal white details such as teeth/highlights"
