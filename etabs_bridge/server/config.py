"""Kopru sunucusunun yapilandirmasi. Tum degerler ortam degiskeninden gelir."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "evet"}


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


#: Streamlit arka ucunun kopru API'sine erisirken kullandigi paylasilan sir.
#: Bu anahtar ASLA tarayiciya gonderilmez; sunucudan sunucuya kullanilir.
INTERNAL_API_KEY = os.environ.get("BRIDGE_INTERNAL_KEY", "").strip()

#: Kopru API'sinin Streamlit tarafindan gorulen adresi.
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8500").rstrip("/")

#: Ajanin baglanacagi genel adres (indirme paketine gomulur).
PUBLIC_BRIDGE_URL = os.environ.get("PUBLIC_BRIDGE_URL", BRIDGE_URL).rstrip("/")

#: Durum veritabani. Kalici bir dizinde olmali (systemd StateDirectory gibi).
DB_PATH = Path(os.environ.get("BRIDGE_DB", "bridge_state.db")).resolve()

#: Eslestirme kodunun gecerlilik suresi (saniye).
PAIRING_TTL = _int("BRIDGE_PAIRING_TTL", 600)

#: Ajandan bu sure boyunca haber alinmazsa cevrimdisi sayilir.
AGENT_IDLE_TIMEOUT = _int("BRIDGE_AGENT_IDLE_TIMEOUT", 90)

#: Bir tarayici oturumunun ajan uzerindeki ozel kullanim kirasi (saniye).
LEASE_TTL = _int("BRIDGE_LEASE_TTL", 120)

#: Alinmamis sonuclarin saklanma suresi.
RESULT_TTL = _int("BRIDGE_RESULT_TTL", 300)

#: Ajan surumu; istemci bundan eskiyse kullaniciya guncelleme uyarisi cikar.
MIN_AGENT_VERSION = os.environ.get("BRIDGE_MIN_AGENT_VERSION", "1.0.0")

#: Gelistirme kolayligi: anahtar verilmemisse gecici bir tane uret.
DEV_MODE = _bool("BRIDGE_DEV_MODE", False)

if not INTERNAL_API_KEY:
    if DEV_MODE:
        INTERNAL_API_KEY = secrets.token_urlsafe(32)
        print(
            "[bridge] UYARI: BRIDGE_INTERNAL_KEY tanimli degil, gelistirme icin "
            f"gecici anahtar uretildi: {INTERNAL_API_KEY}",
            file=sys.stderr,
        )
    else:
        raise RuntimeError(
            "BRIDGE_INTERNAL_KEY ortam degiskeni zorunludur. "
            "Uretmek icin: python -c \"import secrets;print(secrets.token_urlsafe(32))\""
        )
