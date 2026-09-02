import streamlit as st
from etabs_service import check_etabs_status

def setup_sidebar():
    with st.sidebar:
        st.title("Betonarme Hesap Aracı")
        st.markdown("---")
        
        # Navigasyon
        st.markdown("### Navigasyon")
        st.page_link("anasayfa.py", label="Anasayfa", icon="🏠")
        st.page_link("pages/1_goreli_kat_otelemesi.py", label="Göreli Kat Ötelemesi", icon="📏")
        st.page_link("pages/2_kolon_kapasite.py", label="Kolon Kapasite", icon="🏢")
        st.page_link("pages/3_Hesaplama_Gecmisi.py", label="Hesaplama Geçmişi", icon="📜")
        st.page_link("pages/4_perde_kapasite.py", label="Perde Kapasite", icon="🛡️")
        st.page_link("pages/5_perde_kesme.py", label="Perde Kesme", icon="✂️")
        st.page_link("pages/6_kiris_kesme.py", label="Kiriş Kesme", icon="🔧")
        st.page_link("pages/metraj_hesaplama.py", label="Metraj Hesaplama", icon="📐")
        
        # ETABS Canlı Bağlantı Durumu
        st.markdown("---")
        st.markdown("### ETABS Durumu")
        status = check_etabs_status()
        if status["connected"]:
            st.success(f"🟢 **Bağlı ({status['mode'].upper()})**\n\n📁 {status['model_name']}")
        else:
            st.warning("🔴 **ETABS Bağlantısı Yok**")
            with st.expander("❓ Nasıl Bağlanılır?"):
                st.caption(
                    "Web üzerinden ETABS'e bağlanmak için yerel bilgisayarınızda **STACONT Bridge** "
                    "aracını çalıştırınız (`http://127.0.0.1:8765`)."
                )

        # Kullanıcı işlemleri
        st.markdown("---")
        if st.session_state.get("logged_in", False):
            st.write(f"Hoşgeldiniz, **{st.session_state['username']}**!")
            if st.button("Çıkış Yap", key="logout"):
                st.session_state["logged_in"] = False
                st.session_state.pop("username", None)
                cookies = st.session_state.get("cookies")
                if cookies:
                    cookies["logged_in"] = "False"
                    cookies.pop("username", None)
                    cookies.save()
                st.success("Çıkış yapıldı!")
                st.switch_page("pages/üyelik_girisi.py")
        else:
            st.info("Lütfen giriş yapın.")
            st.page_link("pages/üyelik_girisi.py", label="Giriş Yap", icon="🔑")
            st.page_link("pages/kayit_ol.py", label="Kayıt Ol", icon="✍️")