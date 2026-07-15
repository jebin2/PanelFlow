from panelflow.v2.stage1.ordering import sort_panels

TWO_BY_TWO = [[500, 10, 900, 400], [10, 10, 400, 400], [10, 450, 400, 900], [500, 450, 900, 900]]


def test_ltr_reads_left_to_right_then_down():
    assert sort_panels(TWO_BY_TWO, "ltr") == [
        [10, 10, 400, 400], [500, 10, 900, 400],
        [10, 450, 400, 900], [500, 450, 900, 900],
    ]


def test_rtl_flips_within_rows_but_rows_stay_top_down():
    assert sort_panels(TWO_BY_TWO, "rtl") == [
        [500, 10, 900, 400], [10, 10, 400, 400],
        [500, 450, 900, 900], [10, 450, 400, 900],
    ]


def test_slight_vertical_jitter_stays_one_row():
    jittered = [[320, 10, 600, 400], [10, 20, 300, 395]]
    assert sort_panels(jittered, "ltr") == [[10, 20, 300, 395], [320, 10, 600, 400]]


def test_wide_panel_below_two_narrow_ones():
    panels = [[10, 410, 600, 800], [10, 20, 300, 400], [320, 10, 600, 400]]
    assert sort_panels(panels, "ltr") == [[10, 20, 300, 400], [320, 10, 600, 400], [10, 410, 600, 800]]


def test_empty_and_single():
    assert sort_panels([], "ltr") == []
    assert sort_panels([[0, 0, 10, 10]], "rtl") == [[0, 0, 10, 10]]
