"""Kullaniciya dagitilacak ajan paketini uretir.

Neden PyInstaller degil?
------------------------
PyInstaller ile uretilen imzasiz .exe dosyalari SmartScreen'de "Bilinmeyen
yayimci" uyarisi verir ve antivirus yazilimlarinda yanlis pozitif oranlari
yuksektir. Bunun yerine python.org'un **embeddable** dagitimini kullaniyoruz:
calisan ikili dosya (``python.exe``) Python Software Foundation tarafindan
imzalidir ve baslatici duz metin bir ``.bat`` dosyasidir -- kullanici icini
acip okuyabilir. Bu, muhendislik burolarinda guven acisindan onemli bir fark.

Kullanim
--------
    python -m etabs_bridge.tools.build_agent --bridge-url https://site.com/bridge

Uretilen dosya: ``dist/StacontrolAgent-<surum>.zip``
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_SRC = ROOT / "etabs_bridge" / "agent"
PROTOCOL_SRC = ROOT / "etabs_bridge" / "protocol.py"

DEFAULT_PY_VERSION = "3.11.9"
EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def download_embeddable(version: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"python-{version}-embed-amd64.zip"
    if target.exists():
        log(f"onbellekten: {target.name}")
        return target
    url = EMBED_URL.format(v=version)
    log(f"indiriliyor: {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, target.open("wb") as fh:
        shutil.copyfileobj(resp, fh)
    return target


def fix_path_file(py_dir: Path) -> None:
    """``._pth`` dosyasini site-packages ve betik klasorunu gorecek sekilde duzenler."""
    pth_files = list(py_dir.glob("python*._pth"))
    if not pth_files:
        raise RuntimeError("Embeddable dagitimda ._pth dosyasi bulunamadi")
    pth = pth_files[0]
    zip_name = next(py_dir.glob("python*.zip")).name
    pth.write_text(
        "\n".join([zip_name, ".", "..", "Lib\\site-packages", "import site", ""]),
        encoding="utf-8",
    )
    log(f"{pth.name} guncellendi")


def install_comtypes(py_dir: Path) -> None:
    """comtypes'i gomulu dagitimin site-packages klasorune kurar."""
    target = py_dir / "Lib" / "site-packages"
    target.mkdir(parents=True, exist_ok=True)
    log("comtypes kuruluyor...")
    subprocess.run(
        [
            sys.executable, "-m", "pip", "install",
            "--target", str(target),
            "--no-compile",
            "comtypes>=1.2.0",
        ],
        check=True,
    )
    # Dagitimda gereksiz meta klasorleri temizle
    for pattern in ("*.dist-info", "*.egg-info", "__pycache__"):
        for path in target.glob(pattern):
            shutil.rmtree(path, ignore_errors=True)


def agent_version() -> str:
    """Ajan surumunu kaynaktan okur.

    Modulu ice aktarmak yerine metinden okuyoruz: ajan, dagitim duzenine gore
    ``import protocol`` yapar ve derleme ortaminda bu yol her zaman cozulmez.
    """
    text = (AGENT_SRC / "agent.py").read_text(encoding="utf-8")
    match = re.search(r'^AGENT_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("agent.py icinde AGENT_VERSION bulunamadi")
    return match.group(1)


def build(bridge_url: str, py_version: str, out_dir: Path, with_python: bool) -> Path:
    version = agent_version()
    stage = out_dir / "StacontrolAgent"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # 1) Ajan dosyalari
    for name in ("agent.py", "BASLAT.bat", "OKUBENI.txt"):
        shutil.copy2(AGENT_SRC / name, stage / name)
    shutil.copy2(PROTOCOL_SRC, stage / "protocol.py")

    # 2) Sunucu adresi
    (stage / "agent_config.json").write_text(
        json.dumps({"bridge_url": bridge_url.rstrip("/")}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log(f"sunucu adresi: {bridge_url}")

    # 3) Gomulu Python
    if with_python:
        py_dir = stage / "python"
        py_dir.mkdir()
        embed_zip = download_embeddable(py_version, out_dir / ".cache")
        with zipfile.ZipFile(embed_zip) as zf:
            zf.extractall(py_dir)
        fix_path_file(py_dir)
        install_comtypes(py_dir)
    else:
        log("gomulu Python atlandi (--no-python)")

    # 4) Zip
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "" if with_python else "-nopython"
    archive = out_dir / f"StacontrolAgent-{version}{suffix}.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                zf.write(path, Path("StacontrolAgent") / path.relative_to(stage))

    size_mb = archive.stat().st_size / (1024 * 1024)
    log(f"hazir: {archive}  ({size_mb:.1f} MB)")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Stacontrol ETABS ajan paketini uretir")
    parser.add_argument(
        "--bridge-url",
        required=True,
        help="Ajanin baglanacagi genel adres, orn. https://stacontrol.com/bridge",
    )
    parser.add_argument("--python-version", default=DEFAULT_PY_VERSION)
    parser.add_argument("--out", default=str(ROOT / "dist"))
    parser.add_argument(
        "--no-python",
        action="store_true",
        help="Gomulu Python koymadan uret (kullanicida Python varsa)",
    )
    args = parser.parse_args()

    build(
        bridge_url=args.bridge_url,
        py_version=args.python_version,
        out_dir=Path(args.out).resolve(),
        with_python=not args.no_python,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
