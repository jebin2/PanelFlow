"""python -m panelflow.batch [--once] [--model NAME]

The inbox loop: run the pipeline over every comic waiting in
content_to_be_processed, then look again in a minute.

Division of labour — this module decides *which* books and *when*; cli.main
does one book start to finish and never comes back for a second. So nothing
here knows what a stage is, and one book's failure costs only that book.
"""
import argparse
import os
import sys
import time
import traceback

from custom_logger import logger_config

from . import cli

# Books sit directly in the inbox: either a prepared folder or a bare .cbz the
# CLI will prepare. Overridable so a test or a second queue can point elsewhere.
INBOX = os.environ.get("PANELFLOW_INBOX") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "content_to_be_processed")
# A .cbz still being copied in is not a book yet — see _settled.
COPY_SETTLE_SECONDS = 5
IDLE_SECONDS = 60


def is_book(path):
    """A comic folder holds the .cbz it was made from, named after itself.

    That is what tells a book apart from a folder full of books: name the
    inbox and you mean "scan this", name a comic and you mean "run this".
    """
    return os.path.isfile(os.path.join(path, f"{os.path.basename(path)}.cbz"))


def expand(target):
    """One named target as the books it stands for.

    A .cbz or a prepared comic folder is itself; any other folder is an inbox
    to scan, so `run_app.sh content_to_be_processed` does the obvious thing
    instead of hunting for content_to_be_processed.cbz inside itself.
    """
    if os.path.isdir(target) and not is_book(target):
        found = books(target)
        if found:
            logger_config.info(f"{os.path.basename(target)}: scanning as an inbox")
            return found
    return [target]


def books(inbox):
    """Every comic waiting in the inbox, in name order.

    A folder holding its own .cbz is a comic someone already prepared (or one we
    half-finished on an earlier pass); a loose .cbz is one that just landed.
    Anything else — a stray folder, a published book's leftovers — is not ours.
    """
    if not os.path.isdir(inbox):
        logger_config.warning(f"inbox not found: {inbox}")
        return []

    entries = sorted(os.scandir(inbox), key=lambda e: e.name)
    prepared = {e.name for e in entries if e.is_dir()}

    found = []
    for entry in entries:
        if entry.is_dir():
            if is_book(entry.path):
                found.append(entry.path)
        elif entry.name.lower().endswith(".cbz"):
            # The CLI copies a .cbz into its folder rather than moving it, so
            # the original sits in the inbox for good. Once the folder exists
            # it is the book; queueing the .cbz too just re-runs it as a no-op.
            if os.path.splitext(entry.name)[0] in prepared:
                continue
            if _settled(entry.path):
                found.append(entry.path)
    return found


def _settled(path):
    """True once the file has stopped growing.

    A .cbz dropped in over the network arrives in pieces, and unpacking half of
    one fails in 1.1 for a reason that has nothing to do with the book. Waiting
    a beat and re-measuring costs five seconds and answers it exactly.
    """
    size = os.path.getsize(path)
    time.sleep(COPY_SETTLE_SECONDS)
    if os.path.getsize(path) == size:
        return True
    logger_config.info(f"still being copied, leaving for the next pass: {os.path.basename(path)}")
    return False


def run_once(inbox=INBOX, model=None):
    """One pass over the inbox. Returns the number of books that failed."""
    queue = books(inbox)
    if not queue:
        logger_config.info("nothing to process")
        return 0
    return process(queue, model=model)


def process(queue, model=None):
    """Run the pipeline over these books, in order. Returns how many failed."""
    failed = 0
    for index, target in enumerate(queue, start=1):
        name = os.path.basename(target)
        logger_config.info(f"batch {index}/{len(queue)}: {name}")
        try:
            # cli.main swallows its own stage failures and reports them as a
            # status; only a malformed target escapes it.
            failed += bool(cli.main([target] + (["--model", model] if model else [])))
        except Exception:
            logger_config.error(f"batch: {name} could not be started\n{traceback.format_exc()}")
            failed += 1
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="panelflow-batch",
        description="Run the pipeline over every comic in the inbox.")
    parser.add_argument("targets", nargs="*",
                        help="Specific .cbz files or comic folders to run "
                             "(default: everything in the inbox)")
    parser.add_argument("--once", "--onepass", action="store_true", dest="once",
                        help="One pass over the inbox, then exit (default: keep watching)")
    parser.add_argument("--model", help="Override the LLM model for every run")
    parser.add_argument("--inbox", default=INBOX, help=f"Folder to watch (default: {INBOX})")
    args = parser.parse_args(argv)

    # Named books are a request, not a queue: run exactly those, once, and let
    # the exit code say whether they made it. Watching is for the inbox.
    if args.targets:
        queue = [book for t in args.targets for book in expand(os.path.abspath(t))]
        failed = process(queue, model=args.model)
        return 1 if failed else 0

    while True:
        try:
            run_once(args.inbox, model=args.model)
        except KeyboardInterrupt:
            raise
        except Exception:
            # The pass itself broke, not a book. Log it and try again later —
            # a watcher that exits on a bad pass stops watching.
            logger_config.error(f"batch pass failed\n{traceback.format_exc()}")

        if args.once:
            return 0
        logger_config.info(f"Sleeping for {IDLE_SECONDS} seconds", seconds=IDLE_SECONDS)


if __name__ == "__main__":
    sys.exit(main())
