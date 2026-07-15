import os

_DIR = os.path.dirname(__file__)


def load(name):
    with open(os.path.join(_DIR, f"{name}.md"), encoding="utf-8") as f:
        return f.read()
