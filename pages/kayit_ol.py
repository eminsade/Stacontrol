import streamlit as st

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
# Gerekli fonksiyonları içe aktarıyoruz
from utils import hash_password
from database import register_user
from session_config import init_session_state

init_session_state()

setup_sidebar()

st.title("Kayıt Ol")

username = st.text_input("Kullanıcı Adı")
password = st.text_input("Şifre", type="password")
password2 = st.text_input("Şifreyi Tekrar Giriniz", type="password")

if st.button("Kayıt Ol"):
    if not username or not password or not password2:
        st.error("Lütfen tüm alanları doldurunuz.")
    elif password != password2:
        st.error("Şifreler eşleşmiyor!")
    else:
        hashed_password = hash_password(password)
        success, message = register_user(username, hashed_password)
        if success:
            st.success(message)
        else:
            st.error(message)

st.markdown("Zaten hesabınız varsa, [Üyelik Girişi](./üyelik_Girisi) sayfasından giriş yapabilirsiniz.")
