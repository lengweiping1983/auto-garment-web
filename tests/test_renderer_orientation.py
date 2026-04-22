from pathlib import Path

from PIL import Image

from app.core.renderer import render_layered_piece


def _write_mask(path: Path, size: tuple[int, int]) -> str:
    Image.new("L", size, 255).save(path)
    return str(path)


def _write_texture(path: Path) -> str:
    img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
    img.putpixel((0, 0), (255, 0, 0, 255))
    img.putpixel((1, 0), (0, 255, 0, 255))
    img.putpixel((0, 1), (0, 0, 255, 255))
    img.putpixel((1, 1), (255, 255, 0, 255))
    img.save(path)
    return str(path)


def test_render_layered_piece_respects_piece_upright_rotation(tmp_path: Path) -> None:
    texture_path = _write_texture(tmp_path / "texture.png")
    mask_path = _write_mask(tmp_path / "mask.png", (2, 2))
    piece = {
        "piece_id": "back_body",
        "width": 2,
        "height": 2,
        "mask_path": mask_path,
        "piece_upright_rotation": 180,
        "texture_flow": "with_piece_upright",
    }
    plan = {
        "fill_type": "texture",
        "texture_id": "texture_1",
        "scale": 1.0,
        "rotation": 0,
        "offset_x": 0,
        "offset_y": 0,
    }
    textures = {"texture_1": {"path": texture_path}}

    rendered = render_layered_piece(piece, plan, textures, {}, {})

    assert rendered.getpixel((0, 0))[:3] == (255, 255, 0)
    assert rendered.getpixel((1, 0))[:3] == (0, 0, 255)
    assert rendered.getpixel((0, 1))[:3] == (0, 255, 0)
    assert rendered.getpixel((1, 1))[:3] == (255, 0, 0)


def test_render_layered_piece_applies_across_piece_upright_flow(tmp_path: Path) -> None:
    texture_path = _write_texture(tmp_path / "texture.png")
    mask_path = _write_mask(tmp_path / "mask.png", (2, 2))
    piece = {
        "piece_id": "collar",
        "width": 2,
        "height": 2,
        "mask_path": mask_path,
        "piece_upright_rotation": 0,
        "texture_flow": "across_piece_upright",
    }
    plan = {
        "fill_type": "texture",
        "texture_id": "texture_1",
        "scale": 1.0,
        "rotation": 0,
        "offset_x": 0,
        "offset_y": 0,
    }
    textures = {"texture_1": {"path": texture_path}}

    rendered = render_layered_piece(piece, plan, textures, {}, {})

    assert rendered.getpixel((0, 0))[:3] == (0, 255, 0)
    assert rendered.getpixel((1, 0))[:3] == (255, 255, 0)
    assert rendered.getpixel((0, 1))[:3] == (255, 0, 0)
    assert rendered.getpixel((1, 1))[:3] == (0, 0, 255)


def test_back_body_against_piece_upright_flips_relative_to_front_body(tmp_path: Path) -> None:
    texture_path = _write_texture(tmp_path / "texture.png")
    mask_path = _write_mask(tmp_path / "mask.png", (2, 2))
    textures = {"texture_1": {"path": texture_path}}
    plan = {
        "fill_type": "texture",
        "texture_id": "texture_1",
        "scale": 1.0,
        "rotation": 0,
        "offset_x": 0,
        "offset_y": 0,
    }

    front_piece = {
        "piece_id": "front_body",
        "width": 2,
        "height": 2,
        "mask_path": mask_path,
        "piece_upright_rotation": 0,
        "texture_flow": "with_piece_upright",
    }
    back_piece = {
        "piece_id": "back_body",
        "width": 2,
        "height": 2,
        "mask_path": mask_path,
        "piece_upright_rotation": 180,
        "texture_flow": "against_piece_upright",
    }

    front_rendered = render_layered_piece(front_piece, plan, textures, {}, {})
    back_rendered = render_layered_piece(back_piece, plan, textures, {}, {})

    assert front_rendered.getpixel((0, 0))[:3] == (255, 0, 0)
    assert back_rendered.getpixel((0, 0))[:3] == (255, 0, 0)
    assert front_rendered.getpixel((0, 1))[:3] == (0, 0, 255)
    assert back_rendered.getpixel((0, 1))[:3] == (0, 0, 255)
