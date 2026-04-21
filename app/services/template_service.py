"""Template loading and resolution."""
import json
from pathlib import Path

from app.config import settings


GARMENT_TYPE_MAP = {
    "t恤": "DDS26126XCJ01L",
    "t 恤": "DDS26126XCJ01L",
    "t-shirt": "DDS26126XCJ01L",
    "tee": "DDS26126XCJ01L",
    "衬衫": "DDS26126XCJ01L",
    "男士衬衫": "DDS26126XCJ01L",
    "shirt": "DDS26126XCJ01L",
    "防晒服": "BFSK26308XCJ01L",
    "防晒衣": "BFSK26308XCJ01L",
    "sun protection clothing": "BFSK26308XCJ01L",
}


def resolve_template(garment_type: str) -> dict | None:
    """Resolve garment type to template assets."""
    key = garment_type.strip().lower()
    template_id = GARMENT_TYPE_MAP.get(key)
    if not template_id:
        # Try loading index.json for fuzzy match
        index_path = settings.templates_dir / "index.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            for tmpl in index.get("templates", []):
                if key in [a.lower() for a in tmpl.get("aliases", [])]:
                    template_id = tmpl["template_id"]
                    break
    if not template_id:
        return None

    size_label = "s"
    tmpl_dir = settings.templates_dir / template_id / size_label
    if not tmpl_dir.exists():
        return None

    pieces_path = tmpl_dir / f"pieces_{size_label}.json"
    garment_map_path = tmpl_dir / f"garment_map_{size_label}.json"

    if not pieces_path.exists() or not garment_map_path.exists():
        return None

    return {
        "template_id": template_id,
        "size_label": size_label,
        "pieces_path": str(pieces_path.resolve()),
        "garment_map_path": str(garment_map_path.resolve()),
        "template_dir": str(tmpl_dir.resolve()),
    }


def load_json(path: str | Path) -> dict:
    text = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        text = text.replace("False", "false").replace("True", "true")
        return json.loads(text)
