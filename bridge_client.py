import os
import streamlit as st
import streamlit.components.v1 as components

_component_dir = os.path.join(os.path.dirname(__file__), "bridge_component")

if os.path.exists(_component_dir):
    _bridge_component = components.declare_component("stacont_bridge_component", path=_component_dir)
else:
    _bridge_component = None

def render_bridge_status(key="etabs_bridge_status_widget"):
    """
    Kullanıcının tarayıcısından yerel http://127.0.0.1:8765 adresini sorgular.
    Durumu ekranda gösterir; model adını, kombinasyonları, yük durumlarını ve katları kaydeder.
    """
    if _bridge_component is None:
        return None
    
    res = _bridge_component(action="status", endpoint="/status", key=key)
    if res and isinstance(res, dict):
        if res.get("etabs_connected"):
            st.session_state["etabs_connected"] = True
            st.session_state["etabs_model_name"] = res.get("model_name", "Aktif Model")
            
            tunnel = res.get("tunnel_url")
            if tunnel:
                st.session_state["bridge_url"] = tunnel

            if res.get("combinations"):
                st.session_state["etabs_combinations"] = res.get("combinations", [])
            if res.get("load_cases"):
                st.session_state["etabs_load_cases"] = res.get("load_cases", [])
            if res.get("stories"):
                st.session_state["etabs_stories"] = res.get("stories", [])
            st.session_state["etabs_info"] = res
        else:
            st.session_state["etabs_connected"] = False
    return res

def render_bridge_fetcher(endpoint: str, params: dict = None, bundle_name: str = "bundle", key: str = "bridge_fetcher"):
    """
    Kullanıcının tarayıcısı üzerinden yerel 127.0.0.1:8765 adresinden tablo verisi çeker.
    Bulut kısıtlamalarını ve Cloudflare 530 hatalarını tamamen aşar.
    """
    if _bridge_component is None:
        return None
    return _bridge_component(action="fetch_bundle", endpoint=endpoint, params=params or {}, bundle_name=bundle_name, key=key)

def fetch_bundle(*args, **kwargs):
    """Geriye dönük uyumluluk."""
    return render_bridge_fetcher(*args, **kwargs)
