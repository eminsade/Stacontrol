"""Ortak arayuz yardimcilari ve oturum cerezleri.

Guvenlik notu
-------------
``COOKIES_PASSWORD`` cerezleri sifrelemek icin kullanilir. Sabit/varsayilan bir
deger kullanilirsa herkesin cerezi ayni anahtarla sifrelenir ve oturum
sahtekarligi mumkun hale gelir. Bu yuzden uretimde ortam degiskeni **zorunlu**
tutulur; yalnizca ``STACONTROL_DEV=1`` iken gecici bir anahtar uretilir.
"""

import secrets
import sys

import streamlit as st

# --- streamlit-cookies-manager uyumluluk kalkani -----------------------------
# streamlit_cookies_manager 0.2.0 (son surum, 2022'den beri guncellenmiyor)
# ``@st.cache`` dekoratorunu kullanir. Streamlit bu API'yi kaldirdigi icin
# paketin ICE AKTARILMASI bile AttributeError ile cokuyor ve tum sayfalar
# birden dusuyor.
#
# Kalkan, ice aktarmadan ONCE tanimlanmali. Paketin tek kullanimi
# ``key_from_parameters(salt, iterations, password)`` -- deterministik ve
# hashable argumanlar alip bytes donduren saf bir fonksiyon; ``st.cache_data``
# ile davranissal olarak esdegerdir.
if not hasattr(st, "cache"):  # pragma: no cover - surume bagli
    st.cache = st.cache_data

from streamlit_cookies_manager import EncryptedCookieManager  # noqa: E402

from etabs_bridge import settings  # noqa: E402
from session_config import init_session_state  # noqa: E402

_DEV = (settings.get("STACONTROL_DEV") or "").lower() in {"1", "true", "yes"}
_COOKIES_PASSWORD = settings.get("COOKIES_PASSWORD")

if not _COOKIES_PASSWORD:
    if _DEV:
        # Gelistirmede her yeniden baslatmada oturumlar dusor; kabul edilebilir.
        _COOKIES_PASSWORD = secrets.token_urlsafe(32)
        print(
            "[stacontrol] UYARI: COOKIES_PASSWORD yok, gelistirme icin gecici "
            "anahtar uretildi.",
            file=sys.stderr,
        )
    else:
        _COOKIES_PASSWORD = settings.require("COOKIES_PASSWORD", settings.SECRETS_HINT)

# 1. Çerez Yöneticisini Başlatma
cookies = EncryptedCookieManager(prefix="stacontrol/", password=_COOKIES_PASSWORD)

# 2. Çerez Hazır mı Kontrolü (bileşen tarayıcıdan yanıt dönene kadar bekler)
if not cookies.ready():
    st.stop()

# 3. Session State Başlatma
init_session_state()


def top_right_login():
    """
    Sayfanın sağ üst köşesinde Giriş Yap / Kayıt Ol butonlarını
    veya giriş yapıldıysa 'Hoşgeldiniz' butonu ve 'Çıkış Yap' butonunu yan yana gösterir.
    """
    col1, col2 = st.columns([8, 2])

    with col2:
        # Çerezlerde giriş bilgisi varsa session'a aktar
        if cookies.get("logged_in") == "True":
            st.session_state["logged_in"] = True
            st.session_state["username"] = cookies.get("username", "")

        if st.session_state.get("logged_in", False):
            welcome_col, logout_col = st.columns([1.5, 1])

            with welcome_col:
                st.markdown(
                    f'<div style="background-color:#4CAF50; color:white; padding:8px 16px; '
                    f'border-radius:5px; text-align:center; font-size:14px; margin:2px 0;">'
                    f'Hoşgeldiniz, {st.session_state["username"]}</div>',
                    unsafe_allow_html=True
                )

            with logout_col:
                if st.button("Çıkış Yap", type="primary", use_container_width=True):
                    st.session_state.clear()
                    cookies["logged_in"] = "False"
                    cookies["username"] = ""
                    cookies.save()
                    st.rerun()

        else:
            login_col, register_col = st.columns([1, 1])

            with login_col:
                st.markdown(
                    '<a href="/uyelik_girisi" target="_self" style="text-decoration:none; display:block;">'
                    '<button style="background-color:#4CAF50; color:white; border:none; padding:8px 16px; '
                    'width:100%; border-radius:5px; cursor:pointer; font-size:14px;">'
                    'Giriş Yap</button></a>',
                    unsafe_allow_html=True
                )

            with register_col:
                st.markdown(
                    '<a href="/kayit_ol" target="_self" style="text-decoration:none; display:block;">'
                    '<button style="background-color:#008CBA; color:white; border:none; padding:8px 16px; '
                    'width:100%; border-radius:5px; cursor:pointer; font-size:14px;">'
                    'Kayıt Ol</button></a>',
                    unsafe_allow_html=True
                )
