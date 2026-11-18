"""Verify the original Ratatoss documents against the approved baseline."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys


MANIFEST_SHA256 = "f70c1754778268a54f2f6a481ea1aa7facb555dc6d09ad8286d9f8ba9b870d4d"
PROTECTED_DIRECTORIES = ("docs", "plan")


def raise_walk_error(error: OSError) -> None:
    raise error


def verify(root: Path, expected: dict[str, str]) -> int:
    actual = {}
    unexpected_entries = set()
    for name in PROTECTED_DIRECTORIES:
        directory = root / name
        if directory.is_symlink() or directory.exists() and not directory.is_dir():
            unexpected_entries.add(name)
            continue
        for current, directories, filenames in os.walk(directory, onerror=raise_walk_error):
            parent = Path(current)
            for dirname in directories[:]:
                path = parent / dirname
                if path.is_symlink():
                    directories.remove(dirname)
                    unexpected_entries.add(path.relative_to(root).as_posix())
            for filename in filenames:
                path = parent / filename
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or not path.is_file():
                    unexpected_entries.add(relative)
                else:
                    actual[relative] = sha256(path.read_bytes()).hexdigest()

    missing = expected.keys() - actual.keys()
    added = actual.keys() - expected.keys()
    changed = {path for path in expected.keys() & actual.keys() if actual[path] != expected[path]}
    for label, paths in (
        ("Missing", missing),
        ("Added", added),
        ("Changed", changed),
        ("Unexpected entry", unexpected_entries),
    ):
        for path in sorted(paths):
            print(f"{label}: {path}", file=sys.stderr)
    if missing or added or changed or unexpected_entries:
        return 1
    print(f"Verified {len(expected)} original files in docs/ and plan/.")
    return 0


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=script_dir.parent.parent)
    args = parser.parse_args()
    try:
        manifest = (script_dir / "originals.sha256.json").read_bytes()
        if sha256(manifest).hexdigest() != MANIFEST_SHA256:
            print("Baseline manifest digest mismatch.", file=sys.stderr)
            return 2
        return verify(args.root, json.loads(manifest))
    except OSError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
