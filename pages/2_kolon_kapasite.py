import io
import streamlit as st
import pandas as pd
import numpy as np
import json
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplama_by_id
from utils import top_right_login, to_excel
from session_config import init_session_state
from constants import CONCRETE_OPTIONS
from bridge_client import render_bridge_status, fetch_bundle
import etabs_service

# Sayfa konfigürasyonu
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

st.title("Kolon Eksenel Kuvvet Kontrolü")

# Canlı ETABS Durumu
render_bridge_status(key="kolon_bridge_status")

tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:
    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    # AG Grid ayarları
    grid_options = {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter", "maxWidth": 80, "minWidth": 80},
            {"headerName": "Kolon", "field": "Column", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Kesit", "field": "SectProp", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Alan (m²)", "field": "Area", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
             "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(CONCRETE_OPTIONS.keys())}},
            {"headerName": "TS500 Komb", "field": "Düşey Kombinasyon", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Nd (kN)", "field": "Düşey Yük", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "Ac (m²)", "field": "Ac", "editable": True, "filter": "agSetColumnFilter",
             "valueGetter": "data.Area"},
            {"headerName": "TS500 MaxNd", "field": "TS500_Hesap", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "0.9 * (data['fcd'] || 0) * (data['Ac'] || 0)",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "% Nd/MaxNd", "field": "%Nd/MaxNd", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "((Math.abs(data['Düşey Yük'] || 0) / (0.9 * (data['fcd'] || 1) * (data['Ac'] || 1))) * 100).toFixed(1) + '%'"},
            {"headerName": "TS500 Durum", "field": "TS500_Durum", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "(Math.abs(data['Düşey Yük'] || 0) < (0.9 * (data['fcd'] || 0) * (data['Ac'] || 0))) ? '✅' : '❌'"},
            {"headerName": "TBDY Komb", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Ndm (kN)", "field": "Deprem Yük", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "TBDY MaxNdm", "field": "TBDY_Hesap", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "0.4 * (data['fck'] || 0) * (data['Ac'] || 0)",
             "valueFormatter": "function(params){ return params.value != null ? params.value.toFixed(2) : ''; }"},
            {"headerName": "% Ndm/MaxNdm", "field": "%Ndm/MaxNdm", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "((Math.abs(data['Deprem Yük'] || 0) / (0.4 * (data['fck'] || 1) * (data['Ac'] || 1))) * 100).toFixed(1) + '%'"},
            {"headerName": "TBDY Durum", "field": "TBDY_Durum", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": "(Math.abs(data['Deprem Yük'] || 0) < (0.4 * (data['fck'] || 0) * (data['Ac'] || 0))) ? '✅' : '❌'"}
        ],
        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
        "onCellValueChanged": "function(event) { event.api.refreshCells(); }",
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "enableRangeSelection": True,
        "enableFillHandle": True
    }

    # Kaydedilmiş veriyi yükleme
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
        # Kombinasyon listesi
        combo_names = st.session_state.get("etabs_combinations", [])
        if not combo_names:
            combo_names = etabs_service.get_load_combinations()

        if not combo_names:
            st.warning("⚠️ ETABS'e bağlanılıyor veya kombinasyon listesi yükleniyor... Lütfen STACONT Bridge'in açık olduğundan emin olun.")
            st.stop()

        st.subheader("Kombinasyon Seçimleri")
        col1, col2 = st.columns(2)
        with col1:
            main_dusey_combo = st.selectbox("TS500 Düşey Kombinasyon", combo_names, key="main_combo1")
            main_deprem_combo = st.selectbox("TBDY2018 Deprem Kombinasyon", combo_names, key="main_combo2")
            selected_concrete = st.selectbox("Beton Sınıfı", list(CONCRETE_OPTIONS.keys()), key="concrete_class")
            concrete_value = CONCRETE_OPTIONS.get(selected_concrete, 25000)

        with col2:
            is_basement = st.checkbox("YAPI BODRUMLU MU?")
            if is_basement:
                basement_dusey_combo = st.selectbox("Bodrum TS500 Kombinasyon", combo_names, key="basement_combo1")
                basement_deprem_combo = st.selectbox("Bodrum TBDY2018 Kombinasyon", combo_names, key="basement_combo2")
                # Kat seçenekleri
                SapModel = etabs_service.get_active_sap_model()
                story_options = []
                if SapModel:
                    try:
                        ret_stories = SapModel.Story.GetNameList()
                        story_options = list(ret_stories[1]) if ret_stories[0] > 0 else []
                    except Exception:
                        pass
                basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", options=story_options, key="basement_stories")

        # Buton ile veri çekme
        if st.button("Kontrol Et / Tabloyu Getir"):
            with st.spinner("ETABS kolon verileri alınıyor..."):
                # 1. Yerel COM'dan dene
                SapModel = etabs_service.get_active_sap_model()
                if SapModel is not None:
                    def get_table_for_combination(combo):
                        SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
                        SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
                        SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
                        ret = SapModel.DatabaseTables.GetTableForDisplayArray('Element Forces - Columns', [], 'All', 1, [], 0, [])
                        columns, data_list = ret[2], ret[4]
                        if not columns:
                            return None
                        rows = [data_list[i:i + len(columns)] for i in range(0, len(data_list), len(columns))]
                        df = pd.DataFrame(rows, columns=columns).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
                        df['P'] = pd.to_numeric(df['P'], errors='coerce')
                        max_idx = df.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                        return df.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]

                    df_dusey = get_table_for_combination(main_dusey_combo)
                    df_deprem = get_table_for_combination(main_deprem_combo)
                    
                    ret_assign = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Assignments - Section Properties', [], 'All', 1, [], 0, [])
                    cols_a, data_a = ret_assign[2], ret_assign[4]
                    rows_a = [data_a[i:i + len(cols_a)] for i in range(0, len(data_a), len(cols_a))]
                    df_assign = pd.DataFrame(rows_a, columns=cols_a).apply(lambda x: x.str.strip() if x.dtype == "object" else x)

                    ret_defs = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Section Property Definitions - Summary', [], 'All', 1, [], 0, [])
                    cols_d, data_d = ret_defs[2], ret_defs[4]
                    if not cols_d:
                        ret_defs = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Section Property Definitions - Concrete Rectangular', [], 'All', 1, [], 0, [])
                        cols_d, data_d = ret_defs[2], ret_defs[4]
                    rows_d = [data_d[i:i + len(cols_d)] for i in range(0, len(data_d), len(cols_d))]
                    df_defs = pd.DataFrame(rows_d, columns=cols_d).apply(lambda x: x.str.strip() if x.dtype == "object" else x)

                else:
                    # 2. Bridge API'den dene
                    resp = fetch_bundle("/api/column_bundle", params={"combo": main_deprem_combo, "ts500_combo": main_dusey_combo})
                    if resp and resp.get("success"):
                        df_deprem = pd.DataFrame(resp.get("column_forces", []))
                        df_dusey = pd.DataFrame(resp.get("ts500_forces", []))
                        df_assign = pd.DataFrame(resp.get("frame_assignments", []))
                        df_defs = pd.DataFrame(resp.get("section_definitions", []))
                    else:
                        st.error("ETABS'ten kolon verileri alınamadı.")
                        st.stop()

                if df_dusey is None or df_deprem is None or df_dusey.empty or df_deprem.empty:
                    st.error("Kombinasyon verileri okunamadı.")
                    st.stop()

                df_dusey = df_dusey.rename(columns={'OutputCase': 'Düşey Kombinasyon', 'P': 'Düşey Yük'})
                df_deprem = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'P': 'Deprem Yük'})
                merged_df = pd.merge(df_dusey, df_deprem, on=['Story', 'Column'], how='left').sort_index().reset_index(drop=True)

                if is_basement and 'basement_stories' in locals() and basement_stories:
                    # Bodrum güncellemesi
                    pass

                # Kesit birleştirme
                if 'DesignType' in df_assign.columns:
                    df_assign = df_assign[df_assign['DesignType'] == 'Column']
                
                df_assign = df_assign.rename(columns={'FrameObjectName': 'Column', 'AutoSelect': 'SectProp'})
                col_props = df_assign[['Story', 'Column', 'SectProp']].drop_duplicates()
                merged_df = pd.merge(merged_df, col_props, on=['Story', 'Column'], how='left')

                # Kesit alanları
                if 'Name' in df_defs.columns and 'Area' in df_defs.columns:
                    df_defs_clean = df_defs.rename(columns={'Name': 'SectProp'})[['SectProp', 'Area']].drop_duplicates()
                    merged_df = pd.merge(merged_df, df_defs_clean, on='SectProp', how='left')
                else:
                    merged_df['Area'] = 0.25

                merged_df['Beton Sınıfı'] = selected_concrete
                merged_df['fck'] = concrete_value
                merged_df['fcd'] = concrete_value / 1.5
                merged_df['Ac'] = pd.to_numeric(merged_df['Area'], errors='coerce')
                merged_df['Düşey Yük'] = pd.to_numeric(merged_df['Düşey Yük'], errors='coerce')
                merged_df['Deprem Yük'] = pd.to_numeric(merged_df['Deprem Yük'], errors='coerce')

                # Hesaplamalar
                merged_df['TS500_Hesap'] = 0.9 * merged_df['fcd'] * merged_df['Ac']
                merged_df['%Nd/MaxNd'] = (merged_df['Düşey Yük'].abs() / merged_df['TS500_Hesap'].replace(0, 1) * 100).round(1).astype(str) + '%'
                merged_df['TS500_Durum'] = np.where(merged_df['Düşey Yük'].abs() < merged_df['TS500_Hesap'], '✅', '❌')

                merged_df['TBDY_Hesap'] = 0.4 * merged_df['fck'] * merged_df['Ac']
                merged_df['%Ndm/MaxNdm'] = (merged_df['Deprem Yük'].abs() / merged_df['TBDY_Hesap'].replace(0, 1) * 100).round(1).astype(str) + '%'
                merged_df['TBDY_Durum'] = np.where(merged_df['Deprem Yük'].abs() < merged_df['TBDY_Hesap'], '✅', '❌')

                st.session_state["kolon_final_table"] = merged_df

        if "kolon_final_table" in st.session_state:
            disp_df = st.session_state["kolon_final_table"]
            grid_response = AgGrid(
                disp_df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key="aggrid_kolon_main"
            )

            st.divider()
            col_k1, col_k2 = st.columns(2)
            with col_k1:
                rec_name = st.text_input("Kayıt İsmi:", value="Kolon Kapasite Kontrolü")
                if st.button("Sonucu Kaydet"):
                    sonuc_dict = {"final_table": disp_df.to_dict(orient="records")}
                    save_hesaplama(rec_name, json.dumps(sonuc_dict, ensure_ascii=False), st.session_state.get("username", "anon"), "kolon_kapasite")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col_k2:
                st.download_button(
                    label="Excel Olarak İndir",
                    data=to_excel(disp_df),
                    file_name="kolon_kapasite.xlsx",
                    mime="application/vnd.ms-excel"
                )

with tabs[1]:
    st.markdown(r"""
    ## TBDY 2018 & TS 500 Kolon Kapasite Tahkikleri

    ### TS 500 (Düşey Yük Kontrolü)
    $$ N_d \leq 0.9 \cdot f_{cd} \cdot A_c $$

    ### TBDY 2018 (Deprem Yükü Kontrolü - Madde 7.3.1.2)
    $$ N_{dm} \leq 0.40 \cdot f_{ck} \cdot A_c $$
    """)