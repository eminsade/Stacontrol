import io
import streamlit as st
import json
import numpy as np
import pandas as pd
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplamalar, get_hesaplama_by_id
from utils import top_right_login, to_excel
from session_config import init_session_state
from constants import CONCRETE_OPTIONS
from bridge_client import render_bridge_status, render_bridge_fetcher
import etabs_service

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar

# Session state başlatma
init_session_state()
setup_sidebar()
top_right_login()

st.title("Perde Kapasite Kontrolü")

# Canlı ETABS Durumu (Tarayıcıdan sorgulanır, kombinasyonları ve katları yükler)
render_bridge_status(key="perde_kap_bridge_status")

tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:
    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    concrete_mapping = CONCRETE_OPTIONS

    # AG Grid ayarları
    grid_options = {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter", "maxWidth": 90, "minWidth": 80},
            {"headerName": "Perde", "field": "Pier", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Uzunluk (m)", "field": "WidthBot", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Number(params.value).toFixed(2) : ''; }"},
            {"headerName": "Kalınlık (m)", "field": "ThickBot", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Number(params.value).toFixed(2) : ''; }"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
             "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_mapping.keys())}},
            {"headerName": "Kombinasyon", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Ndm (kN)", "field": "Deprem Yük", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "Ach (m²)", "field": "Ach", "editable": True, "filter": "agSetColumnFilter",
             "valueGetter": "data.WidthBot * data.ThickBot",
             "valueFormatter": "function(params){ return params.value != null ? Number(params.value).toFixed(2) : ''; }"},
            {"headerName": "MaxNdm", "field": "TBDY_Hesap", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "0.35 * (data['fck'] || 0) * (data.WidthBot * data.ThickBot)",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "% Ndm/MaxNdm", "field": "%Ndm/MaxNdm", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "((Math.abs(data['Deprem Yük'] || 0) / (0.35 * (data['fck'] || 1) * (data.WidthBot * data.ThickBot))) * 100).toFixed(1) + '%'"},
            {"headerName": "Durum", "field": "TBDY_Durum", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "(Math.abs(data['Deprem Yük'] || 0) < (0.35 * (data['fck'] || 0) * (data.WidthBot * data.ThickBot))) ? '✅' : '❌'"}
        ],
        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
        "onCellValueChanged": "function(event) { event.api.refreshCells(); }",
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "enableRangeSelection": True,
        "enableFillHandle": True
    }

    if saved_id:
        username = st.session_state.get("username", "")
        record = get_hesaplama_by_id(saved_id, username)
        if record is not None:
            st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
            sonuc_dict = json.loads(record["sonuc"])
            updated_df = pd.DataFrame(sonuc_dict["final_table"])

            grid_response = AgGrid(
                updated_df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key=f"aggrid_saved_{saved_id}"
            )

            st.download_button(
                "Excel Olarak İndir",
                data=to_excel(updated_df),
                file_name=f"{record['hesap_tipi']}.xlsx",
                mime="application/vnd.ms-excel",
            )
        else:
            st.error("Kayıt bulunamadı veya erişim yetkiniz yok.")
            st.stop()
    else:
        combo_names = st.session_state.get("etabs_combinations", [])
        if not combo_names:
            combo_names = etabs_service.get_load_combinations()

        if not combo_names:
            st.warning("⚠️ ETABS'e bağlanılıyor veya kombinasyon listesi yükleniyor... Lütfen STACONT Bridge'in açık olduğundan emin olun.")
            st.stop()

        st.subheader("Deprem Kombinasyon Seçimi")
        col1, col2 = st.columns(2)
        with col1:
            main_deprem_combo = st.selectbox("Deprem Kombinasyon", combo_names, key="main_deprem_combo")
            selected_concrete = st.selectbox("Beton Sınıfı", list(concrete_mapping.keys()), key="concrete_class")
            concrete_value = concrete_mapping[selected_concrete]

        with col2:
            is_basement = st.checkbox("YAPI BODRUMLU MU?")
            if is_basement:
                basement_deprem_combo = st.selectbox("Bodrum Deprem Kombinasyon", combo_names, key="basement_deprem_combo")
                story_options = st.session_state.get("etabs_stories", [])
                if not story_options:
                    story_options = etabs_service.get_story_names()
                basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", options=story_options, key="basement_stories")

        if st.button("Final Tabloyu Getir", key="btn_run_perde"):
            st.session_state["fetching_perde_active"] = True

        if st.session_state.get("fetching_perde_active"):
            bundle = None
            SapModel = etabs_service.get_active_sap_model()
            if SapModel:
                bundle = etabs_service.get_pier_bundle(
                    combo=main_deprem_combo,
                    basement_combo=basement_deprem_combo if is_basement else ""
                )
            else:
                bundle = render_bridge_fetcher(
                    endpoint="/api/pier_bundle",
                    params={
                        "combo": main_deprem_combo,
                        "basement_combo": basement_deprem_combo if is_basement else ""
                    },
                    bundle_name="pier_bundle",
                    key="perde_bridge_fetcher_widget"
                )

            if bundle and isinstance(bundle, dict) and bundle.get("success"):
                st.session_state["fetching_perde_active"] = False
                df_deprem = pd.DataFrame(bundle.get("pier_forces", []))
                df_pier_section = pd.DataFrame(bundle.get("pier_section", []))
                df_bodrum = pd.DataFrame(bundle.get("basement_forces", []))

                if df_deprem.empty or df_pier_section.empty:
                    st.error("ETABS'ten perde verileri alınamadı. Modelinizin analiz edildiğinden emin olun.")
                else:
                    df_deprem = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'P': 'Deprem Yük'})
                    merged_df = df_deprem

                    if is_basement and 'basement_stories' in locals() and basement_stories and not df_bodrum.empty:
                        df_bodrum_sub = df_bodrum[df_bodrum["Story"].isin(basement_stories)].copy()
                        df_bodrum_sub = df_bodrum_sub.rename(columns={'OutputCase': 'Bodrum Deprem Kombinasyon', 'P': 'Bodrum Deprem Yük'})
                        merged_df = pd.merge(merged_df, df_bodrum_sub, on=['Story', 'Pier'], how='left')
                        merged_df['Deprem Kombinasyonu'] = merged_df['Bodrum Deprem Kombinasyon'].combine_first(merged_df['Deprem Kombinasyonu'])
                        merged_df['Deprem Yük'] = merged_df['Bodrum Deprem Yük'].combine_first(merged_df['Deprem Yük'])
                        merged_df = merged_df.drop(columns=['Bodrum Deprem Kombinasyon', 'Bodrum Deprem Yük'], errors='ignore')

                    merged_df = pd.merge(merged_df, df_pier_section[['Story', 'Pier', 'WidthBot', 'ThickBot']], on=['Story', 'Pier'], how='left')
                    merged_df['Beton Sınıfı'] = selected_concrete
                    merged_df['fck'] = concrete_value
                    merged_df['WidthBot'] = pd.to_numeric(merged_df['WidthBot'], errors='coerce')
                    merged_df['ThickBot'] = pd.to_numeric(merged_df['ThickBot'], errors='coerce')
                    merged_df['Deprem Yük'] = pd.to_numeric(merged_df['Deprem Yük'], errors='coerce')

                    merged_df['Ach'] = merged_df['WidthBot'] * merged_df['ThickBot']
                    merged_df['TBDY_Hesap'] = 0.35 * merged_df['fck'] * merged_df['Ach']
                    merged_df['%Ndm/MaxNdm'] = (merged_df['Deprem Yük'].abs() / merged_df['TBDY_Hesap'].replace(0, 1) * 100).round(1).astype(str) + '%'
                    merged_df['TBDY_Durum'] = np.where(merged_df['Deprem Yük'].abs() < merged_df['TBDY_Hesap'], '✅', '❌')

                    st.session_state["perde_final_table"] = merged_df
                    st.rerun()

        if "perde_final_table" in st.session_state:
            disp_df = st.session_state["perde_final_table"]
            grid_response = AgGrid(
                disp_df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key="aggrid_perde_main"
            )

            st.divider()
            col_p1, col_p2 = st.columns(2)
            with col_p1:
                rec_name = st.text_input("Kayıt İsmi:", value="Perde Kapasite Kontrolü")
                if st.button("Sonucu Kaydet"):
                    sonuc_dict = {"final_table": disp_df.to_dict(orient="records")}
                    save_hesaplama(rec_name, json.dumps(sonuc_dict, ensure_ascii=False), st.session_state.get("username", "anon"), "perde_kapasite")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col_p2:
                st.download_button(
                    label="Excel Olarak İndir",
                    data=to_excel(disp_df),
                    file_name="perde_kapasite.xlsx",
                    mime="application/vnd.ms-excel"
                )

with tabs[1]:
    st.markdown(r"""
    ## TBDY 2018 Perde Eksenel Gerilme ve Kapasite Kontrolü

    ### Madde 7.6.1.3
    Düşey yükler ve deprem yüklerinin ortak etkisi altında perdelerde eksenel basınç gerilmesi:
    $$ N_{dm} \leq 0.35 \cdot f_{ck} \cdot A_{ch} $$
    """)