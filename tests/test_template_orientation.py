from app.services.template_service import normalize_template_payloads
from app.services.template_service import load_json


def test_normalize_template_payloads_migrates_legacy_fields() -> None:
    pieces_payload = {
        "pieces": [
            {
                "piece_id": "piece_1",
                "pattern_orientation": 0,
            }
        ]
    }
    garment_map = {
        "pieces": [
            {
                "piece_id": "piece_1",
                "pattern_orientation": 180,
                "texture_direction": "transverse",
                "garment_role": "front_body",
                "symmetry_group": "sg_front",
                "same_shape_group": "ssg_front",
            }
        ]
    }

    normalized_pieces, normalized_map, issues = normalize_template_payloads(pieces_payload, garment_map)

    piece = normalized_pieces["pieces"][0]
    map_piece = normalized_map["pieces"][0]
    assert piece["piece_upright_rotation"] == 180
    assert map_piece["texture_flow"] == "across_piece_upright"
    assert map_piece["pair_alignment_mode"] == "front_seam_continuous"
    assert map_piece["orientation_source"] == "template_defined"
    assert any(issue["type"] == "template_orientation_migrated" for issue in issues)


def test_normalize_template_payloads_prefers_new_fields_on_conflict() -> None:
    pieces_payload = {"pieces": [{"piece_id": "piece_1"}]}
    garment_map = {
        "pieces": [
            {
                "piece_id": "piece_1",
                "piece_upright_rotation": 0,
                "pattern_orientation": 180,
                "texture_flow": "with_piece_upright",
                "texture_direction": "transverse",
                "pair_alignment_mode": "independent",
            }
        ]
    }

    _, normalized_map, issues = normalize_template_payloads(pieces_payload, garment_map)

    map_piece = normalized_map["pieces"][0]
    assert map_piece["piece_upright_rotation"] == 0
    assert map_piece["pattern_orientation"] == 0
    assert map_piece["texture_flow"] == "with_piece_upright"
    assert map_piece["texture_direction"] == "longitudinal"
    assert any(issue["type"] == "template_orientation_conflict" for issue in issues)


def test_back_body_can_explicitly_use_against_piece_upright() -> None:
    pieces_payload = {"pieces": [{"piece_id": "piece_back"}]}
    garment_map = {
        "pieces": [
            {
                "piece_id": "piece_back",
                "garment_role": "back_body",
                "piece_upright_rotation": 180,
                "texture_flow": "against_piece_upright",
            }
        ]
    }

    normalized_pieces, normalized_map, _ = normalize_template_payloads(pieces_payload, garment_map)

    assert normalized_map["pieces"][0]["texture_flow"] == "against_piece_upright"
    assert normalized_map["pieces"][0]["texture_direction"] == "longitudinal"
    assert normalized_pieces["pieces"][0]["texture_flow"] == "against_piece_upright"


def test_bfsk_piece_specific_texture_flow_matches_template_layout() -> None:
    garment_map = load_json("app/templates_data/BFSK26308XCJ01L/s/garment_map_s.json")
    by_id = {piece["piece_id"]: piece for piece in garment_map["pieces"]}

    assert by_id["piece_004_s"]["texture_flow"] == "with_piece_upright"
    assert by_id["piece_005_s"]["texture_flow"] == "with_piece_upright"
    assert by_id["piece_001_s"]["texture_flow"] == "with_piece_upright"
    assert by_id["piece_002_s"]["texture_flow"] == "against_piece_upright"
    assert by_id["piece_003_s"]["texture_flow"] == "against_piece_upright"


def test_dds_back_body_keeps_same_upright_flow_as_front_layout_reference() -> None:
    garment_map = load_json("app/templates_data/DDS26126XCJ01L/s/garment_map_s.json")
    by_id = {piece["piece_id"]: piece for piece in garment_map["pieces"]}

    assert by_id["piece_001_s"]["texture_flow"] == "with_piece_upright"
    assert by_id["piece_002_s"]["texture_flow"] == "with_piece_upright"
    assert by_id["piece_003_s"]["texture_flow"] == "with_piece_upright"
