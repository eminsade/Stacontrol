import streamlit as st
from PIL import Image
import base64
from io import BytesIO
import os

# Page configuration
st.set_page_config(
    page_title="Stacontrol",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
from utils import top_right_login
from session_config import init_session_state
from bridge_client import render_bridge_status

# Initialize session state
init_session_state()
setup_sidebar()
top_right_login()

# Professional, modern SaaS design
st.markdown("""
    <style>
    .stApp {
        padding-top: 0 !important;
        background: #f8fafc;
        min-height: 100vh;
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
        color: #0f172a;
    }

    .main-title {
        font-size: 40px;
        font-weight: 800;
        color: #0f172a;
        text-align: center;
        margin-top: 10px;
        margin-bottom: 4px;
        letter-spacing: -0.8px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
    }
    .subtitle {
        font-size: 15px;
        color: #64748b;
        text-align: center;
        max-width: 800px;
        margin: 0 auto 20px auto;
        line-height: 1.5;
    }

    /* Kart Dış Çerçevesi */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: #ffffff !important;
        border-radius: 16px !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.04) !important;
        transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease !important;
        padding: 10px !important;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-4px) !important;
        box-shadow: 0 12px 28px rgba(37, 99, 235, 0.1) !important;
        border-color: #cbd5e1 !important;
    }

    /* Kart İçi İçerik */
    .card-content {
        padding: 12px 10px 5px 10px;
        text-align: center;
        height: 175px;
        display: flex;
        flex-direction: column;
        align-items: center;
    }
    .card-icon {
        width: 52px;
        height: 52px;
        object-fit: contain;
        margin-bottom: 8px;
        transition: transform 0.3s ease;
    }
    [data-testid="stVerticalBlockBorderWrapper"]:hover .card-icon {
        transform: scale(1.1);
    }
    .card-title {
        font-size: 18px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 6px;
    }
    .card-text {
        color: #64748b;
        font-size: 13.5px;
        line-height: 1.45;
    }

    /* Buton Tasarımı (st.page_link) */
    [data-testid="stPageLink-NavLink"] {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        text-align: center !important;
        justify-content: center !important;
        margin: 5px 0 2px 0 !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
        transition: all 0.2s ease !important;
        border: none !important;
    }
    [data-testid="stPageLink-NavLink"]:hover {
        background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.35) !important;
        transform: translateY(-1px) !important;
    }
    [data-testid="stPageLink-NavLink"] p {
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        letter-spacing: 0.2px !important;
    }

    .footer {
        text-align: center;
        color: #94a3b8;
        padding: 35px 0 20px 0;
        font-size: 13.5px;
        border-top: 1px solid #e2e8f0;
        margin-top: 40px;
    }
    </style>
""", unsafe_allow_html=True)

# Helper function to convert image to base64
def get_image_base64(filename):
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    file_path = os.path.join(assets_dir, filename)
    if os.path.exists(file_path):
        try:
            img = Image.open(file_path)
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode()}"
        except Exception:
            return ""
    return ""

img_goreli = get_image_base64("goreli_kat_otelemesi.png")
img_kolon = get_image_base64("kolon_kapasite.png")
img_perde_kap = get_image_base64("perde_kapasite.png")
img_perde_kes = get_image_base64("perde_kesme.png")
img_kiris_kes = get_image_base64("kiris_kesme.png")
img_metraj = get_image_base64("metraj.png")
img_logo = get_image_base64("logo.png")

# Main Title
logo_html = f'<img src="{img_logo}" style="width: 48px; height: 48px; vertical-align: middle;">' if img_logo else '🔨'
st.markdown(f"""
    <h1 class='main-title'>
        {logo_html} Stacontrol
    </h1>
    <div class='subtitle'>TBDY 2018 ve TS 500 uyumlu otomatik betonarme yapı elemanları analiz ve kontrol platformu</div>
""", unsafe_allow_html=True)

# Canlı ETABS Durumu (Kullanıcı Tarayıcısından Doğrudan Sorgulanır)
bridge_status = render_bridge_status()

# İndirme Kılavuzu (Bağlı değilse göster)
if not st.session_state.get("etabs_connected", False):
    with st.expander("📥 STACONT Bridge'i İndir ve 3 Adımda Bağlan", expanded=False):
        st.markdown("""
        **Nasıl Bağlanılır?**
        1. Aşağıdaki butondan **`bridge_agent.py`** veya **`STACONT_Bridge_Baslat.bat`** dosyasını indirin.
        2. İndirdiğiniz dosyayı bilgisayarınızda ETABS açıkken çift tıklayarak çalıştırın.
        3. Sayfayı yenileyin; yukarıdaki durum **🟢 ETABS Bağlandı** olarak güncellenecektir!
        """)
        
        bridge_py_path = os.path.join(os.path.dirname(__file__), "bridge_agent.py")
        bridge_bat_path = os.path.join(os.path.dirname(__file__), "STACONT_Bridge_Baslat.bat")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            if os.path.exists(bridge_py_path):
                with open(bridge_py_path, "r", encoding="utf-8") as f:
                    st.download_button(
                        label="📥 bridge_agent.py İndir",
                        data=f.read(),
                        file_name="bridge_agent.py",
                        mime="text/x-python",
                        use_container_width=True
                    )
        with col_d2:
            if os.path.exists(bridge_bat_path):
                with open(bridge_bat_path, "r", encoding="utf-8") as f:
                    st.download_button(
                        label="📥 Tek Tıkla Başlatıcı (.bat) İndir",
                        data=f.read(),
                        file_name="STACONT_Bridge_Baslat.bat",
                        mime="application/x-bat",
                        use_container_width=True
                    )

# Cards (First Row)
col1, col2, col3 = st.columns([1, 1, 1], gap="medium")

with col1:
    with st.container(border=True):
        icon_html = f'<img src="{img_goreli}" class="card-icon">' if img_goreli else '<div style="font-size:36px; margin-bottom:8px;">📏</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Göreli Kat Ötelemesi</div>
                <div class="card-text">TBDY 2018 Bölüm 4.9.1 uyarınca X ve Y yönü göreli kat ötelemesi ve grafik tahkiki.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/1_goreli_kat_otelemesi.py", label="Analiz Yap", use_container_width=True)

with col2:
    with st.container(border=True):
        icon_html = f'<img src="{img_kolon}" class="card-icon">' if img_kolon else '<div style="font-size:36px; margin-bottom:8px;">🏢</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Kolon Eksenel</div>
                <div class="card-text">TS 500 ve TBDY 2018 kolon eksenel kuvvet ve kapasite kontrolü.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/2_kolon_kapasite.py", label="Analiz Yap", use_container_width=True)

with col3:
    with st.container(border=True):
        icon_html = f'<img src="{img_perde_kap}" class="card-icon">' if img_perde_kap else '<div style="font-size:36px; margin-bottom:8px;">🛡️</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Perde Eksenel</div>
                <div class="card-text">Perde eksenel basınç gerilmesi ve taşıma gücü sınır kontrolleri.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/4_perde_kapasite.py", label="Analiz Yap", use_container_width=True)

# Cards (Second Row)
col4, col5, col6 = st.columns([1, 1, 1], gap="medium")

with col4:
    with st.container(border=True):
        icon_html = f'<img src="{img_perde_kes}" class="card-icon">' if img_perde_kes else '<div style="font-size:36px; margin-bottom:8px;">✂️</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Perde Kesme</div>
                <div class="card-text">Dinamik kesme büyütmesi (Denk 7.16), gövde ezilme ve donatı kesme tahkiki.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/5_perde_kesme.py", label="Analiz Yap", use_container_width=True)

with col5:
    with st.container(border=True):
        icon_html = f'<img src="{img_kiris_kes}" class="card-icon">' if img_kiris_kes else '<div style="font-size:36px; margin-bottom:8px;">🔧</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Kiriş Kesme</div>
                <div class="card-text">TBDY 2018 kiriş enine donatı ve kesme güvenliği tahkikleri.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/6_kiris_kesme.py", label="Analiz Yap", use_container_width=True)

with col6:
    with st.container(border=True):
        icon_html = f'<img src="{img_metraj}" class="card-icon">' if img_metraj else '<div style="font-size:36px; margin-bottom:8px;">📐</div>'
        st.markdown(f"""
            <div class="card-content">
                {icon_html}
                <div class="card-title">Metraj & 3D Model</div>
                <div class="card-text">Kat ve eleman bazında beton, kalıp, donatı metrajı ve interaktif 3D model.</div>
            </div>
        """, unsafe_allow_html=True)
        st.page_link("pages/metraj_hesaplama.py", label="Analiz Yap", use_container_width=True)

# Footer
st.markdown("""
    <div class="footer">
        © 2025 STACONT | Betonarme Yapısal Analiz ve Kontrol Platformu
    </div>
""", unsafe_allow_html=True)