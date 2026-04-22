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
    "texture_1": "seamless tileable visible repeat pattern, small repeat elements for all-over base print, full-body commercial apparel base fabric option, derive one dominant print-treatment language from the reference image such as ink layering, grain, worn edges, tonal breakup, or surface handling, no large motifs, no central placement composition, no text ",
    "texture_2": "seamless tileable visible repeat pattern, small repeat elements for all-over base print, full-body commercial apparel base fabric option, derive a second clearly different repeat organization from another visual family in the reference image, no large motifs, no central placement composition, no text ",
    "texture_3": "seamless tileable visible repeat pattern, small repeat elements for all-over base print, full-body commercial apparel base fabric option, derive a third reference-driven micro vocabulary from small local fragments found in the current image, still a full-body base fabric and not an accent texture, no large motifs, no central placement composition, no text "
}
