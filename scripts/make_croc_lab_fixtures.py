"""Write synthetic Croc lab fixtures to a new directory."""

import argparse
import hashlib
import shutil
from pathlib import Path


FIXTURES = (
    ("a-32mib.bin", 32),
    ("a-64mib.bin", 64),
    ("a-128mib.bin", 128),
    ("b-to-c-32mib.bin", 32),
    ("b-to-c-64mib.bin", 64),
    ("b-to-c-128mib.bin", 128),
)
MIB = 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="new fixture directory")
    output_dir = parser.parse_args().output_dir
    total_bytes = sum(size_mib for _, size_mib in FIXTURES) * MIB
    if shutil.disk_usage(output_dir.parent).free < total_bytes:
        parser.error(f"At least {total_bytes // MIB} MiB of free space is required")
    output_dir.mkdir()

    print("file,bytes,sha256")
    for name, size_mib in FIXTURES:
        digest = hashlib.sha256()
        with (output_dir / name).open("xb") as output:
            for index in range(size_mib):
                seed = f"ratatoss-croc-lab-v1:{name}:{index}".encode("ascii")
                block = hashlib.shake_256(seed).digest(MIB)
                output.write(block)
                digest.update(block)
        print(f"{name},{size_mib * MIB},{digest.hexdigest()}")


if __name__ == "__main__":
    main()
