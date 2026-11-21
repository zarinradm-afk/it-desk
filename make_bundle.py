from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).parent
OUT = ROOT.parent / "it-desk-review.zip"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".venv", "data", "runtime-check"}
SKIP_NAMES = {"windows-ca.pem"}

files = [
    path for path in ROOT.rglob("*")
    if path.is_file()
    and not any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts)
    and path.name not in SKIP_NAMES
    and path.suffix != ".pyc"
    and path.name != OUT.name
]
with ZipFile(OUT, "w", ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(ROOT).as_posix())
print(f"Wrote {len(files)} files to {OUT}")
