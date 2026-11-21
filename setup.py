"""Copy the canonical DDL into built packages."""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
SCHEMAS = ("node.sql", "controller.sql")


class BuildWithSchemas(build_py):
    def run(self):
        super().run()
        destination = Path(self.build_lib) / "ratatoss" / "_sql"
        destination.mkdir(parents=True, exist_ok=True)
        for schema in SCHEMAS:
            self.copy_file(str(ROOT / "spec" / "db" / schema), str(destination / schema))


setup(cmdclass={"build_py": BuildWithSchemas})
