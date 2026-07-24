"""Where things land on screen. Pure arithmetic — no IO, no models.

The renderer draws a panel with `objectFit: contain`, so the panel is letterboxed
into the frame and the mapping from a point on the artwork to a point on screen
depends on both aspect ratios. Every function here works in *fractions* so it
never has to care what resolution the panel was saved at.

Two coordinate spaces come out of Stage 1 and they are not the same:

  - `focal_point` is a fraction of its own panel — [0.65, 0.45].
  - `text_regions` are absolute *page* pixels — a panel at bbox [80, 317, ...]
    has regions at y=357, in page space, not panel space.

`regions_to_panel_fractions` is the only place that difference is resolved.
"""


def contain_rect(image_size, frame_size):
    """Where a contained image lands in the frame, as (x, y, w, h) in frame px."""
    image_width, image_height = image_size
    frame_width, frame_height = frame_size
    scale = min(frame_width / image_width, frame_height / image_height)
    width, height = image_width * scale, image_height * scale
    return ((frame_width - width) / 2, (frame_height - height) / 2, width, height)


def to_frame_fraction(point, image_size, frame_size):
    """A point given as a fraction of the image -> a fraction of the frame.

    This is what the kit's originX/originY want: it draws into the whole frame,
    so a focal point that means 65% across the *panel* is somewhere else
    entirely once the panel is letterboxed.
    """
    x, y, width, height = contain_rect(image_size, frame_size)
    frame_width, frame_height = frame_size
    return ((x + point[0] * width) / frame_width,
            (y + point[1] * height) / frame_height)


def regions_to_panel_fractions(regions, bbox):
    """Page-pixel regions -> fractions of the panel that `bbox` cuts out.

    Regions whose box is degenerate are dropped rather than divided by zero.
    """
    x1, y1, x2, y2 = bbox
    width, height = x2 - x1, y2 - y1
    if width <= 0 or height <= 0:
        return []
    return [((rx1 - x1) / width, (ry1 - y1) / height,
             (rx2 - x1) / width, (ry2 - y1) / height)
            for rx1, ry1, rx2, ry2 in regions]


def frame_box(region, image_size, frame_size):
    """A region given as fractions of the image -> its box in frame pixels."""
    frame_width, frame_height = frame_size
    x1, y1 = to_frame_fraction((region[0], region[1]), image_size, frame_size)
    x2, y2 = to_frame_fraction((region[2], region[3]), image_size, frame_size)
    return (x1 * frame_width, y1 * frame_height,
            x2 * frame_width, y2 * frame_height)


def pan_camera(from_region, to_region, image_size, frame_size):
    """A camera that starts framed on one region and ends framed on another.

    Returns `(zoom, pan_start, pan_end)` for the kit's zoom/pan props, where
    both regions are fractions of the same image — in practice the two panels
    of a `pan` shot, inside the crop that spans them.

    The renderer transforms a point as `origin + zoom * ((p + pan) - origin)`.
    Putting the origin at the frame centre C makes the sum fall out: to land a
    region's centre P on C we need `pan = C - P`, with the zoom dropping out
    entirely, because scaling about C is the one thing that never moves C. So
    the travel and the zoom can be chosen independently, which is the only
    reason this stays simple.
    """
    frame_width, frame_height = frame_size
    centre = (frame_width / 2, frame_height / 2)
    boxes = [frame_box(region, image_size, frame_size)
             for region in (from_region, to_region)]

    # One zoom for the whole move, tight enough that the *larger* panel still
    # fits — a zoom that filled the smaller one would crop the other.
    zoom = float("inf")
    for x1, y1, x2, y2 in boxes:
        if x2 > x1 and y2 > y1:
            zoom = min(zoom, frame_width / (x2 - x1), frame_height / (y2 - y1))
    zoom = max(zoom, 1.0) if zoom != float("inf") else 1.0

    pans = [(centre[0] - (x1 + x2) / 2, centre[1] - (y1 + y2) / 2)
            for x1, y1, x2, y2 in boxes]
    return zoom, pans[0], pans[1]


def zoom_limit(regions, image_size, frame_size, origin):
    """The largest zoom that still keeps every region on screen.

    The renderer scales about `origin`, so a point P maps to
    `origin + (P - origin) * zoom`. Requiring that to stay within the frame
    bounds gives a ceiling per corner per axis; the tightest one wins.

    `regions` are fractions of the image, `origin` a fraction of the frame.
    Returns `inf` when nothing constrains the zoom, and never returns below 1 —
    at zoom 1 the whole panel is visible, so a smaller answer would mean the
    lettering is off-screen already and shrinking cannot be the fix.
    """
    limit = float("inf")
    for region in regions:
        x1, y1, x2, y2 = region
        for corner in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
            point = to_frame_fraction(corner, image_size, frame_size)
            for axis in (0, 1):
                delta = point[axis] - origin[axis]
                if delta > 0:
                    limit = min(limit, (1 - origin[axis]) / delta)
                elif delta < 0:
                    limit = min(limit, origin[axis] / -delta)
    return max(limit, 1.0)


def fill_crop(image_size, frame_size, focal, min_fill):
    """A focal-centred crop that stops a panel being drowned in letterbox.

    Drawn `contain`, a panel whose aspect is far from the frame's covers only
    `min(a, fa) / max(a, fa)` of the frame's short-changed axis — a wide panel
    in a portrait frame is a thin strip over a blurred bar, and unreadable. This
    cuts the panel toward the frame's aspect, around `focal`, *just far enough*
    to cover `min_fill` of that axis — never further, so only the excess that
    was going to be letterbox is lost and the rest of the panel survives.

    Returns None when the panel already covers `min_fill` (no crop needed); the
    caller then draws it whole. Otherwise returns pixels in the image's own
    space, ready for PIL's crop — a cover_box against a virtual frame of the
    capped aspect, so the clamping and focal framing are shared, not repeated.

    `focal` is a fraction of the image.
    """
    width, height = image_size
    frame_aspect = frame_size[0] / frame_size[1]
    aspect = width / height
    if min(aspect, frame_aspect) / max(aspect, frame_aspect) >= min_fill:
        return None
    # Move the aspect toward the frame's but leave a `min_fill` bar: a wide
    # panel keeps its height and is cut narrower (a larger target aspect than
    # the frame), a tall panel keeps its width and is cut shorter.
    capped = frame_aspect / min_fill if aspect > frame_aspect else frame_aspect * min_fill
    return cover_box(image_size, (capped, 1.0), focal)


def cover_box(image_size, frame_size, focal):
    """The box to cut from an image so it *fills* a frame, framed on `focal`.

    Cover, not contain — this is for a thumbnail, where a black bar is worse
    than a missing corner. Something has to be cut, and the focal point decides
    what survives: a thumbnail cropped away from its subject is the whole
    failure mode. Clamped to the image, so a focal point near an edge slides
    the window rather than reaching past the artwork.

    `focal` is a fraction of the image. Returns pixels in the image's own
    space, ready for PIL's crop.
    """
    width, height = image_size
    scale = max(frame_size[0] / width, frame_size[1] / height)
    # Rounded once, here: rounding the two edges separately can land them a
    # pixel apart from this, which is a box that no longer holds the frame's
    # aspect and so a thumbnail stretched by a hair.
    box_width, box_height = round(frame_size[0] / scale), round(frame_size[1] / scale)
    left = min(max(round(focal[0] * width - box_width / 2), 0), width - box_width)
    top = min(max(round(focal[1] * height - box_height / 2), 0), height - box_height)
    return (left, top, left + box_width, top + box_height)
