"""Image utilities: palette extraction, theme image resolution, etc.

Ported and simplified from existing skill scripts.
"""
import base64
import hashlib
import os
import re
import shutil
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def extract_palette(path: Path, count: int = 8) -> list[str]:
    """Extract dominant palette from theme image."""
    from collections import Counter
    with Image.open(path).convert("RGB") as img:
        sample = img.resize((160, 160), Image.Resampling.LANCZOS)
        quantized = sample.quantize(colors=max(count, 4), method=Image.Quantize.MEDIANCUT)
        palette = quantized.getpalette() or []
        used = Counter(quantized.getdata())
        colors = []
        for index, _ in used.most_common(count * 2):
            offset = index * 3
            if offset + 2 >= len(palette):
                continue
            rgb = tuple(palette[offset : offset + 3])
            if max(rgb) - min(rgb) < 8 and sum(rgb) < 45:
                continue
            colors.append(rgb_to_hex(rgb))
            if len(colors) == count:
                break
        return colors


def resolve_theme_image(value: str, out_dir: str | Path) -> Path | None:
    """Resolve a theme image reference into a stable local file."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # data URI / base64
    if value.startswith("data:image/"):
        header, _, payload = value.partition(",")
        if payload:
            match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64", header)
            suffix = f".{match.group(1).lower()}" if match else ".png"
            if suffix == ".jpeg":
                suffix = ".jpg"
            raw = base64.b64decode(payload)
            digest = hashlib.sha256(raw).hexdigest()[:12]
            dest = out_path / f"theme_image_base64_{digest}{suffix}"
            dest.write_bytes(raw)
            return dest.resolve()
        return None

    # URL
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in {"http", "https", "file"}:
        if parsed.scheme == "file":
            src = Path(urllib.request.url2pathname(parsed.path))
            return _copy_stable(src, out_path)
        suffix = ".png"
        if parsed.path:
            ext = Path(parsed.path).suffix.lower()
            if ext in IMAGE_EXTS:
                suffix = ext
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
        dest = out_path / f"theme_image_url_{digest}{suffix}"
        if not dest.exists():
            req = urllib.request.Request(value, headers={"User-Agent": "auto-garment-web/1.0"})
            with urllib.request.urlopen(req, timeout=60) as response:
                dest.write_bytes(response.read())
        return dest.resolve()

    # Local file
    path = Path(value).expanduser()
    if path.exists():
        return _copy_stable(path, out_path)

    return None


def _safe_suffix(path: Path, fallback: str = ".png") -> str:
    suffix = path.suffix.lower()
    return suffix if suffix in IMAGE_EXTS else fallback


def _copy_stable(src: Path, out_dir: Path) -> Path:
    src = src.expanduser().resolve()
    if src.is_dir():
        images = sorted(
            p for p in src.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith(".")
        )
        if images:
            src = images[0]
    digest = file_sha256(src)[:12]
    dest = out_dir / f"theme_image_{digest}{_safe_suffix(src)}"
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return dest.resolve()


# ---------------------------------------------------------------------------
# Thumbnail generation
# ---------------------------------------------------------------------------

THUMB_SIZES = {
    "reference": (400, 400),
    "preview": (800, 800),
    "piece": (400, 400),
}


def generate_thumbnail(
    src_path: str | Path,
    dest_path: str | Path,
    max_size: tuple[int, int] = (400, 400),
    quality: int = 85,
) -> Path:
    """Generate a thumbnail from source image, preserving aspect ratio.

    Returns the destination path. If source does not exist, raises FileNotFoundError.
    """
    src = Path(src_path)
    dest = Path(dest_path)
    if not src.exists():
        raise FileNotFoundError(f"Thumbnail source not found: {src}")

    dest.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src) as img:
        # Convert palette/images to RGB/RGBA for consistent handling
        if img.mode in ("P", "1", "L", "LA"):
            if img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
        elif img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # Use PNG for images with transparency, JPEG for others to save size
        has_alpha = img.mode == "RGBA"
        if has_alpha:
            # Keep PNG for alpha
            img.save(dest, format="PNG", optimize=True)
        else:
            # Save as JPEG for smaller size; if dest already has .png suffix, keep it
            if dest.suffix.lower() == ".png":
                img.save(dest, format="PNG", optimize=True)
            else:
                img.convert("RGB").save(dest, format="JPEG", quality=quality, optimize=True)

    return dest.resolve()


def get_thumbnail_path(task_dir: Path, original_path: Path) -> Path:
    """Compute thumbnail path for an original image inside a task directory.

    Thumbnails are stored under {task_dir}/thumbnails/ mirroring the relative path.
    """
    try:
        rel = original_path.resolve().relative_to(task_dir.resolve())
    except ValueError:
        # Fallback: hash the path
        digest = hashlib.sha256(str(original_path).encode("utf-8")).hexdigest()[:12]
        return task_dir / "thumbnails" / f"{digest}.jpg"
    thumb = task_dir / "thumbnails" / rel
    # Ensure we use .jpg for opaque thumbs unless original was png and we want to keep it
    if thumb.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        thumb = thumb.with_suffix(".jpg")
    return thumb


def ensure_thumbnail(
    original_path: Path,
    task_dir: Path,
    max_size: tuple[int, int] = (400, 400),
) -> Path:
    """Ensure thumbnail exists; generate if missing. Returns thumbnail path."""
    thumb_path = get_thumbnail_path(task_dir, original_path)
    if thumb_path.exists():
        return thumb_path
    return generate_thumbnail(original_path, thumb_path, max_size=max_size)


def _thumb_size_for_role(role: str) -> tuple[int, int]:
    if role in ("preview", "front_pair_check", "preview_white"):
        return THUMB_SIZES["preview"]
    if role == "piece":
        return THUMB_SIZES["piece"]
    return THUMB_SIZES["reference"]
