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
from bridge_client import render_bridge_status

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

        if st.button("Final Tabloyu Getir"):
            with st.spinner("ETABS kiriş verileri alınıyor..."):
                # Beam forces
                df_beams = pd.DataFrame()
                resp = etabs_service._fetch_from_bridge('/api/table', params={'name': 'Element Forces - Beams', 'combo': main_combo})
                if resp and resp.get("success") and resp.get("data"):
                    df_beams = pd.DataFrame(resp.get("data"))
                else:
                    Sap = etabs_service.get_active_sap_model()
                    if Sap:
                        try:
                            Sap.DatabaseTables.SetLoadCasesSelectedForDisplay([])
                            Sap.DatabaseTables.SetLoadCombinationsSelectedForDisplay([main_combo])
                            Sap.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
                            ret = Sap.DatabaseTables.GetTableForDisplayArray('Element Forces - Beams', [], 'All', 1, [], 0, [])
                            cols = [c.strip() for c in ret[2]] if ret[2] else []
                            raw = ret[4] if ret[2] else []
                            df_beams = pd.DataFrame([raw[i:i + len(cols)] for i in range(0, len(raw), len(cols))], columns=cols)
                        except Exception:
                            pass

                if df_beams.empty or 'V2' not in df_beams.columns:
                    st.error("Kiriş kesme kuvvetleri alınamadı.")
                    st.stop()

                df_beams['V2'] = pd.to_numeric(df_beams['V2'], errors='coerce')
                max_idx = df_beams.groupby(['Story', 'Beam'], sort=False)['V2'].apply(lambda x: x.abs().idxmax())
                filtered_df = df_beams.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Beam', 'OutputCase', 'V2']]

                # Frame section properties
                df_assign = pd.DataFrame()
                resp_a = etabs_service._fetch_from_bridge('/api/table', params={'name': 'Frame Assignments - Section Properties'})
                if resp_a and resp_a.get("success") and resp_a.get("data"):
                    df_assign = pd.DataFrame(resp_a.get("data"))
                else:
                    Sap = etabs_service.get_active_sap_model()
                    if Sap:
                        try:
                            ret_a = Sap.DatabaseTables.GetTableForDisplayArray('Frame Assignments - Section Properties', [], 'All', 1, [], 0, [])
                            cols_a = [c.strip() for c in ret_a[2]] if ret_a[2] else []
                            raw_a = ret_a[4] if ret_a[2] else []
                            df_assign = pd.DataFrame([raw_a[i:i + len(cols_a)] for i in range(0, len(raw_a), len(cols_a))], columns=cols_a)
                        except Exception:
                            pass

                if not df_assign.empty:
                    if 'DesignType' in df_assign.columns:
                        df_assign = df_assign[df_assign['DesignType'] == 'Beam']
                    df_assign = df_assign.rename(columns={'FrameObjectName': 'Beam', 'AutoSelect': 'SectProp'})
                    filtered_df = pd.merge(filtered_df, df_assign[['Story', 'Beam', 'SectProp']].drop_duplicates(), on=['Story', 'Beam'], how='left')

                filtered_df['Beton Sınıfı'] = selected_concrete
                filtered_df['fck'] = concrete_value / 1000.0
                filtered_df['fcd'] = filtered_df['fck'] / 1.5
                filtered_df['fctd'] = (0.35 * (filtered_df['fck'] ** 0.5)) / 1.5
                filtered_df['Width'] = 25.0
                filtered_df['Depth'] = 50.0
                filtered_df['KOL'] = 2
                filtered_df['ÇAP'] = 8
                filtered_df['ARALIK'] = 15

                st.session_state["kiris_final_table"] = filtered_df

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