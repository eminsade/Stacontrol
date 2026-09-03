"""Yapilandirma degerlerinin tek okuma noktasi.

Uygulama iki farkli ortamda calisabilmeli:

* **Kendi sunucunuz (VPS)** -- degerler ortam degiskeninden gelir
  (systemd ``EnvironmentFile``).
* **Streamlit Community Cloud** -- degerler uygulama ayarlarindaki
  *Secrets* bolumunden gelir ve ``st.secrets`` ile okunur.

Bu modul ikisini de dener, boylece cagiran kodun ortami bilmesi gerekmez.
``st.secrets``, secrets tanimli degilse istisna firlatir; bu yuzden erisim
her zaman korumali yapilir.
"""

from __future__ import annotations

import os
from typing import Optional


def get(name: str, default: Optional[str] = None) -> Optional[str]:
    """Once ortam degiskenine, sonra ``st.secrets``'a bakar.

    Args:
        name: Aranan anahtar (orn. ``"BRIDGE_INTERNAL_KEY"``).
        default: Hicbir yerde bulunamazsa donecek deger.
    """
    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()

    try:
        import streamlit as st

        # st.secrets, secrets.toml yoksa istisna firlatir -- bu normaldir.
        secret = st.secrets.get(name)  # type: ignore[union-attr]
        if secret is not None and str(secret).strip():
            return str(secret).strip()
    except Exception:
        pass

    return default


def require(name: str, hint: str = "") -> str:
    """Zorunlu bir degeri okur; yoksa anlasilir bir hata ile durur.

    Streamlit icinde calisiyorsa kullaniciya ekranda mesaj gosterip sayfayi
    durdurur; disinda calisiyorsa ``RuntimeError`` firlatir.
    """
    value = get(name)
    if value:
        return value

    message = (
        f"Sunucu yapilandirmasi eksik: {name} tanimli degil. "
        + (hint or "Lutfen site yoneticisine bildirin.")
    )
    try:
        import streamlit as st

        if st.runtime.exists():
            st.error(message)
            st.stop()
    except Exception:
        pass
    raise RuntimeError(message)


#: Streamlit Community Cloud kullanicilari icin yonlendirme metni.
SECRETS_HINT = (
    "Streamlit Community Cloud kullaniyorsaniz: uygulama sayfasinda "
    "Manage app > Settings > Secrets bolumune ekleyin. Kendi sunucunuzda "
    "calisiyorsaniz ortam degiskeni olarak tanimlayin (bkz. .env.example)."
)
