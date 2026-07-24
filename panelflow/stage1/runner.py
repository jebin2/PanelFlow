"""Stage 1 runner: the six sub-stages in order, each skipped when already done."""
from custom_logger import logger_config

from ..paths import Assets
from . import analyze, extract, reconcile, split, synthesize, validate

SUB_STAGES = [
    ("1.1", "extract", extract),
    ("1.2", "split", split),
    ("1.3", "analyze", analyze),
    ("1.4", "reconcile", reconcile),
    ("1.5", "synthesize", synthesize),
    ("1.6", "validate", validate),
]


def run(comic_folder, only=None, model=None):
    """Run Stage 1. `only` limits to one sub-stage id ('1.3'). Returns Assets."""
    assets = Assets(comic_folder)
    for number, name, module in SUB_STAGES:
        if only and number != only:
            continue
        if module.is_done(assets):
            logger_config.info(f"{number} {name}: already done")
            continue

        logger_config.info(f"{number} {name}: running")
        problems = module.run(assets, model=model)
        if problems:
            raise ValueError(
                f"Stage {number} ({name}) found {len(problems)} problem(s):\n  "
                + "\n  ".join(problems)
            )
    return assets
