"""python -m panelflow.cli <comic.cbz | comic_folder> [--only 1.3] [--model NAME]

Runs Stage 1 (assets), Stage 2 (direction), then Stage 3 (production). `--only`
picks one sub-stage from any of them: '1.3' analyses pages, '2.1' directs the
longform, '2.3' validates, '3.3' renders. `--target` limits Stage 3 to one
output.
"""
import argparse
import os
import shutil
import sys
import traceback

from custom_logger import logger_config

from .paths import Assets
from .stage1 import runner
from .stage2 import runner as stage2_runner
from .stage3 import runner as stage3_runner

# Every sub-stage that exists. argparse enforces this so a typo ("3.9") errors
# at the prompt instead of silently doing nothing — or worse, in Stage 3, where
# an unknown id falls past every early return and runs everything.
ONLY_CHOICES = ([number for number, _, _ in runner.SUB_STAGES]
                + sorted(stage2_runner.SUB_STAGES)
                + [stage2_runner.VALIDATE, stage2_runner.EXPAND]
                + sorted(stage3_runner.SUB_STAGES))


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
        prog="panelflow", description="Run the pipeline on one comic.")
    parser.add_argument("target", help="A .cbz file, or a comic folder containing <name>.cbz")
    parser.add_argument("--only", choices=ONLY_CHOICES, metavar="SUB_STAGE",
                        help=f"Run a single sub-stage: {', '.join(ONLY_CHOICES)}")
    parser.add_argument("--model", help="Override the LLM model for this run")
    parser.add_argument("--output", choices=stage3_runner.TARGETS,
                        help="Limit Stage 3 to one output (default: both)")
    args = parser.parse_args(argv)

    folder = prepare_folder(args.target)
    if Assets(folder).published():
        # The publisher wiped this folder and left the tombstone. There is no
        # cbz to read and nothing to re-make; saying so beats failing in 1.1.
        logger_config.info(f"{os.path.basename(folder)}: already published, nothing to do")
        return 0

    # No --only means every stage; --only names the stage by its first digit.
    stage1 = args.only is None or args.only.startswith("1")
    stage2 = args.only is None or args.only.startswith("2")
    stage3 = args.only is None or args.only.startswith("3")

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
        if stage3:
            assets = stage3_runner.run(folder, only=args.only, target=args.output)
            for name in ([args.output] if args.output else stage3_runner.TARGETS):
                logger_config.info(f"Stage 3 complete: {assets.video_path(name)}")
    except Exception:
        # The whole traceback: a KeyError from deep in a sub-stage as just
        # its message is one quoted word with no clue where it came from.
        logger_config.error(traceback.format_exc())
        return 1
    finally:
        # 1.3's browser rides a docker container that outlives the process if
        # nobody says goodbye. No-op when vision never ran.
        from .providers import browser_ui
        browser_ui.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
