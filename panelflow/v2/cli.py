"""python -m panelflow.v2.cli <comic_folder> [--only 1.3] [--model NAME]"""
import argparse
import sys

from custom_logger import logger_config

from .stage1 import runner


def main(argv=None):
    parser = argparse.ArgumentParser(prog="panelflow-v2", description="Run the v2 pipeline on one comic folder.")
    parser.add_argument("folder", help="Comic folder containing <name>.cbz")
    parser.add_argument("--only", help="Run a single sub-stage, e.g. 1.3")
    parser.add_argument("--model", help="Override the LLM model for this run")
    args = parser.parse_args(argv)

    try:
        assets = runner.run(args.folder, only=args.only, model=args.model)
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
