"""The geometry the renderer cannot do for itself.

These are the sums behind `originX`/`originY`/`zoomLimit`. They are pure, so
they are worth pinning exactly: a wrong answer here does not raise, it just
quietly zooms at the wrong spot or crops a speech bubble, and nobody notices
until they watch the video.
"""
import pytest

from panelflow.v2.stage3 import geometry

HD = (1920, 1080)


def test_a_wider_than_frame_image_is_letterboxed_top_and_bottom():
    x, y, width, height = geometry.contain_rect((3840, 1080), HD)

    assert (x, width) == (0, 1920)          # fills the width
    assert (y, height) == (270, 540)        # and is bar'd above and below


def test_a_taller_than_frame_image_is_pillarboxed():
    x, y, width, height = geometry.contain_rect((1080, 1080), HD)

    assert (y, height) == (0, 1080)
    assert (x, width) == (420, 1080)


def test_the_centre_of_a_panel_is_the_centre_of_the_frame_whatever_the_aspect():
    for image_size in ((3840, 1080), (1080, 1080), (800, 1229), HD):
        assert geometry.to_frame_fraction((0.5, 0.5), image_size, HD) == (0.5, 0.5)


def test_a_focal_point_is_squeezed_toward_centre_by_letterboxing():
    """The panel occupies half the frame's height, so a point 100% down the
    *panel* is only 75% down the *frame*. Handing the kit the raw 1.0 would aim
    the zoom at the bottom of a black bar."""
    _, y = geometry.to_frame_fraction((0.5, 1.0), (3840, 1080), HD)

    assert y == 0.75


def test_regions_are_rebased_from_page_pixels_onto_their_panel():
    """The real shape from page 10: a panel cut out at (80, 317) whose region
    is recorded in page coordinates."""
    regions = geometry.regions_to_panel_fractions(
        [(152, 357, 279, 433)], bbox=[80, 317, 772, 1229])

    x1, y1, x2, y2 = regions[0]
    assert (round(x1, 4), round(y1, 4)) == (0.104, 0.0439)
    assert 0 < x1 < x2 < 1 and 0 < y1 < y2 < 1


def test_a_degenerate_bbox_is_dropped_rather_than_dividing_by_zero():
    assert geometry.regions_to_panel_fractions([(1, 2, 3, 4)], bbox=[5, 5, 5, 5]) == []


def _replay(point, pan, zoom, frame_size):
    """What the renderer does: origin + zoom * ((p + pan) - origin), with the
    origin at the frame centre. Mirrors AnimatedBase's transform so these tests
    check the property rather than restating the formula."""
    centre = (frame_size[0] / 2, frame_size[1] / 2)
    return tuple(centre[i] + zoom * ((point[i] + pan[i]) - centre[i]) for i in (0, 1))


def test_a_pan_starts_on_one_panel_and_ends_on_the_other():
    """The whole point of the travel: each end of the move lands its panel dead
    centre. Checked by replaying the renderer's transform, not by re-deriving."""
    left, right = (0.0, 0.2, 0.4, 0.8), (0.6, 0.2, 1.0, 0.8)
    image_size = (1600, 900)
    zoom, pan_start, pan_end = geometry.pan_camera(left, right, image_size, HD)

    for region, pan in ((left, pan_start), (right, pan_end)):
        x1, y1, x2, y2 = geometry.frame_box(region, image_size, HD)
        landed = _replay(((x1 + x2) / 2, (y1 + y2) / 2), pan, zoom, HD)
        assert landed == pytest.approx((960, 540))


def test_the_travel_is_the_distance_between_the_panels():
    left, right = (0.0, 0.2, 0.4, 0.8), (0.6, 0.2, 1.0, 0.8)
    _, pan_start, pan_end = geometry.pan_camera(left, right, (1600, 900), HD)

    assert pan_start[0] > pan_end[0]        # travelling rightward
    assert pan_start[1] == pytest.approx(pan_end[1])   # and not vertically


def test_a_pan_zooms_in_to_fit_the_panel():
    """Two panels each 40%x40% of a frame-shaped image: both axes allow 2.5x,
    so the camera pushes in that far and no further."""
    zoom, _, _ = geometry.pan_camera(
        (0.0, 0.3, 0.4, 0.7), (0.6, 0.3, 1.0, 0.7), (1920, 1080), HD)

    assert zoom == pytest.approx(2.5)


def test_a_panel_that_already_fills_an_axis_forbids_zooming():
    """Full-height panels: fitting is the constraint, so there is nowhere to
    push in to without cropping them."""
    zoom, _, _ = geometry.pan_camera(
        (0.0, 0.0, 0.4, 1.0), (0.6, 0.0, 1.0, 1.0), (1920, 1080), HD)

    assert zoom == 1.0


def test_a_pan_never_zooms_past_the_larger_panel():
    """Mismatched panels: a zoom that filled the small one would crop the big
    one, so the big one sets the ceiling."""
    small, large = (0.0, 0.0, 0.2, 0.2), (0.4, 0.0, 1.0, 1.0)
    zoom, _, _ = geometry.pan_camera(small, large, (1920, 1080), HD)

    x1, y1, x2, y2 = geometry.frame_box(large, (1920, 1080), HD)
    assert zoom == pytest.approx(min(1920 / (x2 - x1), 1080 / (y2 - y1)))


def test_a_pan_never_zooms_out():
    zoom, _, _ = geometry.pan_camera(
        (0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0), (1920, 1080), HD)

    assert zoom == 1.0


def test_a_degenerate_panel_does_not_divide_by_zero():
    zoom, _, _ = geometry.pan_camera(
        (0.5, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5), (1920, 1080), HD)

    assert zoom == 1.0


def test_nothing_to_protect_means_no_ceiling():
    assert geometry.zoom_limit([], HD, HD, (0.5, 0.5)) == float("inf")


def test_a_centred_region_in_the_middle_half_may_zoom_to_two():
    """A box spanning the middle 50% of the frame, zoomed about the centre:
    every edge is 0.25 from the origin and has 0.5 of room, so it may double."""
    limit = geometry.zoom_limit([(0.25, 0.25, 0.75, 0.75)], HD, HD, (0.5, 0.5))

    assert limit == pytest.approx(2.0)


def test_a_region_at_the_very_edge_forbids_zooming_at_all():
    limit = geometry.zoom_limit([(0.0, 0.0, 1.0, 1.0)], HD, HD, (0.5, 0.5))

    assert limit == 1.0


def test_zooming_away_from_lettering_is_what_crops_it():
    """Same region, origin pulled to the far right: the box's left edge now has
    much further to travel off-screen, so the ceiling drops below the centred
    case. This is the whole reason the limit depends on the origin."""
    centred = geometry.zoom_limit([(0.25, 0.25, 0.75, 0.75)], HD, HD, (0.5, 0.5))
    off_axis = geometry.zoom_limit([(0.25, 0.25, 0.75, 0.75)], HD, HD, (0.9, 0.5))

    assert off_axis < centred


def test_the_limit_never_asks_the_renderer_to_shrink():
    """Origin outside the region entirely — the maths would allow a ceiling
    under 1, which is meaningless: at zoom 1 everything is already visible."""
    limit = geometry.zoom_limit([(0.8, 0.8, 1.0, 1.0)], HD, HD, (0.0, 0.0))

    assert limit == 1.0


def test_a_limit_keeps_the_lettering_inside_the_frame():
    """The property the number exists for, checked by applying it the way the
    kit does: scale about the origin and look at where the corners land."""
    region = (0.3, 0.1, 0.6, 0.4)
    origin = (0.65, 0.45)
    limit = geometry.zoom_limit([region], (800, 1229), HD, origin)

    x1, y1, x2, y2 = region
    for corner in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
        point = geometry.to_frame_fraction(corner, (800, 1229), HD)
        for axis in (0, 1):
            landed = origin[axis] + (point[axis] - origin[axis]) * limit
            assert -1e-9 <= landed <= 1 + 1e-9


def test_a_cover_crop_fills_the_frame_and_keeps_its_aspect():
    """A tall panel cropped for a 16:9 thumbnail: the full width survives and
    the height is cut to match, because cover never leaves a bar."""
    x1, y1, x2, y2 = geometry.cover_box((400, 800), HD, (0.5, 0.5))

    assert (x1, x2) == (0, 400)
    assert (y2 - y1) == round(400 * 1080 / 1920)


def test_a_cover_crop_frames_the_focal_point():
    """The whole reason the focal point is passed: the subject is at the top of
    this panel, so the window must sit at the top, not centre."""
    _, centred_top, _, _ = geometry.cover_box((400, 800), HD, (0.5, 0.5))
    _, high_top, _, _ = geometry.cover_box((400, 800), HD, (0.5, 0.1))

    assert high_top < centred_top
    assert high_top == 0        # clamped: there is no artwork above the panel


def test_a_cover_crop_never_reaches_past_the_artwork():
    for focal in ((0.0, 0.0), (1.0, 1.0), (0.5, 0.99)):
        x1, y1, x2, y2 = geometry.cover_box((400, 800), HD, focal)
        assert 0 <= x1 < x2 <= 400
        assert 0 <= y1 < y2 <= 800


def test_a_wide_image_is_cut_on_the_sides_instead():
    """The other axis binds: a very wide page keeps its full height."""
    x1, y1, x2, y2 = geometry.cover_box((4000, 1000), HD, (0.5, 0.5))

    assert (y1, y2) == (0, 1000)
    assert (x2 - x1) == round(1000 * 1920 / 1080)
