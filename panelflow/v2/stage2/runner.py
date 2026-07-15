"""Stage 2 runner: direct each target, then validate what was directed."""
from custom_logger import logger_config

from ..paths import Assets
from . import longform, validate

# (id, module) — 2.2 shorts joins here.
DIRECTORS = [("2.1", longform)]
VALIDATE = "2.3"


def run(comic_folder, only=None, model=None):
    """Run Stage 2. `only` limits to one sub-stage id ('2.1', '2.3')."""
    assets = Assets(comic_folder)
    if not assets.stage1_complete():
        raise ValueError(
            f"{assets.name}: Stage 1 is not complete (book.json.analysis.completed_at "
            f"is unset). The director must not read assets 1.6 has not validated."
        )

    for number, module in DIRECTORS:
        if only not in (None, number):
            continue
        if module.is_done(assets):
            logger_config.info(f"{number} {module.TARGET}: already directed")
            continue
        module.run(assets, model=model)

    if only not in (None, VALIDATE):
        return assets

    problems = []
    for _, module in DIRECTORS:
        problems += validate.run(assets, module.TARGET, model=model)
    if problems:
        raise ValueError(
            f"Stage 2.3 could not validate after {validate.MAX_REPAIRS} repair(s):\n  "
            + "\n  ".join(problems)
        )
    return assets
