import json
from datetime import datetime, timedelta
from pathlib import Path

from app.core.pipeline import read_task_status
from app.core import pipeline


def test_read_task_status_heals_stale_rerender_running(tmp_path: Path, monkeypatch) -> None:
    task_id = "stale_rerender_task"
    task_dir = tmp_path / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    preview_path = task_dir / "variants" / "texture_1" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview")
    (task_dir / "automation_summary.json").write_text(
        json.dumps({"预览图": str(preview_path.resolve()), "裁片模板变体": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "completed",
                "progress": {
                    "phase": "completed",
                    "current_step": "rendering_variants",
                    "detail": {
                        "rerender_status": "running",
                        "rerender_current_step": "rendering_variants",
                    },
                },
                "updated_at": (datetime.now() - timedelta(minutes=5)).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(pipeline.settings, "storage_base_dir", tmp_path)

    status = read_task_status(task_id)

    assert status["progress"]["detail"]["rerender_status"] == "completed"
    assert status["progress"]["detail"]["rerender_current_step"] == "completed"


def test_read_task_status_heals_when_requested_variant_outputs_exist(tmp_path: Path, monkeypatch) -> None:
    task_id = "target_output_ready_task"
    task_dir = tmp_path / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    preview_path = task_dir / "variants" / "texture_1" / "preview.png"
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview")
    (task_dir / "automation_summary.json").write_text(
        json.dumps(
            {
                "预览图": str(preview_path.resolve()),
                "裁片模板变体": [
                    {
                        "纹理ID": "texture_1",
                        "预览图": str(preview_path.resolve()),
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (task_dir / "status.json").write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": "completed",
                "progress": {
                    "phase": "completed",
                    "current_step": "completed",
                    "detail": {
                        "rerender_status": "running",
                        "rerender_current_step": "rendering_variants",
                        "rerender_scope": {"texture_ids": ["texture_1"], "hero_changed": True},
                    },
                },
                "updated_at": datetime.now().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(pipeline.settings, "storage_base_dir", tmp_path)

    status = read_task_status(task_id)

    assert status["progress"]["detail"]["rerender_status"] == "completed"
    assert status["progress"]["detail"]["rerender_current_step"] == "completed"
