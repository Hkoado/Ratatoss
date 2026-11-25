"""Build and record the Windows x64 starter installer from pinned inputs."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

WINDOWS = Path(__file__).resolve().parent
ROOT = WINDOWS.parent.parent
sys.path.insert(0, str(ROOT))

from ratatoss.transport import CROC_VERSION, WINDOWS_X64_SHA256

PYTHON_VERSION = "3.14.2"
INNO_VERSION = "6.7.4"
CROC_ARCHIVE_SHA256 = "ae5b9d249099ff159f6a4b91824a2bf7d2b32f0dd77342aef51b34154aa4fffb"
CROC_NOTICES = ("LICENSE", "THIRD_PARTY_NOTICES.md", "src/codephrase/wordlists/LICENSE.txt")
BUILD_ONLY = {
    "altgraph", "pefile", "pyinstaller-hooks-contrib", "pywin32-ctypes",
}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def powershell(path, expression):
    return subprocess.check_output(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", expression],
        env={**os.environ, "RATATOSS_BUILD_INSPECT_FILE": str(path)}, text=True,
    ).strip()


def check_tools():
    if sys.platform != "win32" or platform.machine() != "AMD64" or struct.calcsize("P") != 8:
        raise ValueError("Build requires x64 Windows and x64 Python.")
    if platform.python_version() != PYTHON_VERSION:
        raise ValueError(f"Use Python {PYTHON_VERSION}.")
    versions = {}
    for line in (WINDOWS / "requirements-build.txt").read_text(encoding="utf-8").splitlines():
        name, expected = line.split("==")
        actual = importlib.metadata.version(name)
        if actual != expected:
            raise ValueError(f"Use {name} {expected}, got {actual}.")
        versions[name] = actual
    return versions


def copy_python_notices(licenses, versions, iscc):
    for name in versions.keys() - BUILD_ONLY:
        distribution = importlib.metadata.distribution(name)
        notices = [path for path in distribution.files if (
            any(part.endswith(".dist-info") for part in path.parts)
            and ("licenses" in path.parts or path.name.upper().startswith(("LICENSE", "COPYING")))
        )]
        if not notices:
            raise ValueError(f"No wheel license found for {name}.")
        for notice in notices:
            target = licenses / name / Path(*notice.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(notice.locate(), target)

    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    shutil.copyfile(iscc.with_name("LICENSE.TXT"), licenses / "Inno-Setup-LICENSE.txt")


def bundle_croc(archive, distribution, licenses):
    if sha256(archive) != CROC_ARCHIVE_SHA256:
        raise ValueError("Croc archive SHA-256 differs from the pinned upstream digest.")
    executable = distribution / "croc.exe"
    with zipfile.ZipFile(archive) as release:
        with release.open("croc.exe") as source, executable.open("wb") as target:
            shutil.copyfileobj(source, target)
        for notice in CROC_NOTICES:
            target = licenses / "croc" / notice
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(release.read(notice))
    digest = sha256(executable)
    if digest != WINDOWS_X64_SHA256:
        raise ValueError("Croc executable SHA-256 differs from the adapter's pin.")
    observed = subprocess.check_output([executable, "--version"], cwd=distribution, text=True, timeout=10).strip()
    if observed != f"croc version {CROC_VERSION}":
        raise ValueError("Croc executable reported an unexpected version.")
    return {"version": CROC_VERSION, "version_output": observed, "archive_sha256": CROC_ARCHIVE_SHA256,
            "executable_sha256": digest, "executable": executable.name}


def build(iscc, croc_archive):
    versions = check_tools()
    if sha256(croc_archive) != CROC_ARCHIVE_SHA256:
        raise ValueError("Croc archive SHA-256 differs from the pinned upstream digest.")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    work = ROOT / "build" / "windows"
    output = ROOT / "dist" / "windows"

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--distpath", output,
         "--workpath", work, WINDOWS / "Ratatoss.spec"], cwd=ROOT, check=True,
    )
    distribution = output / "Ratatoss"
    licenses = distribution / "licenses"
    licenses.mkdir()
    copy_python_notices(licenses, versions, iscc)
    croc = bundle_croc(croc_archive, distribution, licenses)

    with tempfile.TemporaryDirectory(dir=work) as stage:
        subprocess.run(
            [iscc, f"/DReleaseVersion={version}", f"/DDistributionPath={distribution}",
             f"/DOutputPath={stage}", WINDOWS / "Ratatoss.iss"], cwd=ROOT, check=True,
        )
        installer = Path(stage) / f"Ratatoss-Setup-{version}-win-x64.exe"
        manifest = {
            "application_version": version,
            "protocol_major": 1,
            "architecture": "x64",
            "mode": "starter",
            "build_os": platform.platform(),
            "python_runtime": platform.python_version(),
            "inno_setup": INNO_VERSION,
            "python_packages": versions,
            "croc": croc,
            "installer": {
                "file": installer.name,
                "sha256": sha256(installer),
                "authenticode": powershell(
                    installer, "(Get-AuthenticodeSignature -LiteralPath $env:RATATOSS_BUILD_INSPECT_FILE).Status.ToString()"
                ),
            },
            "licenses": sorted(path.relative_to(distribution).as_posix()
                               for path in licenses.rglob("*") if path.is_file()),
        }
        manifest_path = installer.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        installer.replace(output / installer.name)
        manifest_path.replace(output / manifest_path.name)
    print(f"Built {installer.name} and {manifest_path.name}.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iscc", type=Path, required=True, help="Path to the pinned Inno Setup compiler")
    parser.add_argument("--croc-archive", type=Path, required=True, help="Pinned upstream Windows x64 Croc zip")
    args = parser.parse_args()
    build(args.iscc.resolve(strict=True), args.croc_archive.resolve(strict=True))


if __name__ == "__main__":
    main()
