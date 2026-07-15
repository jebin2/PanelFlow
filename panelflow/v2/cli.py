"""python -m panelflow.v2.cli <comic.cbz | comic_folder> [--only 1.3] [--model NAME]"""
import argparse
import os
import shutil
import sys

from custom_logger import logger_config

from .stage1 import runner


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
    parser.add_argument("--only", help="Run a single sub-stage, e.g. 1.3")
    parser.add_argument("--model", help="Override the LLM model for this run")
    args = parser.parse_args(argv)

    try:
        assets = runner.run(prepare_folder(args.target), only=args.only, model=args.model)
    except Exception as e:
        logger_config.error(str(e))
        return 1

    book = assets.load_book()
    logger_config.info(
        f'Stage 1 complete: {book.get("title")} — {book.get("page_count")} pages, '
        f'{len(assets.load_characters().get("characters", []))} characters'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
