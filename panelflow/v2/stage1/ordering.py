"""Reading-order sort for panel bboxes. Pure function, no I/O."""

ROW_OVERLAP = 0.5


def sort_panels(bboxes, reading_direction="ltr"):
    """Sort [x1,y1,x2,y2] bboxes into reading order: rows top-down, then
    left-to-right (ltr) or right-to-left (rtl) within each row."""
    rows = _group_rows(sorted(bboxes, key=lambda b: b[1]))
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: b[0], reverse=(reading_direction == "rtl")))
    return ordered


def _group_rows(bboxes_by_top):
    rows = []
    for bbox in bboxes_by_top:
        row = next((r for r in rows if _same_row(r[0], bbox)), None)
        if row is None:
            rows.append([bbox])
        else:
            row.append(bbox)
    return rows


def _same_row(a, b):
    """True when b's vertical span overlaps a's by more than ROW_OVERLAP of the shorter one."""
    overlap = min(a[3], b[3]) - max(a[1], b[1])
    if overlap <= 0:
        return False
    shorter = min(a[3] - a[1], b[3] - b[1])
    return shorter > 0 and overlap / shorter >= ROW_OVERLAP
