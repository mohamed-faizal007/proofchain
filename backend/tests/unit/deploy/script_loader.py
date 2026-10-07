"""Load the repo-level demo scripts (`scripts/`) as modules for tests (P10-04).

They are plain scripts, not a package, and import each other by bare name, so `scripts/` goes on
`sys.path` for the duration of the import. The data module needs the eval extra (faker) and
`eval/` modules; callers `pytest.importorskip("faker")` first.
"""

import importlib
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "scripts"


def load_script(name: str) -> ModuleType:
    path = str(SCRIPTS)
    added = path not in sys.path
    if added:
        sys.path.insert(0, path)
    try:
        return importlib.import_module(name)
    finally:
        if added:
            sys.path.remove(path)
