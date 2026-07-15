import xml.etree.ElementTree as ET
import zipfile


def parse(cbz_path):
    """ComicInfo.xml → {title, series, characters[], reading_direction}, or None."""
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
        "title": text("Title"),
        "series": text("Series"),
        "characters": [c.strip() for c in text("Characters").split(",") if c.strip()],
        "reading_direction": "rtl" if "righttoleft" in text("Manga").lower().replace(" ", "") else "ltr",
    }
