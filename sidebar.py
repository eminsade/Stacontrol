import streamlit as st


def setup_sidebar():
    """Kenar cubugu: navigasyon, ETABS ajan durumu ve kullanici islemleri.

    Not: Buradaki dosya yollari diskteki adlarla HARF HARF ayni olmalidir.
    Windows'ta buyuk/kucuk harf farki gorulmez ama uretim sunucusu (Linux)
    dosya adlarinda harf duyarlidir; yanlis yazim orada sayfayi kirar.
    """
    with st.sidebar:
        st.title("Betonarme Hesap Aracı")
        st.markdown("---")

        st.markdown("### Navigasyon")

        st.page_link("anasayfa.py", label="Anasayfa", icon="🏠")
        st.page_link("pages/0_ETABS_Baglantisi.py", label="ETABS Bağlantısı", icon="🔌")
        st.page_link("pages/1_goreli_kat_otelemesi.py", label="Göreli Kat Ötelemesi", icon="📏")
        st.page_link("pages/2_kolon_kapasite.py", label="Kolon Kapasite", icon="🏢")
        st.page_link("pages/3_Hesaplama_Gecmisi.py", label="Hesaplama Geçmişi", icon="📜")
        st.page_link("pages/4_perde_kapasite.py", label="Perde Kapasite", icon="🛡️")
        st.page_link("pages/5_perde_kesme.py", label="Perde Kesme", icon="✂️")
        st.page_link("pages/6_kiris_kesme.py", label="Kiriş Kesme", icon="🔧")
        st.page_link("pages/metraj_hesaplama.py", label="Metraj Hesaplama", icon="📐")

        st.markdown("---")

        if st.session_state.get("logged_in", False):
            _render_agent_badge()
            st.write(f"Hoşgeldiniz, {st.session_state['username']}!")

            if st.button("Çıkış Yap", key="logout"):
                st.session_state["logged_in"] = False
                st.session_state.pop("username", None)
                cookies = st.session_state.get("cookies")
                if cookies:
                    cookies["logged_in"] = "False"
                    cookies["username"] = ""
                    cookies.save()
                st.success("Çıkış yapıldı!")
                st.switch_page("pages/uyelik_girisi.py")
        else:
            st.info("Lütfen giriş yapın.")
            st.page_link("pages/uyelik_girisi.py", label="Giriş Yap", icon="🔑")
            st.page_link("pages/kayit_ol.py", label="Kayıt Ol", icon="✍️")


def _render_agent_badge():
    """ETABS ajaninin durumunu kisa bir rozet olarak gosterir.

    Kopruye ulasilamasa bile kenar cubugu calismaya devam etmeli; bu yuzden
    tum hatalar yutulur.
    """
    try:
        from etabs_bridge.streamlit_ui import agent_status, current_username

        username = current_username()
        if not username:
            return
        status = agent_status(username)
    except Exception:
        return

    if status.get("connected") and status.get("online"):
        st.success("ETABS bağlı", icon="🟢")
    elif status.get("connected"):
        st.warning("Ajan çevrimdışı", icon="🟡")
    else:
        st.caption("🔌 ETABS bağlı değil")
