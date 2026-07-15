"""OCR text-region grouping. Pure geometry, no service."""
import json

import pytest

from panelflow.v2.providers import ocr

# Verbatim from a real page-2 OCR response: one box per line of text.
REAL_PAGE_2_LINES = [
    [247, 17, 547, 57],     # "THE CITADEL"          ┐ one caption block
    [33, 69, 766, 105],     # "BELOW - THE SANCTUM…" ┘
    [146, 609, 326, 636],   # "OH, AFANAF"           ┐
    [142, 640, 330, 667],   # "IS STILL THERE"       │
    [112, 672, 363, 699],   # "ALL RIGHT.WAITING"    │ one speech bubble
    [179, 701, 295, 729],   # "FOR THE"              │
    [186, 732, 288, 763],   # "NIGHT...."            ┘
]


def test_lines_of_one_bubble_become_one_box():
    """A crop could otherwise pass through the 5px gap between two lines,
    intersecting neither box while cutting the bubble in half."""
    assert ocr.group(REAL_PAGE_2_LINES) == [[33, 17, 766, 105], [112, 609, 363, 763]]


def test_far_apart_bubbles_stay_separate():
    assert len(ocr.group([[100, 100, 200, 130], [100, 400, 200, 430]])) == 2


def test_side_by_side_bubbles_stay_separate():
    """Same line height, no horizontal overlap: two speakers, not one bubble."""
    assert len(ocr.group([[100, 100, 200, 130], [400, 100, 500, 130]])) == 2


def test_grouping_is_order_independent():
    assert ocr.group(REAL_PAGE_2_LINES) == ocr.group(list(reversed(REAL_PAGE_2_LINES)))


def test_empty_and_single():
    assert ocr.group([]) == []
    assert ocr.group([[1, 2, 3, 4]]) == [[1, 2, 3, 4]]


# ---------------------------------------------------------------- response parsing

def test_boxes_are_read_from_the_real_response_shape():
    result = json.dumps({
        "text": "THE CITADEL",
        "results": [
            {"text": "THE CITADEL", "confidence": 0.97,
             "box": [[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]]},
        ],
    })
    assert ocr._boxes(result) == [[[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]]]


def test_low_confidence_text_is_dropped():
    result = json.dumps({"results": [
        {"text": "clear", "confidence": 0.9, "box": [[0, 0], [10, 0], [10, 10], [0, 10]]},
        {"text": "?!", "confidence": 0.2, "box": [[0, 0], [5, 0], [5, 5], [0, 5]]},
    ]})
    assert len(ocr._boxes(result)) == 1


def test_quad_corners_become_a_bbox():
    """PaddleOCR gives four corners, and they are not axis-aligned."""
    assert ocr._to_bbox([[248.0, 17.0], [547.0, 20.0], [547.0, 57.0], [247.0, 55.0]]) == [247, 17, 547, 57]


def test_empty_result_is_no_regions():
    assert ocr._boxes(None) == []
    assert ocr._boxes(json.dumps({"results": []})) == []
