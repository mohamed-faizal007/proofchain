"""Build-time: install the pinned spaCy model wheel and fetch the pinned embedding model."""

import hashlib
import os
import pathlib
import subprocess
import sys
import urllib.request

url = os.environ["SPACY_MODEL_URL"]
wheel = pathlib.Path("/tmp") / url.rsplit("/", 1)[1]  # pip needs the real wheel filename
urllib.request.urlretrieve(url, wheel)
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
assert digest == os.environ["SPACY_MODEL_SHA256"], f"spaCy model sha256 mismatch: {digest}"
subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-deps", str(wheel)])
wheel.unlink()

from huggingface_hub import snapshot_download  # noqa: E402

rev = os.environ["HF_MODEL_REVISION"]
path = pathlib.Path(snapshot_download("sentence-transformers/all-MiniLM-L6-v2", revision=rev))
assert path.name == rev, path
(path.parents[1] / "refs").mkdir(exist_ok=True)
(path.parents[1] / "refs" / "main").write_text(rev)  # `main` -> the pinned commit
