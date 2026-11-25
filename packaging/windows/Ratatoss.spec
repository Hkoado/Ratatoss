# PyInstaller shares one onedir runtime between the windowed and console entry points.
from pathlib import Path

windows = Path(SPECPATH)
root = windows.parent.parent
analysis = Analysis(
    [str(windows / "launcher.py")],
    pathex=[str(root)],
    datas=[
        (str(root / "ratatoss" / "static"), "ratatoss/static"),
        (str(root / "spec" / "db" / "node.sql"), "ratatoss/_sql"),
    ],
)
archive = PYZ(analysis.pure)
web = EXE(archive, analysis.scripts, exclude_binaries=True, name="Ratatoss",
          console=False, upx=False)
terminal = EXE(archive, analysis.scripts, exclude_binaries=True, name="Ratatoss-Terminal",
               console=True, upx=False)
distribution = COLLECT(web, terminal, analysis.binaries, analysis.datas, name="Ratatoss", upx=False)
