import io
import streamlit as st
import json
import pandas as pd
import etabs_service
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplamalar, get_hesaplama_by_id
from utils import top_right_login
from session_config import init_session_state

# Streamlit page config
st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar

setup_sidebar()
# Beton sabitleri
concrete_mapping = {
    "C16": 16000, "C18": 18000, "C20": 20000, "C25": 25000, "C30": 30000,
    "C35": 35000, "C40": 40000, "C45": 45000, "C50": 50000, "C55": 55000, "C60": 60000
}

# Configuration mapping for dynamic parameters
config_mapping = {
    "paspayi_cm": 2.5  # Default value, will be updated by user input
}

# Function to generate grid_options with config_mapping
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
            {"headerName": "Kombinasyon", "field": "Kombinasyon", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Ve", "field": "Yük", "editable": True, "filter": "agSetColumnFilter",
             "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "Vr", "field": "Kapasite", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{'C16':16000, 'C18':18000, 'C20':20000, 'C25':25000, 'C30':30000,
                 'C35':35000, 'C40':40000, 'C45':45000, 'C50':50000, 'C55':55000, 'C60':60000}};
                 var cv = mapping[data['Beton Sınıfı']] || 0;
                 var width = parseFloat(data.Width || 0) * 10;  // cm'den mm'ye
                 var depth = parseFloat(data.Depth || 0) * 10 - (20 * {paspayi_cm});  // cm'den mm'ye ve paspayi çıkarma
                 var capacity = (0.85 * width * depth * Math.sqrt(cv / 1000)) / 1000;
                 return capacity.toFixed(2);
             """},
            {"headerName": "%Ve/Vr", "field": "Yük Kapasite Yüzdesi", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{'C16':16000, 'C18':18000, 'C20':20000, 'C25':25000, 'C30':30000,
                 'C35':35000, 'C40':40000, 'C45':45000, 'C50':50000, 'C55':55000, 'C60':60000}};
                 var cv = mapping[data['Beton Sınıfı']] || 0;
                 var width = parseFloat(data.Width || 0) * 10;
                 var depth = parseFloat(data.Depth || 0) * 10 - (20 * {paspayi_cm});
                 var capacity = (0.85 * width * depth * Math.sqrt(cv / 1000)) / 1000;
                 return (data['Yük'] != null && capacity != 0) ?
                     (Math.abs(parseFloat(data['Yük']) / capacity * 100)).toFixed(1) + '%' : '';
             """},
            {"headerName": "Ve < Vr", "field": "Durum", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{'C16':16000, 'C18':18000, 'C20':20000, 'C25':25000, 'C30':30000,
                 'C35':35000, 'C40':40000, 'C45':45000, 'C50':50000, 'C55':55000, 'C60':60000}};
                 var cv = mapping[data['Beton Sınıfı']] || 0;
                 var width = parseFloat(data.Width || 0) * 10;
                 var depth = parseFloat(data.Depth || 0) * 10 - (20 * {paspayi_cm});
                 var capacity = (0.85 * width * depth * Math.sqrt(cv / 1000)) / 1000;
                 return (data['Yük'] != null && capacity != 0) ?
                     (parseFloat(data['Yük']) < capacity ? '✅' : '❌') : '';
             """},
        ],
        "suppressContextMenu": False,
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "getContextMenuItems": "function(params) { var defaultItems = params.defaultItems; defaultItems.push({ name: 'Export CSV', action: function() { params.api.exportDataAsCsv(); } }); return defaultItems; }"
    }

# Excel export function
def to_excel(df):
    ordered_columns = [
        "Story", "Beam", "SectProp", "Width", "Depth", "Beton Sınıfı", 
        "Kombinasyon", "Yük", "Kapasite", "Yük Kapasite Yüzdesi", "Durum"
    ]
    df = df[ordered_columns]
    
    column_name_mapping = {
        'Story': 'Kat', 'Beam': 'Kiriş', 'SectProp': 'Kesit', 
        'Width': 'Genişlik (cm)', 'Depth': 'Derinlik (cm)', 'Beton Sınıfı': 'BS', 
        'Kombinasyon': 'Kombinasyon', 'Yük': 'Ve', 'Kapasite': 'Vr', 
        'Yük Kapasite Yüzdesi': '%Ve/Vr', 'Durum': 'Ve < Vr'
    }
    df = df.rename(columns=column_name_mapping)
    
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

# Session state başlatma
init_session_state()

# Sağ üstte giriş/kayıt butonları
top_right_login()

# COM kütüphanesini başlat
comtypes.CoInitialize()

st.title("Kiriş Kesme Kontrolü")

# Query params for saved records
query_params = st.query_params
saved_id = query_params.get("saved_id")

if saved_id:
    username = st.session_state["username"]
    record = get_hesaplama_by_id(saved_id, username)
    if record is not None:
        st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
        sonuc_dict = json.loads(record["sonuc"])
        
        # Kaydedilmiş tabloyu DataFrame'e çevir
        updated_df = pd.DataFrame(sonuc_dict["final_table"])
        
        # Get grid_options with the current paspayi_cm (default for saved data)
        grid_options = get_grid_options(config_mapping["paspayi_cm"])
        
        # AG Grid ile göster
        grid_response = AgGrid(
            updated_df,
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            fit_columns_on_grid_load=True,
            enable_enterprise_modules=True,
            key=f"aggrid_saved_{saved_id}"
        )
        
        # Excel export
        st.download_button(
            "Excel Olarak İndir",
            data=to_excel(updated_df),
            file_name=f"{record['hesap_tipi']}.xlsx",
            mime="application/vnd.ms-excel",
        )
    else:
        st.error("Kayıt bulunamadı veya erişim yetkiniz yok.")
else:
    # ETABS bağlantısı
    SapModel = etabs_service.get_active_sap_model()
    if SapModel is None:
        st.error("ETABS'e bağlanılamadı. Lütfen STACONT Bridge'in ve ETABS modelinizin açık olduğundan emin olun.")
        st.stop()

    # Yük kombinasyonları
    ret_combos = SapModel.RespCombo.GetNameList()
    num_combos = ret_combos[0]
    combo_names = ret_combos[1]

    if num_combos <= 0:
        st.error("ETABS'te yük kombinasyonları bulunamadı.")
        st.stop()

    # get_table_for_combination fonksiyonu
    def get_table_for_combination(combo):
        SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
        SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
        SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

        TableKey_modal = 'Element Forces - Beams'
        ret_modal = SapModel.DatabaseTables.GetTableForDisplayArray(
            TableKey_modal, [], 'All', 1, [], 0, []
        )

        columns_modal = ret_modal[2]
        data_list_modal = ret_modal[4]

        num_columns_modal = len(columns_modal)
        if num_columns_modal == 0:
            st.error(f"ETABS'ten sütun verisi alınamadı. Tablo boş veya yanlış tablo anahtarı. ({combo})")
            return None

        rows_modal = [data_list_modal[i: i + num_columns_modal] for i in range(0, len(data_list_modal), num_columns_modal)]
        df_modal = pd.DataFrame(rows_modal, columns=columns_modal)
        df_modal.columns = df_modal.columns.str.strip()
        df_modal['OriginalOrder'] = df_modal.index

        df_modal['V2'] = pd.to_numeric(df_modal['V2'], errors='coerce')
        max_idx = df_modal.groupby(['Story', 'Beam'], sort=False)['V2'].apply(lambda x: x.abs().idxmax())
        filtered_df = df_modal.loc[max_idx]
        filtered_df = filtered_df.sort_values('OriginalOrder').reset_index(drop=True)
        
        display_columns = ['Story', 'Beam', 'OutputCase', 'V2']
        filtered_df = filtered_df[display_columns]
        return filtered_df

    # Yük kombinasyonu ve bodrum seçenekleri
    st.subheader("Düşey ve Deprem Kombinasyonlarını Seçimi")
    main_combo = st.selectbox("Kombinasyon", combo_names, key="main_combo")
    is_basement = st.checkbox("YAPI BODRUMLU MU?")

    if is_basement:
        st.subheader("Bodrum Seçenekleri")
        df_temp = get_table_for_combination(main_combo)
        if df_temp is not None:
            story_options = df_temp['Story'].drop_duplicates().tolist()
        else:
            story_options = []
        basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", options=story_options, key="basement_stories")
        basement_combo = st.selectbox("Bodrum Düşey Kombinasyon", combo_names, key="basement_combo")

    # Beton sınıfı seçimi
    st.subheader("Beton Sınıfı Seçimi")
    concrete_options = list(concrete_mapping.keys())
    selected_concrete = st.selectbox("Beton Sınıfı", concrete_options, key="concrete_class")
    concrete_value = concrete_mapping.get(selected_concrete, 0)

    # Paspayi girişi (cm cinsinden) - Update config_mapping
    st.subheader("Paspayi Değeri (cm)")
    config_mapping["paspayi_cm"] = st.number_input(
        "Paspayi (cm)", min_value=0.0, value=config_mapping["paspayi_cm"], step=0.1, key="paspayi_cm"
    )

    # Get grid_options with the current paspayi_cm value
    grid_options = get_grid_options(config_mapping["paspayi_cm"])

    # Frame Assignments ve Concrete Rectangular tabloları
    def get_frame_section_properties():
        table_key = 'Frame Assignments - Section Properties'
        ret = SapModel.DatabaseTables.GetTableForDisplayArray(table_key, [], 'All', 1, [], 0, [])
        columns = ret[2]
        data_list = ret[4]
        num_columns = len(columns)
        if num_columns == 0:
            st.error(f"ETABS'ten sütun verisi alınamadı. ({table_key})")
            return None
        rows = [data_list[i: i + num_columns] for i in range(0, len(data_list), num_columns)]
        df = pd.DataFrame(rows, columns=columns)
        df.columns = df.columns.str.strip()
        return df

    def get_frame_section_property_definitions_concrete_rectangular():
        table_key = 'Frame Section Property Definitions - Concrete Rectangular'
        ret = SapModel.DatabaseTables.GetTableForDisplayArray(table_key, [], 'All', 1, [], 0, [])
        columns = ret[2]
        data_list = ret[4]
        num_columns = len(columns)
        if num_columns == 0:
            st.error(f"ETABS'ten sütun verisi alınamadı. ({table_key})")
            return None
        rows = [data_list[i: i + num_columns] for i in range(0, len(data_list), num_columns)]
        df = pd.DataFrame(rows, columns=columns)
        df.columns = df.columns.str.strip()
        return df

    # Final tablo oluşturma
    if st.button("Final Tabloyu Getir"):
        df_dusey = get_table_for_combination(main_combo)
        df_dusey = df_dusey.rename(columns={'OutputCase': 'Kombinasyon', 'V2': 'Yük'})
        
        df_frame_section = get_frame_section_properties()
        df_frame_concrete = get_frame_section_property_definitions_concrete_rectangular()
        
        if df_frame_section is None or df_frame_concrete is None:
            st.error("Frame Section veya Concrete Rectangular tabloları alınamadı.")
            st.stop()
        
        df_A = df_frame_section[['Story', 'Label', 'SectProp']]
        df_B = df_frame_concrete[['Name', 't2', 't3']]
        frame_section_table = pd.merge(df_A, df_B, left_on='SectProp', right_on='Name', how='left')
        frame_section_table = frame_section_table.drop(columns=['Name'])
        
        # Width ve Depth cm cinsine çevriliyor (ETABS mm kullanıyor)
        frame_section_table['Width'] = pd.to_numeric(frame_section_table['t2'], errors='coerce')*100  
        frame_section_table['Depth'] = pd.to_numeric(frame_section_table['t3'], errors='coerce')*100 
        merged_df = pd.merge(df_dusey, frame_section_table, 
                            left_on=['Story', 'Beam'], 
                            right_on=['Story', 'Label'], 
                            how='left', 
                            sort=False)
        merged_df = merged_df.drop(columns=['Label', 't2', 't3'])
        merged_df = merged_df.sort_index().reset_index(drop=True)
        
        if is_basement:
            df_bodrum = get_table_for_combination(basement_combo)
            if basement_stories:
                df_bodrum = df_bodrum[df_bodrum["Story"].isin(basement_stories)]
            
            df_bodrum_dusey = df_bodrum.rename(columns={'OutputCase': 'Kombinasyon', 'V2': 'Yük'})
            
            basement_merged = pd.merge(df_bodrum_dusey, frame_section_table, 
                                    left_on=['Story', 'Beam'], 
                                    right_on=['Story', 'Label'], 
                                    how='outer')
            basement_merged = basement_merged.drop(columns=['Label', 't2', 't3'])
            
            merged_final = pd.merge(merged_df, basement_merged, 
                                on=['Story', 'Beam'], 
                                how='left', 
                                suffixes=('', '_basement'))
            merged_final["Kombinasyon"] = merged_final["Kombinasyon_basement"].combine_first(merged_final["Kombinasyon"])
            merged_final["Yük"] = merged_final["Yük_basement"].combine_first(merged_df["Yük"])
            
            main_table = merged_final.drop(columns=['Kombinasyon_basement', 'Yük_basement'])
        else:
            main_table = merged_df

        main_table['Beton Sınıfı'] = selected_concrete
        main_table['Yük'] = pd.to_numeric(main_table['Yük'], errors='coerce').abs().round(2)
        
        # Clean up any previously computed columns
        for col in ["Kapasite", "Yük Kapasite Yüzdesi", "Durum"]:
            if col in main_table.columns:
                main_table.drop(columns=[col], inplace=True)
                
        st.session_state["final_table"] = main_table

    # AG Grid ile final tabloyu gösterme ve Excel export
    if "final_table" in st.session_state:
        grid_response = AgGrid(
            st.session_state["final_table"],
            gridOptions=grid_options,
            update_mode=GridUpdateMode.VALUE_CHANGED,
            data_return_mode=DataReturnMode.AS_INPUT,
            fit_columns_on_grid_load=True,
            enable_enterprise_modules=True,
            key=f"aggrid_{selected_concrete}_{config_mapping['paspayi_cm']}"
        )
        
        updated_df = grid_response["data"]
        
        # Python tarafında hesaplamaları tekrar uygulama
        updated_df["Width"] = pd.to_numeric(updated_df["Width"], errors="coerce")
        updated_df["Depth"] = pd.to_numeric(updated_df["Depth"], errors="coerce")
        updated_df["Yük"] = pd.to_numeric(updated_df["Yük"], errors="coerce")
        
        # Kapasite hesaplamaları (Width ve Depth cm cinsinden, paspayi cm cinsinden)
        updated_df["Kapasite"] = (
            (0.85 * (updated_df["Width"] * 10) * 
             (updated_df["Depth"] * 10 - 20 * config_mapping["paspayi_cm"]) * 
             ((concrete_value / 1000) ** 0.5)).round(2)
        ) / 1000
        updated_df["Yük Kapasite Yüzdesi"] = (
            (updated_df["Yük"].abs() / updated_df["Kapasite"]) * 100
        ).round(1).astype(str) + '%'
        updated_df["Durum"] = updated_df["Yük"] < updated_df["Kapasite"]
        updated_df["Durum"] = updated_df["Durum"].map({True: "✅", False: "❌"})
        
        st.divider()
        st.subheader("Sonuç Kaydetme")

        # Yan yana iki sütun oluştur
        col1, col2 = st.columns([1, 1])

        with col1:  # Sol sütun: Kayıt işlemi
            record_name = st.text_input("Kayıt için bir isim giriniz:", value="Kiris Kesme Kontrolü", key="record_name_input")
            kaydet_button = st.button("Sonucu Kaydet")
            
            if kaydet_button:
                hesap_tipi = record_name
                sonuc_dict = {
                    "final_table": updated_df.to_dict(orient="records"),
                    "concrete_class": selected_concrete,
                    "main_combo": main_combo
                }
                if is_basement:
                    sonuc_dict.update({
                        "basement_stories": basement_stories,
                        "basement_combo": basement_combo
                    })
                sonuc_str = json.dumps(sonuc_dict, ensure_ascii=False, indent=2)
                save_hesaplama(hesap_tipi, sonuc_str, st.session_state["username"], "kiris_kesme")
                st.success("Sonuç başarıyla kaydedildi!")

        with col2:  # Sağ sütun: Excel indirme butonu
            st.download_button(
                "Excel Olarak İndir",
                data=to_excel(updated_df),
                file_name="kiris_kesme.xlsx",
                mime="application/vnd.ms-excel",
            )

# COM kütüphanesini kapatma
comtypes.CoUninitialize()