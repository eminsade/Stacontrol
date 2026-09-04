import io
import streamlit as st
import json
import pandas as pd
import etabs_service
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplamalar, get_hesaplama_by_id
from utils import top_right_login, to_excel
from session_config import init_session_state
from constants import CONCRETE_OPTIONS
from bridge_client import render_bridge_status, render_bridge_fetcher

# Streamlit page config
st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar

init_session_state()
setup_sidebar()
top_right_login()

st.title("Kiriş Kesme")

# Canlı ETABS Durumu
render_bridge_status(key="kiris_bridge_status")

# Beton sabitleri
concrete_mapping = CONCRETE_OPTIONS

config_mapping = {
    "paspayi_cm": 2.5
}

def get_grid_options(paspayi_cm):
    return {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Kiriş", "field": "Beam", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Kesit", "field": "SectProp", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "b (cm)", "field": "Width", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "h (cm)", "field": "Depth", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
             "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_mapping.keys())}},
            {"headerName": "Kombinasyon", "field": "OutputCase", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Ve (kN)", "field": "V2", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Number(params.value).toFixed(2) : ''; }"},
            {"headerName": "fctd", "field": "fctd", "editable": True, "filter": "agSetColumnFilter",
             "valueGetter": "data.fctd", "valueFormatter": "function(params){ return params.value != null ? Number(params.value).toFixed(2) : ''; }"},
            {"headerName": "d (cm)", "field": "d", "editable": True, "filter": "agSetColumnFilter",
             "valueGetter": f"data.Depth - {paspayi_cm}"},
            {"headerName": "Vcr (kN)", "field": "Vcr", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "Vmax (kN)", "field": "Vmax", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"0.85 * 0.22 * (data.fcd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "Vmax Kontrolü", "field": "Vmax_Kontrol", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"data.V2 < (0.85 * 0.22 * (data.fcd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10) ? '✅' : '❌'"},
            {"headerName": "KOL", "field": "KOL", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "ÇAP (mm)", "field": "ÇAP", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "ARALIK (cm)", "field": "ARALIK", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Asw (cm²)", "field": "Asw", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "Vw (kN)", "field": "Vw", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "Vr (kN)", "field": "Vr", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"(data.V2 <= (0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10)) ? (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10) + (0.8 * 0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10) : (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10)",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "Ve < Vr", "field": "Ve_Vr_Kontrol", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"data.V2 <= ((data.V2 <= (0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10)) ? (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10) + (0.8 * 0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10) : (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10)) ? '✅' : '❌'"},
            {"headerName": "% Ve/Vr", "field": "Ve_Vr_Oran", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"((data.V2 / ((data.V2 <= (0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10)) ? (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10) + (0.8 * 0.65 * (data.fctd || 0) * (data.Width || 0) * (data.Depth - {paspayi_cm}) / 10) : (((data.KOL * (Math.PI * Math.pow((data['ÇAP'] || 0)/10, 2) / 4)) / (data.ARALIK || 1)) * (data.Depth - {paspayi_cm}) * (420 / 1.15) / 10))) * 100).toFixed(1) + '%'"}
        ],
        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
        "onCellValueChanged": "function(event) { event.api.refreshCells(); }",
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "enableRangeSelection": True,
        "enableFillHandle": True
    }

tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:
    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    if saved_id:
        username = st.session_state.get("username", "")
        record = get_hesaplama_by_id(saved_id, username)
        if record is not None:
            st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
            sonuc_dict = json.loads(record["sonuc"])
            updated_df = pd.DataFrame(sonuc_dict["final_table"])

            grid_response = AgGrid(
                updated_df,
                gridOptions=get_grid_options(config_mapping["paspayi_cm"]),
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
        combo_names = st.session_state.get("etabs_combinations", []) or etabs_service.get_load_combinations()
        if not combo_names:
            st.warning("⚠️ ETABS'e bağlanılıyor veya kombinasyon listesi yükleniyor... Lütfen STACONT Bridge'in açık olduğundan emin olun.")
            st.stop()

        st.subheader("Kombinasyon ve Parametre Seçimleri")
        col1, col2 = st.columns(2)
        with col1:
            main_combo = st.selectbox("Kombinasyon", combo_names, key="main_combo")
            selected_concrete = st.selectbox("Beton Sınıfı", list(concrete_mapping.keys()), key="concrete_class")
            concrete_value = concrete_mapping[selected_concrete]
        with col2:
            paspayi_cm = st.number_input("Paspayı (cm):", value=2.5, min_value=1.0, max_value=10.0, step=0.5)
            config_mapping["paspayi_cm"] = paspayi_cm

        if st.button("Final Tabloyu Getir", key="btn_run_kiris"):
            st.session_state["fetching_kiris_active"] = True

        if st.session_state.get("fetching_kiris_active"):
            bundle = None
            SapModel = etabs_service.get_active_sap_model()
            if SapModel:
                bundle = etabs_service.get_beam_bundle(main_combo)
            else:
                bundle = render_bridge_fetcher(
                    endpoint="/api/beam_bundle",
                    params={"combo": main_combo},
                    bundle_name="beam_bundle",
                    key="kiris_bridge_fetcher_widget"
                )

            if bundle and isinstance(bundle, dict) and bundle.get("success"):
                st.session_state["fetching_kiris_active"] = False
                df_beams = pd.DataFrame(bundle.get("beam_forces", []))
                df_assign = pd.DataFrame(bundle.get("frame_assignments", []))
                df_defs = pd.DataFrame(bundle.get("section_definitions", []))

                if df_beams.empty or 'V2' not in df_beams.columns:
                    st.error(f"'{main_combo}' kombinasyonu için kiriş kesme kuvvetleri alınamadı. Modelinizin çözülmüş olduğundan emin olun.")
                else:
                    df_beams['V2'] = pd.to_numeric(df_beams['V2'], errors='coerce')
                    max_idx = df_beams.groupby(['Story', 'Beam'], sort=False)['V2'].apply(lambda x: x.abs().idxmax())
                    filtered_df = df_beams.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Beam', 'OutputCase', 'V2']]

                    # Frame section properties
                    if not df_assign.empty:
                        beam_col = next((c for c in ['Beam', 'FrameObjectName', 'Label', 'Frame'] if c in df_assign.columns), None)
                        if beam_col and beam_col != 'Beam':
                            df_assign['Beam'] = df_assign[beam_col]
                        if 'SectProp' not in df_assign.columns and 'AutoSelect' in df_assign.columns:
                            df_assign['SectProp'] = df_assign['AutoSelect']
                        col_props = df_assign[['Story', 'Beam', 'SectProp']].drop_duplicates()
                        filtered_df = pd.merge(filtered_df, col_props, on=['Story', 'Beam'], how='left')

                    # Kesit boyutları (t2 = genişlik, t3 = yükseklik - metre cinsinden, cm'ye çevir)
                    if not df_defs.empty and 'Name' in df_defs.columns:
                        df_defs_clean = df_defs.rename(columns={'Name': 'SectProp'})
                        if 't2' in df_defs_clean.columns and 't3' in df_defs_clean.columns:
                            df_defs_clean['Width'] = pd.to_numeric(df_defs_clean['t2'], errors='coerce') * 100.0
                            df_defs_clean['Depth'] = pd.to_numeric(df_defs_clean['t3'], errors='coerce') * 100.0
                            filtered_df = pd.merge(filtered_df, df_defs_clean[['SectProp', 'Width', 'Depth']].drop_duplicates(), on='SectProp', how='left')

                    if 'Width' not in filtered_df.columns or filtered_df['Width'].isnull().all():
                        filtered_df['Width'] = 25.0
                    else:
                        filtered_df['Width'] = filtered_df['Width'].fillna(25.0)

                    if 'Depth' not in filtered_df.columns or filtered_df['Depth'].isnull().all():
                        filtered_df['Depth'] = 50.0
                    else:
                        filtered_df['Depth'] = filtered_df['Depth'].fillna(50.0)

                    filtered_df['Beton Sınıfı'] = selected_concrete
                    filtered_df['fck'] = concrete_value / 1000.0
                    filtered_df['fcd'] = filtered_df['fck'] / 1.5
                    filtered_df['fctd'] = (0.35 * (filtered_df['fck'] ** 0.5)) / 1.5
                    filtered_df['KOL'] = 2
                    filtered_df['ÇAP'] = 8
                    filtered_df['ARALIK'] = 15

                    st.session_state["kiris_final_table"] = filtered_df
                    st.rerun()

        if "kiris_final_table" in st.session_state:
            disp_df = st.session_state["kiris_final_table"]
            grid_response = AgGrid(
                disp_df,
                gridOptions=get_grid_options(config_mapping["paspayi_cm"]),
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key="aggrid_kiris_main"
            )

            st.divider()
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                rec_name = st.text_input("Kayıt İsmi:", value="Kiriş Kesme Kontrolü")
                if st.button("Sonucu Kaydet"):
                    sonuc_dict = {"final_table": disp_df.to_dict(orient="records")}
                    save_hesaplama(rec_name, json.dumps(sonuc_dict, ensure_ascii=False), st.session_state.get("username", "anon"), "kiris_kesme")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col_k2:
                st.download_button(
                    label="Excel Olarak İndir",
                    data=to_excel(disp_df),
                    file_name="kiris_kesme.xlsx",
                    mime="application/vnd.ms-excel"
                )

with tabs[1]:
    st.markdown(r"""
    ## TBDY 2018 Kiriş Kesme Güvenliği Tahkikleri

    $$ V_r = V_c + V_w $$
    $$ V_{max} = 0.85 \cdot 0.22 \cdot f_{cd} \cdot b_w \cdot d $$
    """)