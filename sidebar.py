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
        if st.session_state.get("etabs_connected"):
            st.success(f"🟢 **Bağlandı**\n\n📁 {st.session_state.get('etabs_model_name', 'Aktif Model')}")
        else:
            status = check_etabs_status()
            if status.get("connected"):
                st.success(f"🟢 **Bağlandı ({status['mode'].upper()})**\n\n📁 {status['model_name']}")
            else:
                st.warning("🔴 **ETABS Bağlantısı Yok**")

        # Kullanıcı işlemleri
        st.markdown("---")
        if st.session_state.get("logged_in", False):
            st.write(f"Hoşgeldiniz, **{st.session_state['username']}**!")
            if st.button("Çıkış Yap", key="logout"):
                st.session_state["logged_in"] = False
                st.session_state.pop("username", None)
                cookies = st.session_state.get("cookies")
                if cookies:
                    try:
                        cookies["logged_in"] = "False"
                        cookies.pop("username", None)
                        cookies.save()
                    except Exception:
                        pass
                st.success("Çıkış yapıldı!")
                st.switch_page("pages/uyelik_girisi.py")
        else:
            st.info("Lütfen giriş yapın.")
            st.page_link("pages/uyelik_girisi.py", label="Giriş Yap", icon="🔑")
            st.page_link("pages/kayit_ol.py", label="Kayıt Ol", icon="✍️")