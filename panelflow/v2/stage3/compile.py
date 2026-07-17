"""3.2 compile: a validated direction plus its voice tracks become a manifest.

Nothing here decides anything. The director already chose the shots, the
animations and the travel; 3.1 already decided how long each one runs. This
turns those choices into the shape the renderer reads, which mostly means
arithmetic the renderer cannot do for itself:

  - `at_fraction` becomes `startSeconds`, which needs the voice duration.
  - a focal point on a panel becomes an origin on the *frame*, which needs the
    letterboxing.
  - a `pan` between two panels becomes a crop plus a camera.

The manifest is one file per target for the whole book. v1 rendered per page
and stamped `pageNumber` on each manifest, but nothing ever read it back.
"""
import os

from PIL import Image
from custom_logger import logger_config

from panelflow import config

from . import geometry

# Shorts are vertical, which is also what makes the renderer show its title
# card and progress bar — Root.tsx gates both on `height > width`.
FRAME = {"longform": (1920, 1080), "shorts": (1080, 1920)}

# Must match the kit's TRANSITION_FRAMES: the outgoing shot has to stay on
# screen for the whole overlap or the transition eats its final beat.
TRANSITION_FRAMES = 18
TRANSITION_SECONDS = TRANSITION_FRAMES / config.FPS

# An event is punctuation, not a phase — it hits and it is gone. The
# atmosphere events breathe a little longer than the impact ones, but even
# they resolve inside the shot.
EVENT_SECONDS = 0.6
EVENT_SECONDS_BY_TYPE = {"vignette_pulse": 1.2, "color_drain": 1.2,
                         "invert_flash": 0.35, "black_flash": 0.4,
                         "blur_pulse": 0.9}

# A wide panel in the portrait short is drawn as a thin strip over a blurred
# bar, unreadable, so we crop it toward the frame around its focal point. A
# ceiling, not a target — the crop stops the moment the panel covers this much
# of the short-changed axis, to lose as little of the artwork as possible. Only
# the portrait target crops: longform's tall panels would lose too much height,
# and its letterbox is far milder to begin with.
MIN_FRAME_FILL = 0.55


def run(assets, target, direction, voiced):
    """Build the Remotion manifest for one target. Returns the manifest dict."""
    frame = FRAME[target]
    shots = direction["shots"]
    panels = [_panel(assets, target, shot, voice, frame,
                     overlaps_next=_has_transition(shots[i + 1]) if i + 1 < len(shots) else False)
              for i, (shot, voice) in enumerate(zip(shots, voiced))]

    manifest = {
        "fps": config.FPS,
        "width": frame[0],
        "height": frame[1],
        "comicTitle": assets.load_book().get("title") or assets.name,
        "panels": panels,
    }
    # Cover art for the longform intro; the renderer falls back to the first
    # panel image when the book has no thumbnail.
    if os.path.exists(os.path.join(assets.folder, "thumbnail.jpg")):
        manifest["cover"] = "render_assets/thumbnail.jpg"
    # The director's end-card backdrop — a quiet aftermath panel, drawn dimmed
    # behind THE END. Optional: without it the card stays dark.
    outro = (direction.get("meta") or {}).get("outro") or {}
    if outro.get("page") is not None:
        panel = _find_panel(assets.load_page(outro["page"]), outro.get("panel"), outro["page"])
        manifest["outroImage"] = assets.rel_to_book(_panel_image(assets, outro["page"], panel))
    seconds = sum(panel["durationInSeconds"] for panel in panels)
    logger_config.info(
        f"3.2 {target}: {len(panels)} shot(s), {seconds:.1f}s at {frame[0]}x{frame[1]}")
    return manifest


def _has_transition(shot):
    return (shot.get("transition_in") or "none") != "none"


def _panel(assets, target, shot, voice, frame, overlaps_next):
    image_path, regions, camera, focal = _resolve(assets, target, shot, frame)
    size = _image_size(image_path)

    panel = {
        "imageSrc": assets.rel_to_book(image_path),
        "originalWidth": size[0],
        "originalHeight": size[1],
        "audioSrc": assets.rel_to_book(voice["audio"]) if voice["audio"] else "",
        # A transition eats this shot's last TRANSITION_FRAMES by overlapping
        # them with the next shot, so a shot feeding a transition must outlast
        # its narration by the overlap or the voice is cut off mid-word. A
        # hard cut eats nothing — padding there is just dead air on screen.
        "durationInSeconds": voice["duration"]
                             + (TRANSITION_SECONDS if overlaps_next else 0),
        "narrationText": shot.get("narration") or "",
        "sceneCaption": "",
        "animation": shot["animation"],
        "transitionIn": shot.get("transition_in") or "none",
        "events": _events(shot, voice["duration"]),
        "wordTimings": voice["word_timings"],
    }

    if camera:
        panel["camera"] = camera
    elif focal:
        origin = geometry.to_frame_fraction(focal, size, frame)
        panel["focalOrigin"] = list(origin)
        panel["zoomLimit"] = geometry.zoom_limit(regions, size, frame, origin)
    else:
        # Still worth a ceiling: a centred punch_in crops the edges too.
        panel["zoomLimit"] = geometry.zoom_limit(regions, size, frame, (0.5, 0.5))

    if panel.get("zoomLimit") == float("inf"):
        del panel["zoomLimit"]
    return panel


def _resolve(assets, target, shot, frame):
    """A shot's source -> (image path, regions to protect, camera, focal point).

    Regions come back as fractions of the image that was chosen, which is the
    only space the geometry works in.
    """
    source = shot["source"]
    page = assets.load_page(source["page"])
    aim = shot.get("animation_target") == "focal_point"

    if source["kind"] == "panel":
        panel = _find_panel(page, source["panel"], source["page"])
        return _panel_source(assets, target, shot, panel, frame, aim)

    if source["kind"] == "full_page":
        regions = geometry.regions_to_panel_fractions(
            _page_regions(page), [0, 0] + list(_image_size(assets.page_image(source["page"]))))
        return assets.page_image(source["page"]), regions, None, None

    if source["kind"] == "pan":
        return _pan(assets, target, shot, page, frame)

    raise ValueError(f"3.2: unknown source kind {source['kind']!r} in shot {shot['id']}")


def _panel_source(assets, target, shot, panel, frame, aim):
    """A single-panel shot -> (image, regions, camera=None, focal).

    In the portrait short a wide panel is cropped toward the frame around its
    focal point (see geometry.fill_crop), so it is not a thin strip over a
    blurred bar. Longform is left alone — see MIN_FRAME_FILL. The crop is
    measured in the panel image's own pixels, so both the text regions (page
    pixels) and the focal point (a panel fraction) are rebased onto whatever
    image we end up showing — the whole panel, or the cut of it.
    """
    image_path = _panel_image(assets, shot["source"]["page"], panel)
    size = _image_size(image_path)
    bx1, by1, _, _ = panel["bbox"]
    regions_px = [[rx1 - bx1, ry1 - by1, rx2 - bx1, ry2 - by1]
                  for rx1, ry1, rx2, ry2 in (panel.get("text_regions") or [])]
    focal = tuple(panel.get("focal_point") or (0.5, 0.5))

    portrait = frame[1] > frame[0]
    crop = geometry.fill_crop(size, frame, focal, MIN_FRAME_FILL) if portrait else None
    if crop:
        image_path = _crop_image(assets, target, shot["id"], image_path, crop)
        focal = ((focal[0] * size[0] - crop[0]) / (crop[2] - crop[0]),
                 (focal[1] * size[1] - crop[1]) / (crop[3] - crop[1]))
        regions_px = [[rx1 - crop[0], ry1 - crop[1], rx2 - crop[0], ry2 - crop[1]]
                      for rx1, ry1, rx2, ry2 in regions_px]
        size = _image_size(image_path)

    regions = _clip(geometry.regions_to_panel_fractions(
        regions_px, [0, 0, size[0], size[1]]))
    return image_path, regions, None, (focal if aim else None)


def _clip(regions):
    """Keep only the on-screen part of each region.

    After a fill crop a text region may hang off an edge, or sit outside the cut
    entirely. Zoom protection is about what is visible: a region clamped to the
    unit square is protected where it shows; one wholly outside is dropped.
    """
    clipped = []
    for x1, y1, x2, y2 in regions:
        cx1, cy1, cx2, cy2 = max(0.0, x1), max(0.0, y1), min(1.0, x2), min(1.0, y2)
        if cx1 < cx2 and cy1 < cy2:
            clipped.append((cx1, cy1, cx2, cy2))
    return clipped


def _pan(assets, target, shot, page, frame):
    """A pan is one image spanning both panels, plus a camera that travels.

    The panels are cropped out together rather than shown whole-page, so the
    gutters and neighbours the director did not ask for stay off screen.
    """
    source = shot["source"]
    first = _find_panel(page, source["from_panel"], source["page"])
    last = _find_panel(page, source["to_panel"], source["page"])

    crop = _union(first["bbox"], last["bbox"])
    image_path = _crop_image(assets, target, shot["id"], assets.page_image(source["page"]), crop)
    size = _image_size(image_path)

    to_crop = lambda bbox: geometry.regions_to_panel_fractions([bbox], crop)[0]
    zoom, pan_start, pan_end = geometry.pan_camera(
        to_crop(first["bbox"]), to_crop(last["bbox"]), size, frame)

    # No zoom ceiling here, and deliberately. `pan_camera` zooms only far
    # enough to *fit* a panel, so that panel's lettering is on screen by
    # construction. Clamping on both panels' text at once would be asking for
    # something a pan never does — hold both on screen together — and the
    # answer is always "then do not zoom", which is exactly not a pan.
    camera = {"zoom": zoom, "panStart": list(pan_start), "panEnd": list(pan_end)}
    return image_path, [], camera, None


def _events(shot, duration):
    """`at_fraction` through a shot -> a second on the clock.

    Clamped so an event at the very end still gets its full beat on screen
    rather than being cut off by the shot ending under it.
    """
    events = []
    for event in shot.get("events") or []:
        seconds = EVENT_SECONDS_BY_TYPE.get(event["type"], EVENT_SECONDS)
        start = max(0.0, min(float(event["at_fraction"]) * duration,
                             duration - seconds))
        events.append({"type": event["type"],
                       "startSeconds": round(start, 3),
                       "durationSeconds": seconds})
    return events


def _find_panel(page, panel_id, page_index):
    for panel in page.get("panels", []):
        if panel["id"] == panel_id:
            return panel
    raise ValueError(f"3.2: page {page_index} has no panel {panel_id}")


def _panel_image(assets, page_index, panel):
    return os.path.join(assets.page_dir(page_index), panel["image"])


def _page_regions(page):
    regions = []
    for panel in page.get("panels", []):
        regions += panel.get("text_regions") or []
    return regions


def _union(first, second):
    return [min(first[0], second[0]), min(first[1], second[1]),
            max(first[2], second[2]), max(first[3], second[3])]


def _crop_image(assets, target, shot_id, page_image, box):
    path = os.path.join(assets.target_dir(target), "images", f"shot_{shot_id:03d}.jpg")
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with Image.open(page_image) as image:
        image.convert("RGB").crop(tuple(box)).save(path, quality=92)
    return path


def _image_size(path):
    with Image.open(path) as image:
        return image.size
