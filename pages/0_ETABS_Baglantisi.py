"""ETABS ajan baglantisi: indirme, eslestirme ve durum sayfasi."""

import os

import streamlit as st

st.set_page_config(
    page_title="ETABS Baglantisi",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from sidebar import setup_sidebar
from utils import top_right_login
from session_config import init_session_state
from etabs_bridge.streamlit_ui import (
    AGENT_DOWNLOAD_URL,
    agent_status,
    current_username,
    disconnect_agent,
    pair_agent,
)
from etabs_bridge.protocol import BridgeError

init_session_state()
setup_sidebar()
top_right_login()

st.title("ETABS Baglantisi")

username = current_username()
if not username:
    st.warning("Baglanti kurmak icin once giris yapin.")
    st.page_link("pages/uyelik_girisi.py", label="Giris Yap", icon="🔑")
    st.stop()

status = agent_status(username)
connected = bool(status.get("connected"))
online = bool(status.get("online"))

# ---------------------------------------------------------------------------
# Durum karti
# ---------------------------------------------------------------------------
if connected and online:
    model_file = status.get("model_file") or ""
    st.success("ETABS ajani bagli ve calisiyor.")
    info_cols = st.columns(3)
    info_cols[0].metric("Bilgisayar", status.get("hostname") or "-")
    info_cols[1].metric(
        "Acik model", os.path.basename(model_file) if model_file else "model acik degil"
    )
    info_cols[2].metric("Ajan surumu", status.get("agent_version") or "-")

    st.markdown("Artik hesap sayfalarini kullanabilirsiniz.")
    link_cols = st.columns(4)
    with link_cols[0]:
        st.page_link("pages/1_goreli_kat_otelemesi.py", label="Goreli Kat Otelemesi", icon="📏")
    with link_cols[1]:
        st.page_link("pages/2_kolon_kapasite.py", label="Kolon Kapasite", icon="🏢")
    with link_cols[2]:
        st.page_link("pages/5_perde_kesme.py", label="Perde Kesme", icon="✂️")
    with link_cols[3]:
        st.page_link("pages/metraj_hesaplama.py", label="Metraj", icon="📐")

    st.markdown("---")
    col_a, col_b = st.columns([1, 4])
    with col_a:
        if st.button("Baglantiyi kes", type="secondary"):
            disconnect_agent(username)
            st.rerun()
    with col_b:
        st.caption(
            "Baglantiyi kesmek ajan oturumunu sunucudan siler. Yeniden baglanmak "
            "icin ajani kapatip tekrar baslatmaniz ve yeni kodu girmeniz gerekir."
        )
    st.stop()

if connected and not online:
    st.warning(
        "Ajan daha once eslestirilmis ama su anda calismiyor. Bilgisayarinizda "
        "**BASLAT.bat** dosyasini calistirin, birkac saniye icinde burasi yesile doner."
    )
    if st.button("Durumu yenile"):
        st.rerun()
    st.markdown("---")

# ---------------------------------------------------------------------------
# Kurulum + eslestirme
# ---------------------------------------------------------------------------
st.markdown(
    "Stacontrol hesaplarini yapabilmek icin bilgisayarinizda acik olan ETABS "
    "modelinden tablo okumasi gerekir. Tarayicilar guvenlik nedeniyle bir web "
    "sitesinin bilgisayarinizdaki programlara erismesine izin vermez; bu koprüyu "
    "kucuk bir yardimci program kurar."
)

step_left, step_right = st.columns([1.2, 1])

with step_left:
    st.markdown("### 1. Ajani indirin")
    st.link_button("ETABS Ajanini Indir (.zip)", AGENT_DOWNLOAD_URL, type="primary")
    st.markdown(
        """
1. Zip dosyasini bir klasore cikarin (Masaustu olabilir).
2. ETABS'i acin, modelinizi yukleyin ve **analizi calistirin**.
3. Klasordeki **BASLAT.bat** dosyasina cift tiklayin.
4. Acilan siyah pencerede 6 haneli bir kod belirecek.
5. Islemleriniz bitene kadar bu pencereyi **kapatmayin**.
        """
    )
    with st.expander("Windows 'bilinmeyen uygulama' uyarisi verirse"):
        st.markdown(
            "Zip icinden cikan dosyalar internetten indirildigi icin Windows bir "
            "uyari gosterebilir. **Ek bilgi > Yine de calistir** diyebilirsiniz. "
            "Paketin icindeki `python.exe`, Python Software Foundation tarafindan "
            "imzalanmis resmi dosyadir; `BASLAT.bat` ve `agent.py` dosyalarinin "
            "icerigini bir metin duzenleyiciyle acip okuyabilirsiniz."
        )

with step_right:
    st.markdown("### 2. Kodu girin")
    with st.form("pair_form"):
        code = st.text_input(
            "Eslestirme kodu",
            max_chars=6,
            placeholder="ORN: K7M2QP",
            help="Ajan penceresinde yazan 6 haneli kod",
        )
        submitted = st.form_submit_button("Baglan", type="primary", use_container_width=True)

    if submitted:
        code = (code or "").strip().upper()
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
                st.success("Baglanti kuruldu.")
                st.rerun()

    st.markdown("---")
    st.markdown("### Guvenlik")
    st.markdown(
        """
- Ajan yalnizca **disari** baglanti kurar; bilgisayarinizda port acilmaz.
- Yapabilecegi islemler sabit bir listeyle sinirlidir: kombinasyon adlarini
  okumak, rapor birimini ayarlamak ve ETABS tablolarini okumak.
- Modelinizde **degisiklik yapmaz**, dosyalarinizi okumaz.
- Okunan tablolar hesaplama bittikten sonra sunucuda saklanmaz.
        """
    )

with st.expander("Sorun mu yasiyorsunuz?"):
    st.markdown(
        """
**"Acik bir ETABS bulunamadi"** — ETABS'i acip modeli yukleyin. ETABS'i
yonetici olarak calistirdiysaniz ajani da yonetici olarak calistirin.

**"Sunucuya baglanilamadi"** — Kurumsal aginizda vekil sunucu olabilir. BT
biriminizden ajan paketindeki `agent_config.json` icinde yazan adrese erisim
izni isteyin.

**"Tablo bos dondu"** — ETABS'te analizi calistirdiginizdan emin olun.

**Kodun suresi doldu** — Ajani kapatip yeniden baslatin; yeni kod uretilir.
        """
    )
