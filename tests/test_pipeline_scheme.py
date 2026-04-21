import asyncio
from pathlib import Path

from app.core import pipeline


def test_run_pipeline_passes_hero_prompt_scheme_to_vision_and_prompt_generation(tmp_path, monkeypatch) -> None:
    calls: dict[str, str] = {}
    task_id = "scheme_b_task"
    work_dir = tmp_path / task_id
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "reference_image_url.txt").write_text("https://example.com/ref.png", encoding="utf-8")
    theme_image = work_dir / "theme.png"
    theme_image.write_bytes(b"fake")

    monkeypatch.setattr(pipeline.settings, "storage_base_dir", tmp_path)

    class FakeVisionService:
        async def analyze_theme_image(self, image_path, garment_type="T恤", season="spring/summer", user_prompt="", hero_prompt_scheme="b"):
            calls["vision"] = hero_prompt_scheme
            return {"generated_prompts": {"hero_motif_1": "hero", "texture_1": "t1", "texture_2": "t2", "texture_3": "t3"}}

    def fake_generate_texture_prompts(visual, out_dir, hero_prompt_scheme="b"):
        calls["prompt_generation"] = hero_prompt_scheme
        raise RuntimeError("stop after prompt generation")

    monkeypatch.setattr(pipeline, "VisionService", FakeVisionService)
    monkeypatch.setattr(pipeline, "generate_texture_prompts", fake_generate_texture_prompts)

    try:
        asyncio.run(
            pipeline.run_pipeline(
                task_id=task_id,
                theme_image_path=theme_image,
                garment_type="T恤",
                hero_prompt_scheme="b",
            )
        )
    except RuntimeError as exc:
        assert str(exc) == "stop after prompt generation"

    assert calls["vision"] == "b"
    assert calls["prompt_generation"] == "b"
