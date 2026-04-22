"""Shared prompt fragments for auto-garment production.

Ported from scripts/prompt_blocks.py
"""

FRONT_EFFECT_NEGATIVE_EN = (
    "no garment mockup, no front-view clothing render, no fashion model, no mannequin, "
    "no person wearing garment, no on-body render, no T-shirt mockup, no product photo, no lookbook"
)

TEXTURE_NEGATIVE_EN = (
    "no animals, no characters, no faces, no people, no text, "
    "no labels, no captions, no titles, no words, no letters, no typography, no logo, no watermark, "
    "no house, no river, no full landscape scene, no scenery, no environment, no background scene, no poster composition, no sticker sheet, "
    "no harsh black outlines, no dense confetti, no neon colors, no muddy dark colors, "
    "no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no blurred background, "
    "no folds, no wrinkles, no draping, no creases, no shadows, no 3D fabric photography, no light variation across surface, "
    "no gradient backgrounds inside individual panels, no photographic realism, no vector flatness, no digital gradient, "
    "blurry, out of focus, smeared, smudged, vignette, distorted, deformed, low quality, jpeg artifacts, grainy, "
    + FRONT_EFFECT_NEGATIVE_EN
)

HERO_NEGATIVE_EN = (
    "text, labels, captions, titles, typography, words, letters, signage, logo, watermark, "
    "colored background, tinted backdrop, gradient background, plain light box, colored background box, filled rectangle, "
    "background art, scenery, landscape, environment, ground plane, floor, border, frame, extra objects, "
    "drop shadow, contact shadow, cast shadow, halo effect around subject, "
    "full illustration scene, poster composition, sticker sheet, garment mockup, fashion model, mannequin, "
    "person wearing garment, product photo, lookbook, vignette, "
    "botanical backdrop, foliage behind subject, painted wash behind subject, garden background, meadow background, "
    "blurry, out of focus, smeared, smudged, distorted, deformed, low quality, jpeg artifacts, grainy"
)

PANEL_DEFAULTS_EN = {
    "hero_motif_1": "foreground hero motif only, centered complete subject, preserve and recreate the primary subject from the user's reference image as much as possible, keep the recognizable silhouette, color identity, pose, proportions, and key visual details, full head and hair visible, full uncropped figure, pure white background, no shadow, no floor, no scenery, no background art, no extra objects, clean crisp edges, apparel placement graphic, apparel-safe print graphic, no text",
    "texture_1": "seamless tileable visible repeat pattern with concrete small botanical or geometric motifs on pale ground, stable low-to-medium density, clearly repeatable elements, commercial apparel base fabric, crisp clean repeat edges, sharp motif boundaries, high motif-ground separation, high print legibility, flat color, no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no blurred background, no haze, no fog, no soft focus, no low contrast, no distressed print effect, no scene, no landscape, no text, no logo, no watermark",
    "texture_2": "seamless tileable coordinating visible repeat pattern with concrete small motifs, lattice, linework, leaves, dots, or controlled geometric elements, stable repeat structure on light background, same palette, crisp clean repeat edges, sharp motif boundaries, high motif-ground separation, high print legibility, flat color, no abstract wash, no plain texture, no paper grain only, no gradient, no empty background, no tonal atmosphere only, no haze, no fog, no soft focus, no low contrast, no distressed print effect, no scene, no text, no logo, no watermark",
    "texture_3": "small scattered small repeat on light background, moderate density, crisp clean repeat edges, sharp motif boundaries, high print legibility, flat color, no haze, no fog, no soft focus, no low contrast, no distressed print effect, no text, no logo, no watermark"
}
