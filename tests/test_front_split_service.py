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


def _make_transparent_subject(path: Path) -> None:
    img = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((45, 20, 175, 210), fill=(40, 50, 70, 255))
    draw.ellipse((80, 95, 140, 125), fill=(255, 255, 255, 255))
    draw.ellipse((92, 70, 108, 86), fill=(255, 255, 255, 200))
    draw.ellipse((112, 70, 128, 86), fill=(255, 255, 255, 200))
    img.save(path)


def _make_faux_transparent_subject(path: Path) -> None:
    img = Image.new("RGB", (240, 240), (244, 244, 244))
    draw = ImageDraw.Draw(img)
    tile = 18
    for y in range(0, img.height, tile):
        for x in range(0, img.width, tile):
            if (x // tile + y // tile) % 2 == 0:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(232, 232, 232))

    draw.ellipse((50, 26, 190, 222), fill=(42, 58, 78))
    draw.ellipse((86, 102, 154, 134), fill=(250, 250, 250))
    draw.ellipse((102, 74, 118, 90), fill=(246, 246, 246))
    draw.ellipse((122, 74, 138, 90), fill=(246, 246, 246))

    # Simulate AI-generated soft anti-aliased edge glow instead of real transparency.
    for inset, tone in ((0, 214), (2, 224), (4, 234)):
        draw.ellipse((50 - inset, 26 - inset, 190 + inset, 222 + inset), outline=(tone, tone, tone), width=2)

    img.save(path)


def _make_large_enclosed_white_hole_subject(path: Path) -> None:
    img = Image.new("RGB", (260, 260), (248, 248, 248))
    draw = ImageDraw.Draw(img)

    # Build a connected dark silhouette with a large irregular white cavity
    # similar to trapped background between multiple visual elements.
    draw.ellipse((26, 24, 170, 182), fill=(58, 74, 92))
    draw.rounded_rectangle((118, 20, 236, 92), radius=26, fill=(58, 74, 92))
    draw.ellipse((140, 96, 244, 236), fill=(58, 74, 92))
    draw.rectangle((116, 72, 190, 150), fill=(58, 74, 92))

    # Large internal white hole that should be treated as background.
    draw.pieslice((92, 76, 212, 208), start=232, end=26, fill=(248, 248, 248))
    draw.ellipse((120, 102, 180, 162), fill=(248, 248, 248))

    # Small white highlights that should still survive.
    draw.ellipse((82, 86, 98, 102), fill=(248, 248, 248))
    draw.ellipse((104, 70, 116, 82), fill=(248, 248, 248))
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


def test_create_front_split_assets_preserves_existing_alpha_subject(tmp_path: Path) -> None:
    source = tmp_path / "hero_alpha.png"
    _make_transparent_subject(source)

    split_assets = create_front_split_assets(source, tmp_path)

    full = Image.open(split_assets["full"]).convert("RGBA")
    left = Image.open(split_assets["left"]).convert("RGBA")
    right = Image.open(split_assets["right"]).convert("RGBA")

    assert full.getchannel("A").getbbox() is not None
    assert left.getchannel("A").getbbox() is not None
    assert right.getchannel("A").getbbox() is not None
    assert full.getpixel((0, 0))[3] == 0

    semi_transparent_pixels = []
    bright_opaque_pixels = []
    pixels = full.load()
    for y in range(full.height):
        for x in range(full.width):
            r, g, b, a = pixels[x, y]
            if 0 < a < 255:
                semi_transparent_pixels.append((r, g, b, a))
            if a > 220 and min((r, g, b)) >= 245:
                bright_opaque_pixels.append((r, g, b, a))

    assert semi_transparent_pixels, "expected existing alpha softness to survive cropping"
    assert bright_opaque_pixels, "expected white details inside the subject to remain visible"


def test_create_front_split_assets_handles_faux_transparent_ai_background(tmp_path: Path) -> None:
    source = tmp_path / "hero_faux_alpha.png"
    _make_faux_transparent_subject(source)

    split_assets = create_front_split_assets(source, tmp_path)

    full = Image.open(split_assets["full"]).convert("RGBA")
    left = Image.open(split_assets["left"]).convert("RGBA")
    right = Image.open(split_assets["right"]).convert("RGBA")

    assert full.getchannel("A").getbbox() is not None
    assert left.getchannel("A").getbbox() is not None
    assert right.getchannel("A").getbbox() is not None
    assert full.getpixel((0, 0))[3] == 0

    nonzero = 0
    semi_transparent = 0
    near_white_opaque = 0
    pixels = full.load()
    for y in range(full.height):
        for x in range(full.width):
            r, g, b, a = pixels[x, y]
            if a > 0:
                nonzero += 1
            if 0 < a < 255:
                semi_transparent += 1
            if a > 220 and min((r, g, b)) >= 242:
                near_white_opaque += 1

    assert nonzero > 0, "expected extracted subject to remain after faux-alpha cleanup"
    assert semi_transparent > 0, "expected softened anti-aliased edge to survive extraction"
    assert near_white_opaque > 0, "expected internal bright details to survive faux-alpha extraction"


def test_create_front_split_assets_removes_large_enclosed_white_holes_but_keeps_small_highlights(tmp_path: Path) -> None:
    source = tmp_path / "hero_large_hole.png"
    _make_large_enclosed_white_hole_subject(source)

    split_assets = create_front_split_assets(source, tmp_path)

    full = Image.open(split_assets["full"]).convert("RGBA")
    mask = Image.open(tmp_path / "assets" / "theme_front_mask.png").convert("L")

    assert full.getchannel("A").getbbox() is not None
    assert mask.getbbox() is not None

    alpha = full.getchannel("A")
    alpha_px = alpha.load()
    pixels = full.load()

    # The large central white cavity should now be punched out as background.
    transparent_inside_hole = 0
    for y in range(118, 170):
        for x in range(126, 188):
            if alpha_px[x, y] <= 8:
                transparent_inside_hole += 1
    assert transparent_inside_hole > 800, "expected the large enclosed white hole to be removed as background"

    # Small white highlights should still remain visible and opaque.
    preserved_highlights = 0
    for y in range(full.height):
        for x in range(full.width):
            r, g, b, a = pixels[x, y]
            if a > 220 and min((r, g, b)) >= 244:
                preserved_highlights += 1
    assert preserved_highlights > 50, "expected small internal white highlights to be preserved"
