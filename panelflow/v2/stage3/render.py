"""3.3 render: the manifest becomes a video.

Remotion resolves every asset through `staticFile("render_assets/...")`, which
only reaches inside its own `public/` directory. Rather than copy a book's
worth of artwork in there, `public/render_assets` is pointed at the comic
folder for the length of the render and removed afterwards — so two books can
never leave each other's assets lying around, and a crashed render does not
poison the next one.
"""
import contextlib
import os
import subprocess

from custom_logger import logger_config

from .. import jsonio

COMPOSITION = "ComicVideo"
REMOTION_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))),
    "remotion-comic")


def run(assets, target, manifest):
    """Render one target. Returns the video path."""
    from jebin_lib import normalize_loudness  # not importable in the test env

    manifest_path = assets.manifest_path(target)
    # Root.tsx takes the manifest as a *prop*, not as the whole props object.
    jsonio.write(manifest_path, {"manifest": manifest})

    output = assets.video_path(target)
    _ensure_installed()
    with _render_assets(assets):
        _render(manifest_path, output)

    normalize_loudness(output)
    logger_config.info(f"3.3 {target}: rendered {output}")
    return output


def _render(manifest_path, output):
    command = [
        "npx", "remotion", "render", COMPOSITION,
        "--props", os.path.abspath(manifest_path),
        "--output", os.path.abspath(output),
        "--codec", "h264",
    ]
    logger_config.info(f"3.3: {' '.join(command)}")
    result = subprocess.run(command, cwd=REMOTION_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"3.3: remotion render failed ({result.returncode})")


def _ensure_installed():
    if os.path.isdir(os.path.join(REMOTION_DIR, "node_modules")):
        return
    logger_config.info("3.3: installing remotion-comic dependencies")
    if subprocess.run(["npm", "install"], cwd=REMOTION_DIR).returncode != 0:
        raise RuntimeError("3.3: npm install failed for remotion-comic")


@contextlib.contextmanager
def _render_assets(assets):
    """Point remotion-comic/public/render_assets at this book, then let go."""
    public = os.path.join(REMOTION_DIR, "public")
    os.makedirs(public, exist_ok=True)
    link = os.path.join(public, "render_assets")

    if os.path.islink(link):
        os.unlink(link)
    elif os.path.exists(link):
        raise RuntimeError(
            f"3.3: {link} exists and is not a symlink. Stage 3 replaces it every "
            f"render and will not delete something it did not create.")

    os.symlink(assets.folder, link)
    try:
        yield
    finally:
        if os.path.islink(link):
            os.unlink(link)
