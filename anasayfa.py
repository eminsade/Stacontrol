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
from etabs_service import check_etabs_status

# Initialize session state
init_session_state()

setup_sidebar()

# Right-top login/register buttons
top_right_login()

# ETABS Durumu Kontrolü
etabs_info = check_etabs_status()

# Enhanced CSS styles for a professional look
st.markdown("""
    <style>
    .stApp {
        padding-top: 0 !important;
        background: linear-gradient(135deg, #f0f4f8 0%, #e2e8f0 100%);
        min-height: 100vh;
    }

    body {
        font-family: 'Inter', sans-serif;
        color: #1e293b;
    }

    .main-title {
        font-size: 42px;
        font-weight: 800;
        color: #1e293b;
        text-align: center;
        margin-top: 15px;
        margin-bottom: 5px;
        letter-spacing: -1px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
    }
    .subtitle {
        font-size: 16px;
        color: #64748b;
        text-align: center;
        max-width: 900px;
        margin: 0 auto 30px auto;
        line-height: 1.5;
    }
    
    .etabs-file-info {
        font-size: 14px;
        color: #2563eb;
        text-align: center;
        font-weight: 600;
        background-color: #eff6ff;
        border: 1px solid #bfdbfe;
        padding: 8px 16px;
        border-radius: 8px;
        margin: 0 auto 25px auto;
        max-width: 800px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }
    .etabs-file-info-warn {
        font-size: 14px;
        color: #b45309;
        text-align: center;
        font-weight: 600;
        background-color: #fef3c7;
        border: 1px solid #fde68a;
        padding: 8px 16px;
        border-radius: 8px;
        margin: 0 auto 25px auto;
        max-width: 800px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }

    .card {
        padding: 20px;
        border-radius: 12px;
        background: #ffffff;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
        margin-bottom: 25px;
        text-align: center;
        width: 100%;
        height: 230px;
        margin-left: auto;
        margin-right: auto;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .card:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
    }
    .card-title {
        font-size: 20px;
        font-weight: 700;
        margin-bottom: 8px;
        color: #1e293b;
    }
    .card-text {
        color: #64748b;
        font-size: 14px;
        line-height: 1.4;
        margin-bottom: 15px;
        flex-grow: 1;
    }
    .icon {
        font-size: 32px;
        margin-bottom: 10px;
        color: #3b82f6;
        transition: transform 0.3s ease;
    }
    .card:hover .icon {
        transform: scale(1.15);
    }

    .analiz-button {
        background: linear-gradient(90deg, #3b82f6 0%, #60a5fa 100%);
        color: white !important;
        padding: 8px 20px;
        border-radius: 6px;
        border: none;
        text-decoration: none;
        font-size: 14px;
        font-weight: 600;
        display: block;
        transition: background 0.3s ease, transform 0.2s ease;
        width: 150px;
        margin: 0 auto;
        text-align: center;
    }
    .analiz-button:hover {
        background: linear-gradient(90deg, #2563eb 0%, #3b82f6 100%);
        transform: translateY(-2px);
    }

    .footer {
        text-align: center;
        color: #64748b;
        padding: 30px 0;
        font-size: 14px;
        border-top: 1px solid #e2e8f0;
        margin-top: 40px;
        background: #ffffff;
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
logo_html = f'<img src="{img_logo}" style="width: 50px; height: 50px; vertical-align: middle;">' if img_logo else '🔨'
st.markdown(f"""
    <h1 class='main-title'>
        {logo_html} Stacontrol
    </h1>
    <div class='subtitle'>TBDY 2018 ve TS 500 uyumlu otomatik betonarme yapı elemanları analiz ve kontrol platformu</div>
""", unsafe_allow_html=True)

# ETABS dosya bilgisi gösterimi
if etabs_info["connected"]:
    st.markdown(f"""
        <div class='etabs-file-info'>
            <span>🟢</span> <b>ETABS Bağlandı:</b> {etabs_info['model_name']} ({etabs_info['mode'].upper()} modu)
        </div>
    """, unsafe_allow_html=True)
else:
    st.markdown(f"""
        <div class='etabs-file-info-warn'>
            <span>⚠️</span> <b>ETABS Bağlantısı Bekleniyor:</b> Web üzerinden otomatik analiz için yerel bilgisayarınızda <b>STACONT Bridge</b>'i çalıştırınız.
        </div>
    """, unsafe_allow_html=True)

# Cards (First Row)
col1, col2, col3 = st.columns([1, 1, 1], gap="medium")

with col1:
    icon_html = f'<img src="{img_goreli}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_goreli else '<div class="icon">📏</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Göreli Kat Ötelemesi</div>
                <div class="card-text">TBDY 2018 Bölüm 4.9.1 uyarınca X ve Y yönü göreli kat ötelemesi ve grafik tahkiki.</div>
            </div>
            <a href="/1_goreli_kat_otelemesi" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

with col2:
    icon_html = f'<img src="{img_kolon}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_kolon else '<div class="icon">🏢</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Kolon Eksenel</div>
                <div class="card-text">TS 500 ve TBDY 2018 kolon eksenel kuvvet ve kapasite kontrolü.</div>
            </div>
            <a href="/2_kolon_kapasite" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

with col3:
    icon_html = f'<img src="{img_perde_kap}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_perde_kap else '<div class="icon">🛡️</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Perde Eksenel</div>
                <div class="card-text">Perde eksenel basınç gerilmesi ve taşıma gücü sınır kontrolleri.</div>
            </div>
            <a href="/4_perde_kapasite" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

# Cards (Second Row)
col4, col5, col6 = st.columns([1, 1, 1], gap="medium")

with col4:
    icon_html = f'<img src="{img_perde_kes}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_perde_kes else '<div class="icon">✂️</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Perde Kesme</div>
                <div class="card-text">Dinamik kesme büyütmesi (Denk 7.16), gövde ezilme ve donatı kesme tahkiki.</div>
            </div>
            <a href="/5_perde_kesme" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

with col5:
    icon_html = f'<img src="{img_kiris_kes}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_kiris_kes else '<div class="icon">🔧</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Kiriş Kesme</div>
                <div class="card-text">TBDY 2018 kiriş enine donatı ve kesme güvenliği tahkikleri.</div>
            </div>
            <a href="/6_kiris_kesme" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

with col6:
    icon_html = f'<img src="{img_metraj}" style="width: 50px; height: 50px; margin-bottom: 5px;" class="icon">' if img_metraj else '<div class="icon">📐</div>'
    st.markdown(f"""
        <div class="card">
            <div>
                {icon_html}
                <div class="card-title">Metraj & 3D Model</div>
                <div class="card-text">Kat ve eleman bazında beton, kalıp, donatı metrajı ve interaktif 3D model.</div>
            </div>
            <a href="/metraj_hesaplama" target="_self" class="analiz-button">Analiz Yap</a>
        </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown("""
    <div class="footer">
        © 2025 STACONT | Betonarme Yapısal Analiz ve Kontrol Platformu
    </div>
""", unsafe_allow_html=True)