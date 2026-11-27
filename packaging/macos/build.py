"""Produce the Apple Silicon starter disk image and its review manifest."""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import plistlib
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from ratatoss.transport import CROC_VERSION

ARCHIVE_SHA256 = "b6a6da6c6a21bd5a3723003295cf232da281d3767687f5731725c6c4360e1015"
CROC_SHA256 = "56d4c1845f2638217c6e8fe2464e3db19db518a0772b570aafbe61af0125a54b"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def copy_licenses(target):
    target.mkdir()
    shutil.copyfile(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", target / "Python-LICENSE.txt")
    versions = {}
    for line in (HERE / "requirements-build.txt").read_text().splitlines():
        name, pin = line.split("==")
        dist = importlib.metadata.distribution(name)
        if dist.version != pin:
            raise ValueError(f"Expected {name}=={pin}, found {dist.version}")
        versions[name] = pin
        notices = [p for p in dist.files if p.parts[0].endswith(".dist-info")
                   and ("licenses" in p.parts or p.name.upper().startswith(("LICENSE", "COPYING")))]
        if not notices:
            raise ValueError(f"Missing license for {name}")
        for notice in notices:
            destination = target / name / Path(*notice.parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(notice.locate(), destination)
    return versions


def add_croc(archive, contents, licenses):
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError("Croc archive SHA-256 mismatch")
    binary = contents / "MacOS" / "croc"
    with tarfile.open(archive, "r:gz") as release:
        for name in ("croc", "LICENSE", "THIRD_PARTY_NOTICES.md", "src/codephrase/wordlists/LICENSE.txt"):
            target = binary if name == "croc" else licenses / "croc" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with release.extractfile(name) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
    if digest(binary) != CROC_SHA256:
        raise ValueError("Croc executable SHA-256 mismatch")
    binary.chmod(0o755)
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    if version != f"croc version {CROC_VERSION}":
        raise ValueError(f"Unexpected Croc version {version}")


def build(archive):
    if sys.platform != "darwin" or platform.machine() != "arm64" or sys.version_info[:2] != (3, 11):
        raise ValueError("Use arm64 Python 3.11 on macOS")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    work = ROOT / "build" / "macos"
    output = ROOT / "dist" / "macos"
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as tmp:
        stage = Path(tmp)
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--windowed", "--onedir", "--noupx",
            "--target-architecture", "arm64", "--name", "Ratatoss", "--osx-bundle-identifier",
            "com.ratatoss.starter", "--paths", str(ROOT), "--specpath", str(stage),
            "--workpath", str(stage / "work"), "--distpath", str(stage / "dist"),
            "--add-data", f"{ROOT / 'ratatoss/static'}:ratatoss/static",
            "--add-data", f"{ROOT / 'spec/db/node.sql'}:ratatoss/_sql", HERE / "launcher.py",
        ], cwd=ROOT, check=True)
        image_root = stage / "image"
        image_root.mkdir()
        app = (stage / "dist/Ratatoss.app").rename(image_root / "Ratatoss.app")
        contents = app / "Contents"
        plist = contents / "Info.plist"
        info = plistlib.loads(plist.read_bytes())
        info.update(CFBundleShortVersionString=version, CFBundleVersion=version, LSUIElement=True)
        plist.write_bytes(plistlib.dumps(info))
        licenses = contents / "Resources" / "licenses"
        packages = copy_licenses(licenses)
        add_croc(archive, contents, licenses)
        subprocess.run(["codesign", "--force", "--sign", "-", app], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", app], check=True)
        image = stage / f"Ratatoss-Starter-{version}-macos-arm64.dmg"
        subprocess.run(["hdiutil", "create", "-fs", "HFS+", "-format", "UDZO", "-volname",
                        "Ratatoss Starter", "-srcfolder", image_root, image], check=True)
        manifest = {
            "application_version": version, "mode": "starter", "architecture": "arm64",
            "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "build_os": platform.mac_ver()[0], "build_os_version": platform.version(),
            "python_runtime": platform.python_version(), "python_packages": packages,
            "croc": {"version": CROC_VERSION, "archive_sha256": ARCHIVE_SHA256, "executable_sha256": CROC_SHA256},
            "disk_image": {"file": image.name, "sha256": digest(image), "signature": "unsigned"},
            "app_signature": "ad-hoc", "notarized": False,
            "licenses": sorted(p.relative_to(licenses).as_posix() for p in licenses.rglob("*") if p.is_file()),
        }
        record = image.with_suffix(".manifest.json")
        record.write_text(json.dumps(manifest, indent=2) + "\n")
        image.replace(output / image.name)
        record.replace(output / record.name)
        print(output / image.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--croc-archive", required=True, type=Path)
    build(parser.parse_args().croc_archive.resolve(strict=True))
