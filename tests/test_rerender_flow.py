import asyncio
import json
from pathlib import Path

from fastapi import BackgroundTasks

from app.api import results, tasks
from app.core import pipeline


def _write_status(task_dir: Path, payload: dict) -> None:
    (task_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_delete_assets_mark_detail_as_deleted(tmp_path, monkeypatch) -> None:
    task_id = "deleted_asset_task"
    task_dir = tmp_path / task_id
    (task_dir / "neo_hero_motif").mkdir(parents=True, exist_ok=True)
    (task_dir / "neo_textures").mkdir(parents=True, exist_ok=True)
    (task_dir / "neo_hero_motif" / "hero_motif.png").write_bytes(b"hero")
    (task_dir / "neo_textures" / "texture_1.png").write_bytes(b"texture")
    _write_status(
        task_dir,
        {
            "task_id": task_id,
            "status": "completed",
            "progress": {
                "detail": {
                    "hero_motif": {"status": "completed", "path": "hero"},
                    "texture_1": {"status": "completed", "path": "texture"},
                }
            },
        },
    )

    monkeypatch.setattr(results.settings, "storage_base_dir", tmp_path)

    asyncio.run(results.delete_hero_motif(task_id))
    asyncio.run(results.delete_texture(task_id, "texture_1"))

    status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    assert status["progress"]["detail"]["hero_motif"]["status"] == "deleted"
    assert status["progress"]["detail"]["texture_1"]["status"] == "deleted"


def test_continue_render_keeps_completed_status_and_sets_rerender_state(tmp_path, monkeypatch) -> None:
    task_id = "continue_render_task"
    task_dir = tmp_path / task_id
    (task_dir / "theme_inputs").mkdir(parents=True, exist_ok=True)
    (task_dir / "neo_textures").mkdir(parents=True, exist_ok=True)
    (task_dir / "theme_inputs" / "theme_image.png").write_bytes(b"theme")
    (task_dir / "neo_textures" / "texture_1.png").write_bytes(b"t1")
    (task_dir / "neo_textures" / "texture_3.png").write_bytes(b"t3")
    (task_dir / "task_config.json").write_text(json.dumps({"garment_type": "T恤"}, ensure_ascii=False), encoding="utf-8")
    (task_dir / "dirty_assets.json").write_text(json.dumps({"hero": True, "textures": ["texture_1"]}, ensure_ascii=False), encoding="utf-8")
    _write_status(
        task_dir,
        {
            "task_id": task_id,
            "status": "completed",
            "progress": {"detail": {"hero_motif": {"status": "deleted", "path": ""}}},
        },
    )

    async def fake_run_pipeline(**kwargs):
        return None

    monkeypatch.setattr(tasks.settings, "storage_base_dir", tmp_path)
    monkeypatch.setattr(tasks, "run_pipeline", fake_run_pipeline)

    response = asyncio.run(tasks.continue_render(task_id, BackgroundTasks()))

    status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    assert response["rerender_status"] == "running"
    assert response["rerender_scope"]["texture_ids"] == ["texture_1", "texture_3"]
    assert status["status"] == "completed"
    assert status["progress"]["detail"]["rerender_status"] == "running"
    assert status["progress"]["detail"]["rerender_scope"]["hero_changed"] is True


def test_run_pipeline_rerender_preserves_completed_status_without_hero(tmp_path, monkeypatch) -> None:
    task_id = "pipeline_rerender_task"
    task_dir = tmp_path / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "theme_inputs").mkdir(exist_ok=True)
    (task_dir / "neo_textures").mkdir(exist_ok=True)
    (task_dir / "generated_texture_prompts").mkdir(exist_ok=True)
    (task_dir / "theme_inputs" / "theme_image.png").write_bytes(b"theme")
    (task_dir / "reference_image_url.txt").write_text("https://example.com/ref.png", encoding="utf-8")
    (task_dir / "visual_elements.json").write_text(json.dumps({"ok": True}, ensure_ascii=False), encoding="utf-8")
    (task_dir / "texture_prompts.json").write_text(json.dumps({"prompts": []}, ensure_ascii=False), encoding="utf-8")
    (task_dir / "generated_texture_prompts" / "texture_1.txt").write_text("texture one", encoding="utf-8")
    (task_dir / "generated_texture_prompts" / "texture_2.txt").write_text("texture two", encoding="utf-8")
    (task_dir / "neo_textures" / "texture_1.png").write_bytes(b"t1")
    (task_dir / "neo_textures" / "texture_2.png").write_bytes(b"t2")
    _write_status(
        task_dir,
        {
            "task_id": task_id,
            "status": "completed",
            "progress": {"detail": {"hero_motif": {"status": "deleted", "path": ""}}},
        },
    )

    pieces_path = tmp_path / "pieces.json"
    garment_map_path = tmp_path / "garment_map.json"
    pieces_path.write_text(json.dumps({"pieces": []}, ensure_ascii=False), encoding="utf-8")
    garment_map_path.write_text(json.dumps({"pieces": []}, ensure_ascii=False), encoding="utf-8")

    def fake_resolve_template(_garment_type):
        return {
            "pieces_path": str(pieces_path),
            "garment_map_path": str(garment_map_path),
            "template_dir": str(tmp_path),
        }

    def fake_build_texture_set(out_dir, texture_paths, hero_motif_path, prompt_map):
        path = out_dir / "texture_set.json"
        payload = {
            "texture_set_id": "fake",
            "textures": [
                {"texture_id": tid, "path": str(p.resolve())}
                for tid, p in texture_paths.items()
            ],
            "motifs": [],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def fake_build_fill_plan(*_args, **_kwargs):
        return {"pieces": []}

    def fake_render_all(_pieces_payload, _texture_set, _fill_plan, out_dir, _texture_set_path=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "front_pair_check.png").write_bytes(b"pair")
        (out_dir / "preview_white.jpg").write_bytes(b"white")
        return []

    def fake_compose_preview(_pieces_payload, _rendered, out_path):
        out_path.write_bytes(b"preview")
        return out_path

    async def fake_generate_variant_thumbnails(_variant_dir, _work_dir):
        return None

    monkeypatch.setattr(pipeline.settings, "storage_base_dir", tmp_path)
    monkeypatch.setattr(pipeline, "resolve_template", fake_resolve_template)
    monkeypatch.setattr(pipeline, "_build_texture_set", fake_build_texture_set)
    monkeypatch.setattr(pipeline, "build_fill_plan", fake_build_fill_plan)
    monkeypatch.setattr(pipeline, "render_all", fake_render_all)
    monkeypatch.setattr(pipeline, "compose_preview", fake_compose_preview)
    monkeypatch.setattr(pipeline, "_generate_variant_thumbnails", fake_generate_variant_thumbnails)

    asyncio.run(
        pipeline.run_pipeline(
            task_id=task_id,
            theme_image_path=task_dir / "theme_inputs" / "theme_image.png",
            garment_type="T恤",
            force_render=True,
            force_render_texture_ids=["texture_1", "texture_2"],
            allow_missing_hero=True,
        )
    )

    status = json.loads((task_dir / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["progress"]["detail"]["rerender_status"] == "completed"
    assert status["progress"]["detail"]["hero_motif"]["status"] == "deleted"
    assert status["progress"]["detail"]["texture_1"]["status"] == "completed"
    assert status["progress"]["detail"]["texture_3"]["status"] == "deleted"
