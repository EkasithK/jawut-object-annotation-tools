# PyInstaller build for the Windows desktop application.
#
# Built as onedir rather than onefile on purpose: onefile unpacks itself to a
# temporary directory on every launch, which costs 5-15 seconds of startup and
# draws noticeably more antivirus false positives. The zip a user downloads
# contains a folder; the exe inside it starts in about a second.
#
# Run from the repository root, after building the frontend:
#     npm --prefix frontend run build
#     pyinstaller packaging/jawut.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PACKAGE = ROOT / "src" / "jawut"
STATIC = PACKAGE / "static"
SCHEMA = PACKAGE / "db" / "schema.sql"

if not STATIC.is_dir():
    raise SystemExit(
        "src/jawut/static is missing — run `npm --prefix frontend run build` first"
    )
if not SCHEMA.is_file():
    raise SystemExit(f"{SCHEMA} is missing")

# Only .py files go into the archive, so every other file the application reads at
# runtime has to be listed here and resolved through jawut.resources.package_file.
datas = [
    (str(STATIC), "jawut/static"),
    (str(SCHEMA), "jawut/db"),
]

hidden = [
    # uvicorn resolves these by name at runtime, so static analysis misses them.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    *collect_submodules("jawut"),
]

analysis = Analysis(
    [str(ROOT / "src" / "jawut" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    # No ML stack is bundled: adding one would take the download from roughly
    # 100 MB to over 2 GB, which defeats the point of a double-click install.
    excludes=[
        "torch",
        "ultralytics",
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "IPython",
        "tkinter",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Jawut Object Annotation Tools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "packaging" / "icon.ico")
    if (ROOT / "packaging" / "icon.ico").is_file()
    else None,
)

COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="Jawut Object Annotation Tools",
)
