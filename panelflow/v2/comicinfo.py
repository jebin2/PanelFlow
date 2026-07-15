import xml.etree.ElementTree as ET
import zipfile


def parse(cbz_path):
    """ComicInfo.xml → book metadata, or None when absent/unreadable."""
    with zipfile.ZipFile(cbz_path) as z:
        member = next((n for n in z.namelist() if n.lower().endswith("comicinfo.xml")), None)
        if not member:
            return None
        try:
            root = ET.fromstring(z.read(member))
        except ET.ParseError:
            return None

    def text(tag):
        el = root.find(tag)
        return el.text.strip() if el is not None and el.text else ""

    return {
        "title": text("Title") or _title_from_series(text("Series"), text("Number"), text("Volume")),
        "series": text("Series"),
        "summary": text("Summary"),
        "publisher": text("Publisher"),
        "characters": [c.strip() for c in text("Characters").split(",") if c.strip()],
        "reading_direction": "rtl" if "righttoleft" in text("Manga").lower().replace(" ", "") else "ltr",
    }


def _title_from_series(series, number, volume):
    """Many files carry no <Title>. Series+Number beats a scene-release filename
    like 'Strange Scales 006 (2026) (digital-mobile-Empire)'."""
    if not series:
        return ""
    title = f"{series} #{number}" if number else series
    return f"{title} ({volume})" if volume else title
