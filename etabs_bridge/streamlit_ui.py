"""Streamlit sayfalari ile kopru arasindaki tutkal.

Sayfalarin tek ihtiyaci::

    from etabs_bridge.streamlit_ui import connect_etabs
    SapModel = connect_etabs(units=6)

``connect_etabs`` sirasiyla sunlari yapar:

1. Kullanicinin giris yapmis olmasini sart kosar.
2. Kullaniciya bagli bir ajanin canli olup olmadigini kontrol eder; yoksa
   kurulum/eslestirme panelini gosterip sayfayi durdurur.
3. COM ile ayni sekle sahip ``RemoteSapModel`` nesnesini dondurur.

Ayrica sayfanin ustune kucuk bir durum cubugu cizer: hangi model acik, veri
ne zaman okundu ve "Verileri yenile" dugmesi.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Optional

import streamlit as st

from . import settings
from .client import DEFAULT_CACHE_TTL, BridgeTransport, RemoteSapModel
from .protocol import AgentBusyError, AgentOfflineError, BridgeError

_CACHE_KEY = "_etabs_table_cache"
_CLIENT_KEY = "_etabs_client_id"

#: Ajan indirme baglantisi.
#: Varsayilan, Streamlit'in statik dosya servisidir: ``static/`` klasorune
#: konan dosyalar ``/app/static/<ad>`` altinda yayinlanir (bunun icin
#: ``.streamlit/config.toml`` icinde ``enableStaticServing = true`` olmali).
#: Buyuk dosyayi nginx ile servis etmek daha verimlidir; o durumda bu ortam
#: degiskenini kendi adresinizle ezin.
AGENT_DOWNLOAD_URL = settings.get(
    "AGENT_DOWNLOAD_URL", "app/static/StacontrolAgent.zip"
)


def _bridge_url() -> str:
    """Kopru API'sinin adresi.

    Ayni sunucuda calisirken localhost; Streamlit Community Cloud gibi tek
    surecli ortamlarda koprunun genel HTTPS adresi olmalidir (kopru orada
    barinamaz, ayri bir yerde calismalidir -- bkz. README).
    """
    return (settings.get("BRIDGE_URL") or "http://127.0.0.1:8500").rstrip("/")


def _internal_key() -> str:
    return settings.require("BRIDGE_INTERNAL_KEY", settings.SECRETS_HINT)


@st.cache_resource(show_spinner=False)
def _transport(base_url: str, key: str) -> BridgeTransport:
    """HTTP oturumu surecte tek ornek olsun (baglanti havuzu paylasilir)."""
    return BridgeTransport(base_url, key)


def get_transport() -> BridgeTransport:
    return _transport(_bridge_url(), _internal_key())


def _client_id() -> str:
    """Bu tarayici oturumuna ait sabit kimlik (ajan kiralamasi icin)."""
    if _CLIENT_KEY not in st.session_state:
        st.session_state[_CLIENT_KEY] = uuid.uuid4().hex
    return st.session_state[_CLIENT_KEY]


def current_username() -> Optional[str]:
    if not st.session_state.get("logged_in"):
        return None
    username = st.session_state.get("username")
    return username or None


# ---------------------------------------------------------------------------
# Durum sorgusu
# ---------------------------------------------------------------------------

def agent_status(username: str) -> dict:
    try:
        return get_transport().status(username)
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def pair_agent(username: str, code: str) -> dict:
    return get_transport().pair(username, code)


def disconnect_agent(username: str) -> None:
    get_transport().disconnect(username)
    st.session_state.pop(_CACHE_KEY, None)


# ---------------------------------------------------------------------------
# Arayuz parcalari
# ---------------------------------------------------------------------------

def _render_setup_panel(username: str, status: dict) -> None:
    """Ajan yokken gosterilen kurulum + eslestirme paneli."""
    st.warning("Bu sayfa ETABS modelinize baglanmayi gerektiriyor.")

    if status.get("connected") and not status.get("online"):
        st.info(
            "Ajan daha once eslestirilmis ama su an calismiyor gorunuyor. "
            "Bilgisayarinizda **BASLAT.bat** dosyasini calistirin."
        )

    col_left, col_right = st.columns([1.15, 1])

    with col_left:
        st.markdown("#### 1. Ajani indirin ve calistirin")
        st.markdown(
            f"""
- [ETABS Ajanini indirin]({AGENT_DOWNLOAD_URL}) (zip)
- Zip dosyasini bir klasore cikarin
- **BASLAT.bat** dosyasina cift tiklayin
- Acilan pencerede 6 haneli kod gorunecek

Kurulum gerekmez. Ajan bilgisayarinizda hicbir port acmaz, yalnizca
disariya baglanti kurar ve modelinizi **sadece okur**.
            """
        )

    with col_right:
        st.markdown("#### 2. Kodu buraya girin")
        with st.form("agent_pair_form", clear_on_submit=False):
            code = st.text_input(
                "Eslestirme kodu", max_chars=6, placeholder="ORN: K7M2QP"
            ).strip().upper()
            submitted = st.form_submit_button("Baglan", type="primary", use_container_width=True)
        if submitted:
            if len(code) != 6:
                st.error("Kod 6 karakter olmali.")
            else:
                try:
                    pair_agent(username, code)
                except BridgeError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Baglanti kurulamadi: {exc}")
                else:
                    st.session_state.pop(_CACHE_KEY, None)
                    st.success("Baglanti kuruldu.")
                    time.sleep(0.6)
                    st.rerun()

        if st.button("Durumu yenile", use_container_width=True):
            st.rerun()


def _render_status_bar(model: RemoteSapModel, status: dict) -> None:
    """Sayfa ustundeki ince durum cubugu."""
    model_file = status.get("model_file") or ""
    name = os.path.basename(model_file) if model_file else "model adi okunamadi"
    age = model.cache_age()

    col_a, col_b, col_c = st.columns([3, 2, 1.2])
    with col_a:
        st.caption(f"🟢 ETABS bagli — **{name}**")
    with col_b:
        if age is None:
            st.caption("Veri: bu calistirmada okunacak")
        elif age < 60:
            st.caption(f"Veri: {int(age)} sn once okundu")
        else:
            st.caption(f"Veri: {int(age // 60)} dk once okundu")
    with col_c:
        if st.button("↻ Verileri yenile", use_container_width=True,
                     help="ETABS'te analizi yeniden calistirdiysaniz buna basin"):
            model.clear_cache()
            st.rerun()


def render_sidebar_status() -> None:
    """Kenar cubugunda kisa ajan durumu (tum sayfalarda cagrilabilir)."""
    username = current_username()
    if not username:
        return
    status = agent_status(username)
    with st.sidebar:
        st.markdown("---")
        if status.get("connected") and status.get("online"):
            model_file = status.get("model_file") or ""
            st.success("ETABS ajani bagli")
            if model_file:
                st.caption(os.path.basename(model_file))
        elif status.get("connected"):
            st.warning("Ajan cevrimdisi")
        else:
            st.info("ETABS ajani bagli degil")
        st.page_link(
            "pages/0_ETABS_Baglantisi.py", label="ETABS Baglantisi", icon="🔌"
        )


# ---------------------------------------------------------------------------
# Ana giris noktasi
# ---------------------------------------------------------------------------

def connect_etabs(
    units: Optional[int] = None,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    show_status_bar: bool = True,
) -> RemoteSapModel:
    """Kullanicinin ajani uzerinden ETABS'e baglanir.

    Args:
        units: Baglanti kurulur kurulmaz uygulanacak ETABS birim kodu
            (6 = kN-m-C, 12 = ton-m-C). ``None`` ise dokunulmaz.
        cache_ttl: Okunan tablolarin onbellekte kalma suresi (saniye).
        show_status_bar: Sayfa ustune durum cubugu cizilsin mi.

    Returns:
        COM ``SapModel`` nesnesiyle ayni sekle sahip ``RemoteSapModel``.

    Not:
        Baglanti yoksa kurulum panelini cizer ve ``st.stop()`` cagirir; bu
        durumda fonksiyon **donmez**.
    """
    username = current_username()
    if not username:
        st.warning("Bu sayfayi kullanmak icin giris yapmalisiniz.")
        st.page_link("pages/uyelik_girisi.py", label="Giris Yap", icon="🔑")
        st.stop()

    status = agent_status(username)
    if not (status.get("connected") and status.get("online")):
        _render_setup_panel(username, status)
        st.stop()

    cache = st.session_state.setdefault(_CACHE_KEY, {})
    model = RemoteSapModel(
        transport=get_transport(),
        username=username,
        client_id=_client_id(),
        cache=cache,
        cache_ttl=cache_ttl,
    )

    if units is not None:
        try:
            model.SetPresentUnits(int(units))
        except AgentOfflineError:
            st.error("ETABS ajani ile baglanti koptu. Ajanin calistigini kontrol edin.")
            st.stop()
        except AgentBusyError as exc:
            st.error(str(exc))
            st.stop()
        except BridgeError as exc:
            st.error(f"ETABS birimleri ayarlanirken hata: {exc}")
            st.stop()

    if show_status_bar:
        _render_status_bar(model, status)

    return model
