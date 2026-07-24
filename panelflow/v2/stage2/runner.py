"""Stage 2 runner: direct each target, validate it, then expand the longform."""
from custom_logger import logger_config

from ..paths import Assets
from . import direct, expand, validate

# sub-stage id -> target. 2.3 validates whatever 2.1 and 2.2 produced.
SUB_STAGES = {"2.1": "longform", "2.2": "shorts"}
VALIDATE = "2.3"
# 2.4 moves the picture to follow the words 2.3 has already blessed, longform
# only — so it runs after validation, never instead of it.
EXPAND = "2.4"


def run(comic_folder, only=None, model=None):
    """Run Stage 2. `only` limits to one sub-stage id ('2.1', '2.2', '2.3')."""
    assets = Assets(comic_folder)
    if not assets.stage1_complete():
        raise ValueError(
            f"{assets.name}: Stage 1 is not complete (book.json.analysis.completed_at "
            f"is unset). The director must not read assets 1.6 has not validated."
        )

    for number, target in SUB_STAGES.items():
        if only not in (None, number):
            continue
        if direct.is_done(assets, target):
            logger_config.info(f"{number} {target}: already directed")
            continue
        direct.run(assets, target, model=model)

    if only in (None, VALIDATE):
        problems = []
        for target in SUB_STAGES.values():
            problems += validate.run(assets, target, model=model)
        if problems:
            raise ValueError(
                f"Stage 2.3 could not validate after {validate.MAX_REPAIRS} repair(s):\n  "
                + "\n  ".join(problems)
            )

    if only in (None, EXPAND):
        if expand.is_done(assets, expand.TARGET):
            logger_config.info(f"{EXPAND} {expand.TARGET}: already expanded")
        else:
            expand.run(assets, expand.TARGET, model=model)

    return assets
