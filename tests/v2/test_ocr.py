"""The OCR provider: reading the service's response. No grouping — which
lines share a bubble is 1.3's question, tested in test_stage1.py."""
import json

import pytest

from panelflow.v2.providers import ocr


# ---------------------------------------------------------------- response parsing

def test_text_and_box_are_read_from_the_real_response_shape():
    result = json.dumps({
        "text": "THE CITADEL",
        "results": [
            {"text": "THE CITADEL", "confidence": 0.97,
             "box": [[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]]},
        ],
    })
    assert ocr._entries(result) == [("THE CITADEL",
                                    [[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]])]


def test_low_confidence_text_is_dropped():
    result = json.dumps({"results": [
        {"text": "clear", "confidence": 0.9, "box": [[0, 0], [10, 0], [10, 10], [0, 10]]},
        {"text": "?!", "confidence": 0.2, "box": [[0, 0], [5, 0], [5, 5], [0, 5]]},
    ]})
    assert len(ocr._entries(result)) == 1


def test_quad_corners_become_a_bbox():
    """PaddleOCR gives four corners, and they are not axis-aligned."""
    assert ocr._to_bbox([[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]]) == [247, 17, 547, 57]


def test_empty_result_is_no_regions():
    assert ocr._entries(None) == []
    assert ocr._entries(json.dumps({"results": []})) == []
