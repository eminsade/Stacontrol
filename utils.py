import os
import io
import streamlit as st
import hashlib
import pandas as pd
from streamlit_cookies_manager import EncryptedCookieManager
from session_config import init_session_state

# 1. Çerez Yöneticisini Başlatma
cookies = EncryptedCookieManager(
    prefix="my_app/",
    password=os.environ.get("COOKIES_PASSWORD", "My secret password"),
)

# 2. Çerez Hazır mı Kontrolü (HAYATİ KISIM)
if not cookies.ready():
    st.stop()

# 3. Session State Başlatma
init_session_state()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def to_excel(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """DataFrame'i biçimlendirilmiş Excel baytlarına dönüştürür."""
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine="xlsxwriter")
    df.to_excel(writer, sheet_name=sheet_name, index=False)
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]
    for idx, col in enumerate(df.columns):
        series_str = df[col].astype(str)
        max_len = max(series_str.apply(len).max() if not series_str.empty else 0, len(str(col)))
        worksheet.set_column(idx, idx, max_len + 3)
    writer.close()
    return output.getvalue()

def top_right_login():
    """
    Sayfanın sağ üst köşesinde Giriş Yap / Kayıt Ol butonlarını
    veya giriş yapıldıysa 'Hoşgeldiniz' butonu ve 'Çıkış Yap' butonunu yan yana gösterir.
    """
    col1, col2 = st.columns([8, 2])
    
    with col2:
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
                    '<a href="/üyelik_girisi" target="_self" style="text-decoration:none; display:block;">'
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