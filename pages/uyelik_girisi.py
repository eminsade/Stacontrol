import streamlit as st

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
# Gerekli fonksiyonları içe aktarıyoruz
from utils import cookies
from database import verify_user, normalize_username
from session_config import init_session_state

init_session_state()

setup_sidebar()

st.title("Üyelik Girişi")

# Eğer kullanıcı zaten giriş yaptıysa anasayfaya yönlendir
if st.session_state.get("logged_in", False):
    st.info("Giriş Yapıldı!")
    st.switch_page("anasayfa.py")  # Anasayfaya yönlendirme
else:
    with st.form("login_form"):
        username = st.text_input("Kullanıcı Adı")
        password = st.text_input("Şifre", type="password")
        submitted = st.form_submit_button("Giriş Yap")
        
        if submitted:
            if username and password:
                # Şifre düz metin doğrulanır; karşılaştırma bcrypt ile
                # database.verify_user içinde yapılır.
                if verify_user(username, password):
                    username = normalize_username(username)
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username

                    # Çerezlere kaydet
                    cookies["logged_in"] = "True"
                    cookies["username"] = username
                    cookies.save()

                    st.success(f"Hoşgeldiniz, {username}!")
                    st.switch_page("anasayfa.py")  # Anasayfaya yönlendirme
                else:
                    st.error("Geçersiz kullanıcı adı veya şifre")
            else:
                st.error("Lütfen tüm alanları doldurunuz.")

st.markdown("Hesabınız yoksa, [Kayıt Ol](./kayit_ol) sayfasına giderek üye olabilirsiniz.")