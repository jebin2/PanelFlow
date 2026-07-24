"""Mechanical shape-fixing for director output, before validation judges it.

The director model is asked for a precise JSON shape but reliably drifts on two
points: it writes an event as a bare string ("flash") instead of the object the
renderer needs, and it leaves a `silent_seconds` value on a shot that also has
narration. Each has exactly one correct form the contract already fixes — there
is nothing to decide, so code settles it here rather than spending the model's
limited repair budget on format it cannot reliably hit.

Judgment is not touched: an invented name, an over-used camera move, a silent
shot missing its duration — those need the model, and are left for validation.
"""

# Where a coerced event fires when the model gave no fraction. Middle of the
# shot: the safe, unopinionated default for a beat of punctuation.
DEFAULT_AT_FRACTION = 0.5


def normalize_shots(shots):
    """Assign ids by position and settle the shapes the model drifts on.

    Ids are positions — a model asked to number a list drifts off by one, and
    the ids are what Stage 3 renders in order, so we count rather than ask.
    """
    for shot_id, shot in enumerate(shots, start=1):
        shot["id"] = shot_id
        shot["events"] = [_normalize_event(e) for e in (shot.get("events") or [])]
        if (shot.get("narration") or "").strip():
            # Length comes from the voice track; a silent_seconds here is a
            # contradiction the contract resolves to null.
            shot["silent_seconds"] = None
    return shots


def _normalize_event(event):
    """A bare "flash" names the type; the renderer needs the whole object."""
    if isinstance(event, str):
        return {"type": event, "at_fraction": DEFAULT_AT_FRACTION}
    return event
