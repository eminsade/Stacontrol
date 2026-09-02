import os
import io
import streamlit as st
import hashlib
import pandas as pd
from session_config import init_session_state

# Modern Streamlit uyumluluk yaması
if not hasattr(st, "cache"):
    st.cache = st.cache_resource

# Güvenli Çerez Yöneticisi Başlatma
try:
    from streamlit_cookies_manager import EncryptedCookieManager
    cookies = EncryptedCookieManager(
        prefix="my_app/",
        password=os.environ.get("COOKIES_PASSWORD", "MySecretPassword123!"),
    )
except Exception:
    class DummyCookies(dict):
        def ready(self):
            return True
        def save(self):
            pass
        def get(self, k, default=None):
            return super().get(k, default)
    cookies = DummyCookies()

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
    col1, col2 = st.columns([7.5, 2.5])
    
    with col2:
        try:
            if hasattr(cookies, 'ready') and cookies.ready():
                if cookies.get("logged_in") == "True":
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = cookies.get("username", "")
        except Exception:
            pass

        if st.session_state.get("logged_in", False):
            welcome_col, logout_col = st.columns([1.5, 1])
            with welcome_col:
                st.markdown(
                    f'<div style="background-color:#4CAF50; color:white; padding:6px 12px; '
                    f'border-radius:6px; text-align:center; font-size:13px; font-weight:600; margin-top:3px;">'
                    f'👤 {st.session_state["username"]}</div>',
                    unsafe_allow_html=True
                )
            with logout_col:
                if st.button("Çıkış", type="secondary", use_container_width=True):
                    st.session_state.clear()
                    try:
                        cookies["logged_in"] = "False"
                        cookies["username"] = ""
                        cookies.save()
                    except Exception:
                        pass
                    st.rerun()
        else:
            login_col, register_col = st.columns([1, 1])
            with login_col:
                st.page_link("pages/uyelik_girisi.py", label="Giriş Yap", icon="🔑", use_container_width=True)
            with register_col:
                st.page_link("pages/kayit_ol.py", label="Kayıt Ol", icon="✍️", use_container_width=True)