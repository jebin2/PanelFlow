"""python -m panelflow.v2.cli <comic.cbz | comic_folder> [--only 1.3] [--model NAME]

Runs Stage 1 (assets) then Stage 2 (direction). `--only` picks one sub-stage
from either: '1.3' analyses pages, '2.1' directs the longform, '2.3' validates.
"""
import argparse
import os
import shutil
import sys

from custom_logger import logger_config

from .stage1 import runner
from .stage2 import runner as stage2_runner


def prepare_folder(target):
    """Accept either a prepared comic folder or a bare .cbz, which is copied
    into a folder named after it (the layout Assets expects)."""
    target = os.path.abspath(target)
    if os.path.isdir(target):
        return target
    if not target.lower().endswith(".cbz"):
        raise ValueError(f"Expected a .cbz file or a comic folder: {target}")
    if not os.path.exists(target):
        raise FileNotFoundError(target)

    name = os.path.splitext(os.path.basename(target))[0]
    folder = os.path.join(os.path.dirname(target), name)
    os.makedirs(folder, exist_ok=True)
    destination = os.path.join(folder, f"{name}.cbz")
    if not os.path.exists(destination):
        shutil.copy2(target, destination)
        logger_config.info(f"Prepared {folder}")
    return folder


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="panelflow-v2", description="Run the v2 pipeline on one comic.")
    parser.add_argument("target", help="A .cbz file, or a comic folder containing <name>.cbz")
    parser.add_argument("--only", help="Run a single sub-stage, e.g. 1.3 or 2.1")
    parser.add_argument("--model", help="Override the LLM model for this run")
    args = parser.parse_args(argv)

    folder = prepare_folder(args.target)
    # No --only means both stages; --only names the stage by its first digit.
    stage1 = args.only is None or args.only.startswith("1")
    stage2 = args.only is None or args.only.startswith("2")

    try:
        if stage1:
            assets = runner.run(folder, only=args.only, model=args.model)
            book = assets.load_book()
            logger_config.info(
                f'Stage 1 complete: {book.get("title")} — {book.get("page_count")} pages, '
                f'{len(assets.load_characters().get("characters", []))} characters'
            )
        if stage2:
            assets = stage2_runner.run(folder, only=args.only, model=args.model)
            direction = assets.load_direction("longform")
            logger_config.info(
                f'Stage 2 complete: {len(direction.get("shots", []))} shots, '
                f'validated={direction.get("validated")}'
            )
    except Exception as e:
        logger_config.error(str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
