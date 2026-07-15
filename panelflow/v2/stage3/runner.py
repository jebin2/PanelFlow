"""Stage 3 runner: voice each shot, compile a manifest, render it.

Mechanical throughout. Every judgement was made upstream — if something here
needs a decision, it belongs in Stage 2, not in this file.

The sub-stages are ordered because each needs the one before: the manifest
cannot place an event until the voice has decided how long the shot runs, and
the renderer cannot start until the manifest exists.
"""
import os

from custom_logger import logger_config

from .. import jsonio
from ..paths import Assets
from . import compile as compiler
from . import render, voice

TARGETS = ("longform", "shorts")
SUB_STAGES = {"3.1": "voice", "3.2": "compile", "3.3": "render"}


def run(comic_folder, only=None, target=None):
    """Run Stage 3. `only` limits to one sub-stage id, `target` to one output."""
    assets = Assets(comic_folder)
    targets = [target] if target else list(TARGETS)

    for name in targets:
        if name not in TARGETS:
            raise ValueError(f"unknown target {name!r} — expected one of {TARGETS}")
        if not assets.stage2_complete(name):
            raise ValueError(
                f"{assets.name}: {name} direction is not validated "
                f"(direction/{name}.json has no validated: true). Stage 3 must not "
                f"render a direction 2.3 has not passed.")
        _run_target(assets, name, only)
    return assets


def _run_target(assets, target, only):
    if _done(assets, target) and only is None:
        logger_config.info(f"3: {target} already rendered")
        return

    direction = assets.load_direction(target)
    shots = direction["shots"]

    voiced = voice.run(assets, target, shots)
    if only == "3.1":
        return

    manifest = compiler.run(assets, target, direction, voiced)
    if only == "3.2":
        # 3.3 writes the manifest as part of rendering; on its own, 3.2 still
        # owes the caller the file it just built.
        jsonio.write(assets.manifest_path(target), {"manifest": manifest})
        return

    render.run(assets, target, manifest)


def _done(assets, target):
    """The video exists. Nothing cheaper is a reliable marker: the manifest is
    rewritten every render, and the audio is cached per shot regardless."""
    return os.path.exists(assets.video_path(target))
