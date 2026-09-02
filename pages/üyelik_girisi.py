import streamlit as st

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
from utils import hash_password, cookies
from database import verify_user
from session_config import init_session_state

init_session_state()
setup_sidebar()

st.title("Üyelik Girişi")

# Eğer kullanıcı zaten giriş yaptıysa anasayfaya yönlendir
if st.session_state.get("logged_in", False):
    st.info("Giriş Yapıldı!")
    st.switch_page("anasayfa.py")
else:
    with st.form("login_form"):
        username = st.text_input("Kullanıcı Adı")
        password = st.text_input("Şifre", type="password")
        submitted = st.form_submit_button("Giriş Yap")
        
        if submitted:
            if username and password:
                hashed_password = hash_password(password)
                if verify_user(username, hashed_password):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username

                    try:
                        cookies["logged_in"] = "True"
                        cookies["username"] = username
                        cookies.save()
                    except Exception:
                        pass

                    st.success(f"Hoşgeldiniz, {username}!")
                    st.switch_page("anasayfa.py")
                else:
                    st.error("Geçersiz kullanıcı adı veya şifre")
            else:
                st.error("Lütfen tüm alanları doldurunuz.")

st.markdown("Hesabınız yoksa, [Kayıt Ol](./kayit_ol) sayfasına giderek üye olabilirsiniz.")