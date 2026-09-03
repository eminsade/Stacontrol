import io
import streamlit as st

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
from etabs_bridge.streamlit_ui import connect_etabs
import pandas as pd
import numpy as np
import json
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplamalar, get_hesaplama_by_id
from utils import top_right_login
from session_config import init_session_state

# Sayfa konfigürasyonu

init_session_state()

setup_sidebar()

top_right_login()

st.title("Perde Kesme")


tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:


    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    # ETABS Bağlantı ve Yardımcı Fonksiyonlar
    def connect_to_etabs():
        # Kullanıcının bilgisayarındaki ajan üzerinden bağlanılır; bağlantı
        # yoksa connect_etabs kurulum panelini gösterip sayfayı durdurur.
        return connect_etabs(units=6)  # kN-m units

    def get_load_combinations(SapModel):
        try:
            ret_combos = SapModel.RespCombo.GetNameList()
            return ret_combos[1] if ret_combos[0] > 0 else []
        except Exception as e:
            st.error(f"Yük kombinasyonlarını alırken hata: {e}")
            return []

    def get_table_for_combination(SapModel, combo):
        try:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Forces', [], 'All', 1, [], 0, [])
            if not ret[2]:
                st.error(f"Tablo verisi alınamadı: {combo}")
                return None
            df = pd.DataFrame([ret[4][i:i + len(ret[2])] for i in range(0, len(ret[4]), len(ret[2]))],
                            columns=[col.strip() for col in ret[2]])
            df['V2'] = pd.to_numeric(df['V2'], errors='coerce')
            max_idx = df.groupby(['Story', 'Pier'])['V2'].apply(lambda x: x.abs().idxmax())
            return df.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Pier', 'OutputCase', 'V2']]
        except Exception as e:
            st.error(f"Tablo çekilirken hata: {e}")
            return None

    def get_pier_section_properties(SapModel):
        try:
            ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Section Properties', [], 'All', 1, [], 0, [])
            if not ret[2]:
                st.error("Pier Section Properties tablosu boş")
                return None
            df = pd.DataFrame([ret[4][i:i + len(ret[2])] for i in range(0, len(ret[4]), len(ret[2]))],
                            columns=[col.strip() for col in ret[2]])
            return df
        except Exception as e:
            st.error(f"Pier Section Properties hatası: {e}")
            return None

    def to_excel(df):
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine="xlsxwriter")
        df.to_excel(writer, sheet_name="Sheet1", index=False)
        workbook = writer.book
        worksheet = writer.sheets["Sheet1"]
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col))
            worksheet.set_column(idx, idx, max_length + 2)
        writer.close()
        return output.getvalue()

    # Kayıtlı Sonuç Gösterme
    if saved_id:
        username = st.session_state["username"]
        record = get_hesaplama_by_id(saved_id, username)
        if record is not None:
            st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
            sonuc_dict = json.loads(record["sonuc"])
            updated_df = pd.DataFrame(sonuc_dict["final_table"])

            # Kaydedilen parametreleri geri yükle
            selected_concrete = sonuc_dict.get("concrete_class", "C25")
            selected_steel = sonuc_dict.get("steel_class", "S420")
            main_deprem_combo = sonuc_dict.get("main_deprem_combo", "")
            selected_bosluk = sonuc_dict.get("bosluk_option", "Boşluksuz Perde: 0.85")
            bv_value = sonuc_dict.get("bv_value", 1)
            Mp_Md = sonuc_dict.get("Mp_Md", 0.0)
            is_sekil_712c = sonuc_dict.get("is_sekil_712c", False)
            is_basement = "basement_deprem_combo" in sonuc_dict
            basement_deprem_combo = sonuc_dict.get("basement_deprem_combo", "")
            basement_stories = sonuc_dict.get("basement_stories", [])

            # Sabit seçenekler
            concrete_options = {"C16": 16000, "C18": 18000, "C20": 20000, "C25": 25000, "C30": 30000,
                                "C35": 35000, "C40": 40000, "C45": 45000, "C50": 50000, "C55": 55000, "C60": 60000}
            steel_options = {"S420": 420000, "B420C": 420000, "B500C": 500000}
            bosluk_options = {"Boşluksuz Perde: 0.85": 0.85, "Boşluklu Perde: 0.65": 0.65}

            concrete_value = concrete_options[selected_concrete]
            steel_value = steel_options[selected_steel]
            bosluk_value = bosluk_options[selected_bosluk]

            # Dinamik grid options (ana arayüzle aynı mantık)
            grid_options = {
                "columnDefs": [
                    {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter"},
                    {"headerName": "Perde", "field": "Pier", "editable": True, "filter": "agSetColumnFilter"},
                    {"headerName": "Yükseklik", "field": "HW", "editable": False, "filter": "agSetColumnFilter", 
                    "valueFormatter": "value.toFixed(1)"},
                    {"headerName": "Uzunluk", "field": "WidthBot", "editable": True, "filter": "agSetColumnFilter", 
                    "valueFormatter": "value.toFixed(1)"},
                    {"headerName": "Kalınlık", "field": "ThickBot", "editable": True, "filter": "agSetColumnFilter", 
                    "valueFormatter": "value.toFixed(1)"},
                    {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
                    "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_options.keys())}},
                    {"headerName": "Kombinasyon", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
                    {"headerName": "VE1", "field": "VE1", "editable": False, "filter": "agSetColumnFilter",
                    "valueFormatter": "value.toFixed(1)",
                    "valueGetter": f"""
                        var hw_lw = parseFloat(data.HW) / parseFloat(data.WidthBot || 1);
                        var deprem_yuk = Math.abs(parseFloat(data['Deprem Yük']) || 0);
                        return hw_lw < 2 ? deprem_yuk * Math.min(3 / (1 + hw_lw), 2) : deprem_yuk * {bv_value} * {Mp_Md};
                    """},
                    {"headerName": "VE2", "field": "VE2", "editable": False, "filter": "agSetColumnFilter",
                    "valueFormatter": "value.toFixed(1)",
                    "valueGetter": "Math.abs(parseFloat(data['Deprem Yük']) || 0)"},
                    {"headerName": "VE", "field": "VE", "editable": False, "filter": "agSetColumnFilter",
                    "valueFormatter": "value.toFixed(1)",
                    "valueGetter": "Math.min(data.VE1, data.VE2)"},
                    {"headerName": "VR", "field": "VR", "editable": False, "filter": "agSetColumnFilter",
                    "valueFormatter": "value.toFixed(1)",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var sqrt_cv = Math.sqrt(cv / 1000);
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        return 1000 * {bosluk_value} * width * thick * sqrt_cv;
                    """},
                    {"headerName": "%VE/VR", "field": "%VE/VR", "editable": False, "filter": "agSetColumnFilter",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var sqrt_cv = Math.sqrt(cv / 1000);
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        var vr = 1000 * {bosluk_value} * width * thick * sqrt_cv;
                        return (data.VE != null && vr != 0) ? ((data.VE / vr) * 100).toFixed(1) + '%' : '';
                    """},
                    {"headerName": "VE < VR", "field": "Durum", "editable": False, "filter": "agSetColumnFilter",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var sqrt_cv = Math.sqrt(cv / 1000);
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        var vr = 1000 * {bosluk_value} * width * thick * sqrt_cv;
                        return (data.VE != null && vr != 0) ? (data.VE < vr ? '✅' : '❌') : '';
                    """},
                    {"headerName": "KOL", "field": "KOL", "editable": True, "filter": "agSetColumnFilter",
                    "enableFillHandle": True, "fillHandleDirection": "y"},
                    {"headerName": "ÇAP", "field": "ÇAP", "editable": True, "filter": "agSetColumnFilter",
                    "enableFillHandle": True, "fillHandleDirection": "y"},
                    {"headerName": "ARALIK", "field": "ARALIK", "editable": True, "filter": "agSetColumnFilter",
                    "enableFillHandle": True, "fillHandleDirection": "y"},
                    {"headerName": "∑VR", "field": "Vrt", "editable": False, "filter": "agSetColumnFilter",
                    "valueFormatter": "value.toFixed(1)",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var fck = cv / 1000;
                        var fctk = 0.35 * Math.sqrt(fck);
                        var fctd = fctk / 1.5;
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        var vrc = 0.65 * fctd * 1000 * width * thick;
                        var ach = width * thick;
                        var fyk = {steel_value} / 1000;
                        var fywd = fyk / 1.15;
                        var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                        var ach_1m = 1 * thick;
                        var rho_sh = as / (ach_1m * 1e6);
                        var vrw = ach * rho_sh * fywd * 1000;
                        return vrc + vrw;
                    """},
                    {"headerName": "%VE/∑VR", "field": "%VE/Vrt", "editable": False, "filter": "agSetColumnFilter",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var fck = cv / 1000;
                        var fctk = 0.35 * Math.sqrt(fck);
                        var fctd = fctk / 1.5;
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        var vrc = 0.65 * fctd * 1000 * width * thick;
                        var ach = width * thick;
                        var fyk = {steel_value} / 1000;
                        var fywd = fyk / 1.15;
                        var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                        var ach_1m = 1 * thick;
                        var rho_sh = as / (ach_1m * 1e6);
                        var vrw = ach * rho_sh * fywd * 1000;
                        var vrt = vrw + vrc;
                        return (data.VE != null && vrt != 0) ? ((data.VE / vrt) * 100).toFixed(1) + '%' : '';
                    """},
                    {"headerName": "VE < ∑VR", "field": "Durum1", "editable": False, "filter": "agSetColumnFilter",
                    "valueGetter": f"""
                        var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                        var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                        var fck = cv / 1000;
                        var fctk = 0.35 * Math.sqrt(fck);
                        var fctd = fctk / 1.5;
                        var width = parseFloat(data.WidthBot || 0);
                        var thick = parseFloat(data.ThickBot || 0);
                        var vrc = 0.65 * fctd * 1000 * width * thick;
                        var ach = width * thick;
                        var fyk = {steel_value} / 1000;
                        var fywd = fyk / 1.15;
                        var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                        var ach_1m = 1 * thick;
                        var rho_sh = as / (ach_1m * 1e6);
                        var vrw = ach * rho_sh * fywd * 1000;
                        var vrt = vrw + vrc;
                        return (data.VE != null && vrt != 0) ? (data.VE < vrt ? '✅' : '❌') : '';
                    """}
                ],
                "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
                "onCellValueChanged": "function(event) { event.api.refreshCells(); }",
                "sideBar": {"toolPanels": ["columns", "filters"]},
                "enableRangeSelection": True,
                "enableFillHandle": True
            }

            # AgGrid ile tabloyu göster
            grid_response = AgGrid(
                updated_df,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key=f"aggrid_saved_{saved_id}"
            )

            # Güncellenmiş veriyi al ve yeniden hesapla
            updated_df = pd.DataFrame(grid_response["data"])
            numeric_cols = ['WidthBot', 'ThickBot', 'Deprem Yük', 'KOL', 'ÇAP', 'ARALIK']
            updated_df[numeric_cols] = updated_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            updated_df['Deprem Yük'] = updated_df['Deprem Yük'].abs()

            updated_df['HW/LW'] = updated_df['HW'] / updated_df['WidthBot']
            updated_df['VE1'] = updated_df.apply(
                lambda row: abs(row['Deprem Yük'] * min(3 / (1 + row['HW/LW']), 2)) if row['HW/LW'] < 2 
                else abs(row['Deprem Yük'] * bv_value * Mp_Md), 
                axis=1
            )
            updated_df['VE2'] = updated_df['Deprem Yük'].abs()

            if is_sekil_712c:
                if 'HW*' not in updated_df.columns:
                    updated_df['HW*'] = updated_df['HW']  # Approximation
                updated_df['HW/3'] = updated_df['HW'] / 3
                mask = updated_df['HW*'] > updated_df['HW/3']
                pier_max = updated_df.groupby('Pier')[['VE1', 'VE2']].max()
                updated_df = pd.merge(updated_df, pier_max, on='Pier', suffixes=('', '_max'))
                updated_df.loc[mask & (updated_df['VE1_max'] / 2 > updated_df['VE1']), 'VE1'] = updated_df['VE1_max'] / 2
                updated_df.loc[mask & (updated_df['VE2_max'] / 2 > updated_df['VE2']), 'VE2'] = updated_df['VE2_max'] / 2
                updated_df = updated_df.drop(columns=['HW/3', 'VE1_max', 'VE2_max'])

            updated_df['VE'] = np.minimum(updated_df['VE1'], updated_df['VE2'])
            updated_df['VR'] = 1000 * bosluk_value * updated_df['WidthBot'] * updated_df['ThickBot'] * np.sqrt(
                updated_df['Beton Sınıfı'].map(concrete_options).fillna(concrete_value) / 1000
            )
            updated_df["%VE/VR"] = ((updated_df["VE"] / updated_df["VR"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum"] = updated_df["VE"] < updated_df["VR"]
            updated_df["Durum"] = updated_df["Durum"].map({True: "✅", False: "❌"})

            fck = updated_df['Beton Sınıfı'].map(concrete_options).fillna(concrete_value) / 1000
            fctk = 0.35 * np.sqrt(fck)
            fctd = fctk / 1.5
            updated_df['Vrc'] = 0.65 * fctd * 1000 * updated_df['WidthBot'] * updated_df['ThickBot']

            Ach = updated_df['WidthBot'] * updated_df['ThickBot']
            fyk = steel_value / 1000
            fywd = fyk / 1.15
            As = updated_df['KOL'] * (np.pi * (updated_df['ÇAP'] / 2)**2) * (1000 / (updated_df['ARALIK'] * 10))
            Ach_1m = 1 * updated_df['ThickBot']
            rho_sh = As / (Ach_1m * 1e6)
            updated_df['Vrw'] = Ach * rho_sh * fywd * 1000
            updated_df['Vrt'] = updated_df['Vrw'] + updated_df['Vrc']
            updated_df["%VE/Vrt"] = ((updated_df["VE"] / updated_df["Vrt"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum1"] = updated_df["VE"] < updated_df["Vrt"]
            updated_df["Durum1"] = updated_df["Durum1"].map({True: "✅", False: "❌"})

            # Excel indirme butonu
            st.download_button(
                label="Excel Olarak İndir",
                data=to_excel(updated_df),
                file_name=f"{record['hesap_tipi']}.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.error("Kayıt bulunamadı veya erişim yetkiniz yok.")
            st.stop()
    else:
        # Ana Hesaplama Arayüzü
        st.subheader("Deprem Kombinasyon Seçimi")
        with st.spinner("ETABS'e bağlanıyor..."):
            SapModel = connect_to_etabs()
        if SapModel is None:
            st.stop()

        combo_names = get_load_combinations(SapModel)
        if not combo_names:
            st.error("ETABS'te yük kombinasyonları bulunamadı.")
            st.stop()

        df_pier_section = get_pier_section_properties(SapModel)
        if df_pier_section is None:
            st.stop()

        col1, col2 = st.columns(2)
        with col1:
            main_deprem_combo = st.selectbox("Kombinasyon", combo_names, key="main_deprem_combo")
            is_basement = st.checkbox("YAPI BODRUMLU MU?")
            if is_basement:
                basement_deprem_combo = st.selectbox("Bodrum Kombinasyon", combo_names, key="basement_deprem_combo")
                df_temp_basement = get_table_for_combination(SapModel, basement_deprem_combo)
                story_options = df_temp_basement['Story'].drop_duplicates().tolist() if df_temp_basement is not None else []
                basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", story_options, key="basement_stories")
            concrete_options = {"C16": 16000, "C18": 18000, "C20": 20000, "C25": 25000, "C30": 30000,
                                "C35": 35000, "C40": 40000, "C45": 45000, "C50": 50000, "C55": 55000, "C60": 60000}
            selected_concrete = st.selectbox("Beton Sınıfı", list(concrete_options.keys()), key="concrete_class")
            concrete_value = concrete_options[selected_concrete]
            steel_options = {"S420": 420000, "B420C": 420000, "B500C": 500000}
            selected_steel = st.selectbox("Çelik Sınıfı", list(steel_options.keys()), key="steel_class")
            steel_value = steel_options[selected_steel]
        with col2:
            bosluk_options = {"Boşluksuz Perde: 0.85": 0.85, "Boşluklu Perde: 0.65": 0.65}
            selected_bosluk = st.selectbox("Boşluklu/Boşluksuz", list(bosluk_options.keys()), key="bosluk_class")
            bosluk_value = bosluk_options[selected_bosluk]
            bv_options = {"Deprem Yükünün Tamamı Perdelerde: 1": 1, "Deprem Yükü Paylaşılıyor: 1.5": 1.5}
            selected_bv = st.selectbox("Bv Değeri", list(bv_options.keys()), key="bv_class")
            bv_value = bv_options[selected_bv]
            Mp_Md = st.number_input("Mp/Md Değeri", value=0.0, format="%.1f")
            is_sekil_712c = st.checkbox("Kesme Kuvvetini Şekil 7.12c'ye Göre Artır")

        # Grid Options for Main Interface
        grid_options = {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Perde", "field": "Pier", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Yükseklik", "field": "HW", "editable": False, "filter": "agSetColumnFilter", 
            "valueFormatter": "value.toFixed(1)"},
            {"headerName": "Uzunluk", "field": "WidthBot", "editable": True, "filter": "agSetColumnFilter", 
            "valueFormatter": "value.toFixed(1)"},
            {"headerName": "Kalınlık", "field": "ThickBot", "editable": True, "filter": "agSetColumnFilter", 
            "valueFormatter": "value.toFixed(1)"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
            "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_options.keys())}},
            {"headerName": "Kombinasyon", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "VE1", "field": "VE1", "editable": False, "filter": "agSetColumnFilter",
            "valueFormatter": "value.toFixed(1)",
            "valueGetter": f"""
                var hw_lw = parseFloat(data.HW) / parseFloat(data.WidthBot || 1);
                var deprem_yuk = Math.abs(parseFloat(data['Deprem Yük']) || 0);
                return hw_lw < 2 ? deprem_yuk * Math.min(3 / (1 + hw_lw), 2) : deprem_yuk * {bv_value} * {Mp_Md};
            """},
            {"headerName": "VE2", "field": "VE2", "editable": False, "filter": "agSetColumnFilter",
            "valueFormatter": "value.toFixed(1)",
            "valueGetter": "Math.abs(parseFloat(data['Deprem Yük']) || 0)"},
            {"headerName": "VE", "field": "VE", "editable": False, "filter": "agSetColumnFilter",
            "valueFormatter": "value.toFixed(1)",
            "valueGetter": "Math.min(data.VE1, data.VE2)"},
            {"headerName": "VR", "field": "VR", "editable": False, "filter": "agSetColumnFilter",
            "valueFormatter": "value.toFixed(1)",
            "valueGetter": f"""
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var sqrt_cv = Math.sqrt(cv / 1000);
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                return 1000 * {bosluk_value} * width * thick * sqrt_cv;
            """},
            {"headerName": "%VE/VR", "field": "%VE/VR", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": f"""
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var sqrt_cv = Math.sqrt(cv / 1000);
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                var vr = 1000 * {bosluk_value} * width * thick * sqrt_cv;
                return (data.VE != null && vr != 0) ? ((data.VE / vr) * 100).toFixed(1) + '%' : '';
            """},
            {"headerName": "VE < VR", "field": "Durum", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": f"""
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var sqrt_cv = Math.sqrt(cv / 1000);
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                var vr = 1000 * {bosluk_value} * width * thick * sqrt_cv;
                return (data.VE != null && vr != 0) ? (data.VE < vr ? '✅' : '❌') : '';
            """},
            {"headerName": "KOL", "field": "KOL", "editable": True, "filter": "agSetColumnFilter",
            "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "ÇAP", "field": "ÇAP", "editable": True, "filter": "agSetColumnFilter",
            "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "ARALIK", "field": "ARALIK", "editable": True, "filter": "agSetColumnFilter",
            "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "∑VR", "field": "Vrt", "editable": False, "filter": "agSetColumnFilter",
            "valueFormatter": "value.toFixed(1)",
            "valueGetter": f"""
                // Vrc hesaplanması
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var fck = cv / 1000;
                var fctk = 0.35 * Math.sqrt(fck);
                var fctd = fctk / 1.5;
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                var vrc = 0.65 * fctd * 1000 * width * thick;

                // Vrw hesaplanması
                var ach = width * thick;
                var fyk = {steel_value} / 1000;
                var fywd = fyk / 1.15;
                var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                var ach_1m = 1 * thick;
                var rho_sh = as / (ach_1m * 1e6);
                var vrw = ach * rho_sh * fywd * 1000;

                // Vrt = Vrc + Vrw
                return vrc + vrw;
            """},
            {"headerName": "%VE/∑VR", "field": "%VE/Vrt", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": f"""
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var fck = cv / 1000;
                var fctk = 0.35 * Math.sqrt(fck);
                var fctd = fctk / 1.5;
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                var vrc = 0.65 * fctd * 1000 * width * thick;
                var ach = width * thick;
                var fyk = {steel_value} / 1000;
                var fywd = fyk / 1.15;
                var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                var ach_1m = 1 * thick;
                var rho_sh = as / (ach_1m * 1e6);
                var vrw = ach * rho_sh * fywd * 1000;
                var vrt = vrw + vrc;
                return (data.VE != null && vrt != 0) ? ((data.VE / vrt) * 100).toFixed(1) + '%' : '';
            """},
            {"headerName": "VE < ∑VR", "field": "Durum1", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": f"""
                var mapping = {{ {','.join([f"'{k}':{v}" for k, v in concrete_options.items()])} }};
                var cv = mapping[data['Beton Sınıfı']] || {concrete_value};
                var fck = cv / 1000;
                var fctk = 0.35 * Math.sqrt(fck);
                var fctd = fctk / 1.5;
                var width = parseFloat(data.WidthBot || 0);
                var thick = parseFloat(data.ThickBot || 0);
                var vrc = 0.65 * fctd * 1000 * width * thick;
                var ach = width * thick;
                var fyk = {steel_value} / 1000;
                var fywd = fyk / 1.15;
                var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                var ach_1m = 1 * thick;
                var rho_sh = as / (ach_1m * 1e6);
                var vrw = ach * rho_sh * fywd * 1000;
                var vrt = vrw + vrc;
                return (data.VE != null && vrt != 0) ? (data.VE < vrt ? '✅' : '❌') : '';
            """}
        ],
        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
        "onCellValueChanged": "function(event) { event.api.refreshCells(); }",
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "enableRangeSelection": True,
        "enableFillHandle": True
    }

        if st.button("Final Tabloyu Getir"):
            with st.spinner("Tablo oluşturuluyor..."):
                SapModel = connect_to_etabs()
                if SapModel is None:
                    st.stop()
                df_deprem = get_table_for_combination(SapModel, main_deprem_combo)
                if df_deprem is None:
                    st.stop()
                main_table = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'V2': 'Deprem Yük'})
                if is_basement and 'basement_stories' in locals() and basement_stories:
                    df_bodrum = get_table_for_combination(SapModel, basement_deprem_combo)
                    if df_bodrum is not None:
                        df_bodrum = df_bodrum[df_bodrum["Story"].isin(basement_stories)]
                        df_bodrum = df_bodrum.rename(columns={'OutputCase': 'Bodrum Deprem Kombinasyon', 'V2': 'Bodrum Deprem Yük'})
                        main_table = pd.merge(main_table, df_bodrum, on=['Story', 'Pier'], how='left', suffixes=('', '_bodrum'))
                        main_table["Deprem Kombinasyonu"] = main_table["Bodrum Deprem Kombinasyon"].combine_first(main_table["Deprem Kombinasyonu"])
                        main_table["Deprem Yük"] = main_table["Bodrum Deprem Yük"].combine_first(main_table["Deprem Yük"])
                        main_table = main_table.drop(columns=['Bodrum Deprem Kombinasyon', 'Bodrum Deprem Yük'])

                main_table = pd.merge(main_table, 
                                    df_pier_section[['Story', 'Pier', 'WidthBot', 'ThickBot', 'CGBotZ', 'CGTopZ']], 
                                    on=['Story', 'Pier'], 
                                    how='left')

                # Height calculations
                df_pier_section[['CGTopZ', 'CGBotZ']] = df_pier_section[['CGTopZ', 'CGBotZ']].apply(pd.to_numeric, errors='coerce')
                pier_height_df = df_pier_section.groupby('Pier').agg({'CGTopZ': 'max', 'CGBotZ': 'min'})
                pier_height_df['HW'] = pier_height_df['CGTopZ'] - pier_height_df['CGBotZ']
                min_cgbotz_df = df_pier_section.groupby('Pier')['CGBotZ'].min().rename('MinCGBotZ')

                main_table["Beton Sınıfı"] = selected_concrete
                main_table = pd.merge(main_table, min_cgbotz_df, on='Pier', how='left')
                main_table['HW*'] = pd.to_numeric(main_table['CGTopZ'], errors='coerce') - main_table['MinCGBotZ']
                main_table = pd.merge(main_table, pier_height_df[['HW']], on='Pier', how='left')

                # Initial calculations
                main_table[['WidthBot', 'ThickBot']] = main_table[['WidthBot', 'ThickBot']].apply(pd.to_numeric, errors='coerce')
                main_table['HW/LW'] = main_table['HW'] / main_table['WidthBot']
                main_table['Deprem Yük'] = main_table['Deprem Yük'].abs()
                
                main_table['VE1'] = main_table.apply(
                    lambda row: abs(row['Deprem Yük'] * min(3 / (1 + row['HW/LW']), 2)) if row['HW/LW'] < 2 
                    else abs(row['Deprem Yük'] * bv_value * Mp_Md), 
                    axis=1
                )
                main_table['VE2'] = main_table['Deprem Yük'].abs()

                if is_sekil_712c:
                    main_table['HW/3'] = main_table['HW'] / 3
                    mask = main_table['HW*'] > main_table['HW/3']
                    pier_max = main_table.groupby('Pier')[['VE1', 'VE2']].max()
                    main_table = pd.merge(main_table, pier_max, on='Pier', suffixes=('', '_max'))
                    main_table.loc[mask & (main_table['VE1_max'] / 2 > main_table['VE1']), 'VE1'] = main_table['VE1_max'] / 2
                    main_table.loc[mask & (main_table['VE2_max'] / 2 > main_table['VE2']), 'VE2'] = main_table['VE2_max'] / 2
                    main_table = main_table.drop(columns=['HW/3', 'VE1_max', 'VE2_max'])

                # Final calculations
                main_table['VE'] = np.minimum(main_table['VE1'], main_table['VE2'])
                main_table['VR'] = 1000 * bosluk_value * main_table['WidthBot'] * main_table['ThickBot'] * np.sqrt(concrete_value/1000)
                main_table["%VE/VR"] = ((main_table["VE"] / main_table["VR"]) * 100).round(1).astype(str) + '%'
                main_table["Durum"] = main_table["VE"] < main_table["VR"]
                main_table["Durum"] = main_table["Durum"].map({True: "✅", False: "❌"})

                fck = concrete_value / 1000
                fctk = 0.35 * np.sqrt(fck)
                fctd = fctk / 1.5
                main_table['Vrc'] = 0.65 * fctd * 1000 * main_table['WidthBot'] * main_table['ThickBot']

                main_table['KOL'] = 2
                main_table['ÇAP'] = 10
                main_table['ARALIK'] = 20

                Ach = main_table['WidthBot'] * main_table['ThickBot']
                fyk = steel_value / 1000
                fywd = fyk / 1.15
                As = main_table['KOL'] * (np.pi * (main_table['ÇAP'] / 2)**2) * (1000 / (main_table['ARALIK'] * 10))
                Ach_1m = 1 * main_table['ThickBot']
                rho_sh = As / (Ach_1m * 1e6)
                main_table['Vrw'] = Ach * rho_sh * fywd * 1000
                main_table['Vrt'] = main_table['Vrw'] + main_table['Vrc']
                main_table["%VE/Vrt"] = ((main_table["VE"] / main_table["Vrt"]) * 100).round(1).astype(str) + '%'
                main_table["Durum1"] = main_table["VE"] < main_table["Vrt"]
                main_table["Durum1"] = main_table["Durum1"].map({True: "✅", False: "❌"})

                display_columns = ["Story", "Pier", "HW", "WidthBot", "ThickBot", "Beton Sınıfı", 
                                "Deprem Kombinasyonu", "Deprem Yük", "VE1", "VE2", "VE", "VR", "Vrc", 
                                "%VE/VR", "Durum", "KOL", "ÇAP", "ARALIK", "Vrw", "Vrt", "%VE/Vrt", "Durum1"]
                final_table = main_table[display_columns]

                # Save to session state
                st.session_state["final_table"] = final_table

        if "final_table" in st.session_state:
            grid_response = AgGrid(
                st.session_state["final_table"],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key=f"aggrid_{selected_concrete}"
            )
            updated_df = pd.DataFrame(grid_response["data"])
            numeric_cols = ['WidthBot', 'ThickBot', 'Deprem Yük', 'KOL', 'ÇAP', 'ARALIK']
            updated_df[numeric_cols] = updated_df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            updated_df['Deprem Yük'] = updated_df['Deprem Yük'].abs()

            updated_df['HW/LW'] = updated_df['HW'] / updated_df['WidthBot']
            updated_df['VE1'] = updated_df.apply(
                lambda row: abs(row['Deprem Yük'] * min(3 / (1 + row['HW/LW']), 2)) if row['HW/LW'] < 2 
                else abs(row['Deprem Yük'] * bv_value * Mp_Md), 
                axis=1
            )
            updated_df['VE2'] = updated_df['Deprem Yük'].abs()

            if is_sekil_712c:
                if 'HW*' not in updated_df.columns:
                    updated_df['HW*'] = updated_df['HW']  # Approximation
                updated_df['HW/3'] = updated_df['HW'] / 3
                mask = updated_df['HW*'] > updated_df['HW/3']
                pier_max = updated_df.groupby('Pier')[['VE1', 'VE2']].max()
                updated_df = pd.merge(updated_df, pier_max, on='Pier', suffixes=('', '_max'))
                updated_df.loc[mask & (updated_df['VE1_max'] / 2 > updated_df['VE1']), 'VE1'] = updated_df['VE1_max'] / 2
                updated_df.loc[mask & (updated_df['VE2_max'] / 2 > updated_df['VE2']), 'VE2'] = updated_df['VE2_max'] / 2
                updated_df = updated_df.drop(columns=['HW/3', 'VE1_max', 'VE2_max'])

            updated_df['VE'] = np.minimum(updated_df['VE1'], updated_df['VE2'])
            updated_df['VR'] = 1000 * bosluk_value * updated_df['WidthBot'] * updated_df['ThickBot'] * np.sqrt(
                updated_df['Beton Sınıfı'].map(concrete_options).fillna(concrete_value) / 1000
            )
            updated_df["%VE/VR"] = ((updated_df["VE"] / updated_df["VR"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum"] = updated_df["VE"] < updated_df["VR"]
            updated_df["Durum"] = updated_df["Durum"].map({True: "✅", False: "❌"})

            fck = updated_df['Beton Sınıfı'].map(concrete_options).fillna(concrete_value) / 1000
            fctk = 0.35 * np.sqrt(fck)
            fctd = fctk / 1.5
            updated_df['Vrc'] = 0.65 * fctd * 1000 * updated_df['WidthBot'] * updated_df['ThickBot']

            Ach = updated_df['WidthBot'] * updated_df['ThickBot']
            fyk = steel_value / 1000
            fywd = fyk / 1.15
            As = updated_df['KOL'] * (np.pi * (updated_df['ÇAP'] / 2)**2) * (1000 / (updated_df['ARALIK'] * 10))
            Ach_1m = 1 * updated_df['ThickBot']
            rho_sh = As / (Ach_1m * 1e6)
            updated_df['Vrw'] = Ach * rho_sh * fywd * 1000
            updated_df['Vrt'] = updated_df['Vrw'] + updated_df['Vrc']
            updated_df["%VE/Vrt"] = ((updated_df["VE"] / updated_df["Vrt"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum1"] = updated_df["VE"] < updated_df["Vrt"]
            updated_df["Durum1"] = updated_df["Durum1"].map({True: "✅", False: "❌"})

            

            st.session_state["final_table"] = updated_df

            st.divider()
            st.subheader("Sonuç Kaydetme")

            col1, col2 = st.columns([1, 1])  # İki sütunu eşit genişlikte ayırdık

            with col1:
                record_name = st.text_input("Kayıt için bir isim giriniz:", value="Perde Kesme", key="record_name_input")
                kaydet_button = st.button("Sonucu Kaydet")
                
                if kaydet_button:
                    hesap_tipi = record_name
                    # Kaydedilecek veriler: final tablo ve uygulamada kullanılan parametreler
                    sonuc_dict = {
                        "final_table": updated_df.to_dict(orient="records"),
                        "concrete_class": selected_concrete,
                        "steel_class": selected_steel,
                        "main_deprem_combo": main_deprem_combo,
                        "bosluk_option": selected_bosluk,
                        "bv_value": bv_value,
                        "Mp_Md": Mp_Md,
                        "is_sekil_712c": is_sekil_712c
                    }
                    if is_basement:
                        sonuc_dict.update({
                            "basement_deprem_combo": basement_deprem_combo,
                            "basement_stories": basement_stories
                        })
                    sonuc_str = json.dumps(sonuc_dict, ensure_ascii=False, indent=2)
                    save_hesaplama(hesap_tipi, sonuc_str, st.session_state["username"], "perde_kesme")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col2:
                st.download_button(
                    label="Tabloyu Excel olarak indir",
                    data=to_excel(updated_df),
                    file_name="perde_kesme_tablosu.xlsx",
                    mime="application/vnd.ms-excel"
                )
with tabs[1]:
    st.markdown(r"""
    ## TBDY 2018

    ### 7.6.6. Tasarım Eğilme Momentleri ve Kesme Kuvvetleri

    ##### 7.6.6.1
    $(H_w / l_{cw} > 2.0)$ koşulunu sağlayan perdelerde tasarım esas eğilme momentleri, 7.6.2.2'ye göre belirlenen kritik perde yüksekliği boyunca sabit bir değer olarak, perde tabanında Bölüm 4'e göre hesaplanan eğilme momentine eşit alınacaktır. Kritik perde yüksekliğinin sona erdiği kesit üstünde ise, Bölüm 4'e göre perdenin tabanında ve tepesinde hesaplanan momentler birleştiren doğruya paralel olan doğrusal moment diyagramı uygulanacaktır (Şekil 7.12). 3.3.1.1'de verilen koşulları sağlayan bodrumlu binalarda sabit

    ##### 7.6.6.2
    Perde momenti, 7.6.2.2'de tanımlanan kritik perde yüksekliği boyunca gözönüne alınacaktır. $(H_w / l_{cw} \leq 2.0)$ olan perdelerin bütün kesitlerinde tasarım eğilme momentleri, Bölüm 4'e göre hesaplanan eğilme momentlere eşit alınacaktır.

    ##### 7.6.6.2
    $(H_w / l_{cw} > 2.0)$ olması durumunda, her bir katta perde kesitinin taşıma gücü momentlerinin, perdenin güçlü doğrultusunda kolonlar için Denk.(7.3) ile verilen koşulu sağlaması zorunludur. Aksi durumda perde boyutları ve/veya donatıları artırılarak deprem hesabı tekrarlanacaktır.

    ##### 7.6.6.3
    $(H_w / l_{cw} > 2.0)$ koşulunu sağlayan perdelerde, gözönüne alınır herhangi bir kesitte enine donatının esas alınacak tasarım kesme kuvveti, $(V_e)$, Denk.(7.16) ile hesaplanacaktır.

    $$ V_e = β_v \\left( \\frac{(M_p)_t}{(M_d)_t} \\right) V_d $$ **(7.16)**
                

    Bu denklemde yer alan kesme kuvveti dinamik büyütme katsayısı $(Β_v = 1.5)$ alınacaktır. Ancak, deprem yükünün tamamının betonarme perdelerle taşındığı binalarda $(Β_v = 1.0)$ alınabilir. Daha kesin hesap yapılmadığı durumlarda burada $((M_p)_t \leq 1.25 (M_d)_t)$ kabul edilebilir. Düşey yükler ile Bölüm 4'e göre depremden hesaplanan kesme kuvvetinin 1.2D (boşluksuz perdeler) veya 1.4D (bağ kirişli perdeler) katı ile büyütülmesi ile elde edilen değerin, Denk.(7.16) ile hesaplanan $(V_e)$'den küçük olması durumunda, $(V_e)$ yerine bu kesme kuvveti kullanılacaktır.
                
   

    ### 7.6.7. Perdelerin Kesme Güvenliği

    #### 7.6.7.1 
    Perde kesitlerinin kesme dayanımı, $ V_r $, Denk.(7.17) ile hesaplanacaktır.

    $$
    V_r = A_{ch} (0.65 f_{ctd} + \p_{sh} f_{ywd})
    $$

    7.6.7.3’te tanımlanan $ V_e $ tasarım kesme kuvveti Denk.(7.18)’de verilen koşulları sağlayacaktır:

    $$
    V_e \leq V_r
    $$

    $$
    V_e \leq 0.85 A_{ch} \sqrt{f_{ck}} \quad (\t{Bosluksuz perdeler})
    $$

    $$
    V_e \leq 0.65 A_{ch} \sqrt{f_{ck}} \quad (\t{Bag kirisli perdeler})
    $$

    Aksi durumda, perde enine donatısı ve/veya perde kesit boyutları bu koşulları sağlamak üzere artırılacaktır.

    #### 7.6.7.2
    Temele bağlantı dizeyinde ve üst katlarda yapılacak yatay inşaat derzlerindeki düşey donatıya kesitte aktarılan kesme kuvveti gövdeyi oluşturan kesme bölgesinde yöntem ile kontrol edilecektir. Kesme sürtünmesi hesabında perde gövde ve bağlantı düşey donatısının tamami $ A_v $ ve pürüzlendirilmiş yüzey ile betonun katkısı $ f_{ctd} $ ile çözümü alınacaktır. $ V_e $ sürtünme kesme kuvveti Denk.(7.19)’da verilen koşulları sağlayacaktır:
    
    $$
    V_e \leq f_{ctd} A_c + \mu A_v f_{yd}
    $$

    $$
    V_e \leq \min[0.2 f_{ck} A_c; \ (3.3 + 0.08 f_{ck}) A_c]
    $$

    
    **Şekil 7.12**
    """)
    st.image(r"C:\Users\Emin\Desktop\deneme2\assets\7_12.png", caption="Şekil 7.12: Tasarım eğilme momenti ve kesme kuvveti diyagramları")

# COM kütüphanesini kapatma
