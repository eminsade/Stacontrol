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
    Durumu ekranda gösterir, kombinasyonları ve yük durumlarını Streamlit oturumuna aktarır.
    """
    if _bridge_component is None:
        return None
    
    res = _bridge_component(action="status", endpoint="/status", key=key)
    if res and isinstance(res, dict):
        if res.get("etabs_connected"):
            st.session_state["etabs_connected"] = True
            st.session_state["etabs_model_name"] = res.get("model_name", "Aktif Model")
            if res.get("combinations"):
                st.session_state["etabs_combinations"] = res.get("combinations", [])
            if res.get("load_cases"):
                st.session_state["etabs_load_cases"] = res.get("load_cases", [])
            st.session_state["etabs_info"] = res
        else:
            st.session_state["etabs_connected"] = False
    return res

def fetch_bundle(endpoint: str, params: dict = None, bundle_name: str = "bundle", key: str = "fetch_bundle_key"):
    """
    Tarayıcı üzerinden yerel Bridge'den veri paketi çeker.
    """
    if _bridge_component is None:
        return None
    return _bridge_component(action="fetch_bundle", endpoint=endpoint, params=params or {}, bundle_name=bundle_name, key=key)
