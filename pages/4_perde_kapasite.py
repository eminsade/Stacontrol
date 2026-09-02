import io
import comtypes.client
import streamlit as st
import json

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar

import pandas as pd
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode
from database import save_hesaplama, get_hesaplamalar, get_hesaplama_by_id
from utils import top_right_login
from session_config import init_session_state
from database import save_hesaplama

# Session state başlatma
init_session_state()

setup_sidebar()

# Sağ üstte giriş/kayıt butonları
top_right_login()

# COM kütüphanesini başlat
comtypes.CoInitialize()

st.title("Perde Kapasite Kontrolü")

tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:


    # URL'den saved_id parametresini al
    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    # Beton sabitleri
    concrete_mapping = {
        "C16": 16000, "C18": 18000, "C20": 20000, "C25": 25000, "C30": 30000,
        "C35": 35000, "C40": 40000, "C45": 45000, "C50": 50000, "C55": 55000, "C60": 60000
    }

    # AG Grid yapılandırması
    grid_options = {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Perde", "field": "Pier", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Uzunluk", "field": "WidthBot", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Kalınlık", "field": "ThickBot", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Beton Sınıfı", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
            "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_mapping.keys())}},
            {"headerName": "Kombinasyon", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Yük", "field": "Deprem Yük", "editable": True, "filter": "agSetColumnFilter",
            "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            
            {"headerName": "Kapasite", "field": "Deprem Kapasite", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                return Number(0.35 * cv * parseFloat(data.WidthBot || 0) * parseFloat(data.ThickBot || 0)).toFixed(2);
            """},
            {"headerName": "Deprem Yük Kapasite Yüzdesi", "field": "Deprem Yük Kapasite Yüzdesi", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.35 * cv * parseFloat(data.WidthBot || 0) * parseFloat(data.ThickBot || 0);
                return (data['Deprem Yük'] != null && capacity != 0) ?
                        (Math.abs(parseFloat(data['Deprem Yük']) / capacity * 100)).toFixed(1) + '%' : '';
            """},
            {"headerName": "Durum Deprem", "field": "Durum Deprem", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.35 * cv * parseFloat(data.WidthBot || 0) * parseFloat(data.ThickBot || 0);
                return (data['Deprem Yük'] != null && capacity != 0) ?
                        (parseFloat(data['Deprem Yük']) < capacity ? '✅' : '❌') : '';
            """}
        ],
        "defaultColDef": {"resizable": True, "sortable": True, "filter": True},
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "enableRangeSelection": True,
        "suppressContextMenu": False,
        "getContextMenuItems": "function(params) { var defaultItems = params.defaultItems; defaultItems.push({ name: 'Export CSV', action: function() { params.api.exportDataAsCsv(); } }); return defaultItems; }"
    }

    # Excel export fonksiyonu
    def to_excel(df):
        """DataFrame'i Excel formatına çevirir ve bayt olarak döndürür."""
        ordered_columns = [
            "Story", "Pier", "WidthBot", "ThickBot", "Beton Sınıfı", 
            "Deprem Kombinasyonu", "Deprem Yük", "Deprem Kapasite", 
            "Deprem Yük Kapasite Yüzdesi", "Durum Deprem"
        ]
        df = df[ordered_columns]
        column_name_mapping = {'Story': 'Kat', 'Pier': 'Perde', 'WidthBot': 'Uzunluk', 'ThickBot': 'Kalınlık'}
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

    # Kaydedilmiş veriyi yükleme
    if saved_id:
        username = st.session_state["username"]
        record = get_hesaplama_by_id(saved_id, username)
        if record is not None:
            st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
            sonuc_dict = json.loads(record["sonuc"])
            
            # Kaydedilmiş tabloyu DataFrame'e çevir
            updated_df = pd.DataFrame(sonuc_dict["final_table"])
            
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
        # Yeni hesaplama modu
        # ETABS'e bağlan ve birimleri ayarla
        try:
            etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
            SapModel = etabs_object.SapModel
        except Exception as e:
            st.error(f"ETABS'e bağlanılırken hata oluştu: {e}")
            st.stop()

        try:
            SapModel.SetPresentUnits(6)  # kN-m birimleri
        except Exception as e:
            st.error(f"ETABS birimleri ayarlanırken hata oluştu: {e}")
            st.stop()

        # Yük kombinasyonlarını al
        ret_combos = SapModel.RespCombo.GetNameList()
        num_combos = ret_combos[0]
        combo_names = ret_combos[1]

        if num_combos <= 0:
            st.error("ETABS'te yük kombinasyonları bulunamadı.")
            st.stop()

        # Seçilen kombinasyona göre tabloyu çekme fonksiyonu
        def get_table_for_combination(combo):
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

            TableKey_modal = 'Pier Forces'
            FieldKeyList = []
            GroupName = 'All'
            TableVersion = 1
            FieldsKeysIncluded = []
            NumberRecords = 0
            TableData_modal = []

            ret_modal = SapModel.DatabaseTables.GetTableForDisplayArray(
                TableKey_modal, FieldKeyList, GroupName, TableVersion,
                FieldsKeysIncluded, NumberRecords, TableData_modal
            )

            columns_modal = ret_modal[2]
            data_list_modal = ret_modal[4]

            num_columns_modal = len(columns_modal)
            if num_columns_modal == 0:
                st.error(f"ETABS'ten sütun verisi alınamadı. Tablo boş veya yanlış tablo anahtarı. ({combo})")
                return None

            rows_modal = [data_list_modal[i:i + num_columns_modal] for i in range(0, len(data_list_modal), num_columns_modal)]
            df_modal = pd.DataFrame(rows_modal, columns=columns_modal)
            df_modal.columns = df_modal.columns.str.strip()
            df_modal['OriginalOrder'] = df_modal.index

            df_modal['P'] = pd.to_numeric(df_modal['P'], errors='coerce')
            max_idx = df_modal.groupby(['Story', 'Pier'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
            filtered_df = df_modal.loc[max_idx]
            filtered_df = filtered_df.sort_values('OriginalOrder').reset_index(drop=True)

            display_columns = ['Story', 'Pier', 'OutputCase', 'P']
            filtered_df = filtered_df[display_columns]
            return filtered_df

        # Pier Section Properties tablosunu çekme fonksiyonu
        def get_pier_section_properties():
            table_key = 'Pier Section Properties'
            FieldKeyList = []
            GroupName = 'All'
            TableVersion = 1
            FieldsKeysIncluded = []
            NumberRecords = 0
            TableData = []

            ret = SapModel.DatabaseTables.GetTableForDisplayArray(
                table_key, FieldKeyList, GroupName, TableVersion,
                FieldsKeysIncluded, NumberRecords, TableData
            )
            columns = ret[2]
            data_list = ret[4]
            num_columns = len(columns)
            if num_columns == 0:
                st.error(f"ETABS'ten sütun verisi alınamadı. ({table_key})")
                return None
            rows = [data_list[i:i + num_columns] for i in range(0, len(data_list), num_columns)]
            df = pd.DataFrame(rows, columns=columns)
            df.columns = df.columns.str.strip()
            return df

        # Kullanıcı Arayüzü
        st.subheader("Deprem Kombinasyon Seçimi")
        main_deprem_combo = st.selectbox("Deprem Kombinasyon", combo_names, key="main_deprem_combo")
        is_basement = st.checkbox("YAPI BODRUMLU MU?")

        # Pier section properties'i erken al
        df_pier_section = get_pier_section_properties()
        if df_pier_section is None:
            st.error("Pier Section tabloları alınamadı.")
            st.stop()

        # df_temp'i başlat
        df_temp = get_table_for_combination(main_deprem_combo)

        # Bodrum Seçenekleri
        if is_basement:
            st.subheader("Bodrum Seçenekleri")
            story_options = df_temp['Story'].drop_duplicates().tolist() if df_temp is not None else []
            basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", options=story_options, key="basement_stories")
            basement_deprem_combo = st.selectbox("Bodrum Deprem Kombinasyon", combo_names, key="basement_deprem_combo")

        # Beton Sınıfı Seçimi
        st.subheader("Beton Sınıfı Seçimi")
        selected_concrete = st.selectbox("Beton Sınıfı", list(concrete_mapping.keys()), key="concrete_class")
        concrete_value = concrete_mapping[selected_concrete]

        # Final Tabloyu Getir
        if st.button("Final Tabloyu Getir"):
            df_deprem = get_table_for_combination(main_deprem_combo)
            df_deprem = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'P': 'Deprem Yük'})
            merged_df = df_deprem
            
            if is_basement:
                df_bodrum_deprem = get_table_for_combination(basement_deprem_combo)
                
                if basement_stories:
                    df_bodrum_deprem = df_bodrum_deprem[df_bodrum_deprem["Story"].isin(basement_stories)]
                
                df_bodrum_deprem = df_bodrum_deprem.rename(columns={'OutputCase': 'Bodrum Deprem Kombinasyonu', 'P': 'Bodrum Deprem Yük'})
                basement_merged = pd.merge(df_bodrum_deprem, df_pier_section[['Story', 'Pier', 'WidthBot', 'ThickBot']], 
                                        on=['Story', 'Pier'], how='outer')
                merged_final = pd.merge(merged_df, basement_merged, on=['Story', 'Pier'], how='left')
                merged_final["Deprem Kombinasyonu"] = merged_final["Bodrum Deprem Kombinasyonu"].combine_first(merged_final["Deprem Kombinasyonu"])
                merged_final["Deprem Yük"] = merged_final["Bodrum Deprem Yük"].combine_first(merged_final["Deprem Yük"])
                main_table = merged_final.drop(columns=['Bodrum Deprem Kombinasyonu', 'Bodrum Deprem Yük'])
            else:
                main_table = pd.merge(merged_df, df_pier_section[['Story', 'Pier', 'WidthBot', 'ThickBot']], 
                                    on=['Story', 'Pier'], how='left')

            final_table = main_table.copy()
            final_table['Beton Sınıfı'] = selected_concrete
            final_table['Deprem Yük'] = pd.to_numeric(final_table['Deprem Yük'], errors='coerce').abs().round(2)
            final_table['WidthBot'] = pd.to_numeric(final_table['WidthBot'], errors='coerce')
            final_table['ThickBot'] = pd.to_numeric(final_table['ThickBot'], errors='coerce')
            
            # İlk hesaplamalar
            final_table["Area"] = (final_table["WidthBot"] * final_table["ThickBot"]).round(2)
            final_table["Deprem Kapasite"] = (0.35 * concrete_value * final_table["Area"]).round(2)
            final_table["Deprem Yük Kapasite Yüzdesi"] = ((final_table["Deprem Yük"] / final_table["Deprem Kapasite"]) * 100).round(1).astype(str) + '%'
            final_table["Durum Deprem"] = final_table["Deprem Yük"] < final_table["Deprem Kapasite"]
            final_table["Durum Deprem"] = final_table["Durum Deprem"].map({True: "✅", False: "❌"})

            st.session_state["final_table"] = final_table

        # Tabloyu Görüntüle
        if "final_table" in st.session_state:
            grid_response = AgGrid(
                st.session_state["final_table"],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key=f"aggrid_{selected_concrete}"
            )
            
            # AG Grid'den dönen güncel veriyi al
            updated_df = pd.DataFrame(grid_response["data"])
            
            # Sayısal değerleri düzelt
            updated_df["WidthBot"] = pd.to_numeric(updated_df["WidthBot"], errors="coerce")
            updated_df["ThickBot"] = pd.to_numeric(updated_df["ThickBot"], errors="coerce")
            updated_df["Deprem Yük"] = pd.to_numeric(updated_df["Deprem Yük"], errors="coerce").abs()

            # Beton sınıfına göre kapasite hesaplamaları
            updated_df["Area"] = (updated_df["WidthBot"] * updated_df["ThickBot"]).round(2)
            updated_df["Deprem Kapasite"] = (0.35 * updated_df["Beton Sınıfı"].map(concrete_mapping).fillna(0) * updated_df["Area"]).round(2)
            updated_df["Deprem Yük Kapasite Yüzdesi"] = ((updated_df["Deprem Yük"] / updated_df["Deprem Kapasite"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum Deprem"] = updated_df["Deprem Yük"] < updated_df["Deprem Kapasite"]
            updated_df["Durum Deprem"] = updated_df["Durum Deprem"].map({True: "✅", False: "❌"})
            
            st.divider()
            st.subheader("Sonuç Kaydetme")

            # Yan yana iki sütun oluştur
            col1, col2 = st.columns([1, 1])  # İki sütunu eşit genişlikte ayırdık

            with col1:  # Sol sütun: Kayıt işlemi
                record_name = st.text_input("Kayıt için bir isim giriniz:", value="Perde Kapasite Kontrolü", key="record_name_input")
                kaydet_button = st.button("Sonucu Kaydet")
                
                if kaydet_button:
                    hesap_tipi = record_name
                    sonuc_dict = {
                        "final_table": updated_df.to_dict(orient="records"),
                        "concrete_class": selected_concrete,
                        "main_deprem_combo": main_deprem_combo
                    }
                    if is_basement:
                        sonuc_dict.update({
                            "basement_stories": basement_stories,
                            "basement_deprem_combo": basement_deprem_combo
                        })
                    sonuc_str = json.dumps(sonuc_dict, ensure_ascii=False, indent=2)
                    save_hesaplama(hesap_tipi, sonuc_str, st.session_state["username"], "perde_kapasite")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col2:  # Sağ sütun: Excel indirme butonu
                st.download_button(
                    "Excel Olarak İndir",
                    data=to_excel(updated_df),
                    file_name="perde_kapasite.xlsx",
                    mime="application/vnd.ms-excel",
                )

with tabs[1]:
    st.markdown("""
    ## Nasıl Çalışır?
    - **ETABS Bağlantısı:** ETABS'in açık ve aktif olduğundan emin olun.
    - **Deprem Kombinasyonu:** G+Q+E kombinasyonunu seçin.
    - **Bodrum Seçenekleri:** Yapı bodrumlu ise, ilgili bodrum katlarını seçin ve bodrum katlar için kombinasyonunu belirleyin.
    - **Beton Sınıfı Seçimi:** Kullandığınız beton sınıfını seçin.
    - **Sonuç:** Gerekli seçimleri yaptıktan sonra **"Kontrol Et"** butonuna basın.
    - **Kayıt:** Hesaplama sonuçlarını kaydedebilir veya Excel formatında indirebilirsiniz.
    
    ## TBDY 2018 
    **Madde 7.6.1.1:** Perdenin boşluklar çıkarıldıktan sonra kalan net enkesit alanı, Ndm TS 498'de hareketli
    yükler için tanımlanmış olan hareketli yük azaltma katsayıları da dikkate alınarak, G ve Q
    düşey yükler ve E deprem etkisinin ortak etkisi **G+Q+E** altında hesaplanan eksenel basınç
    kuvvetlerinin en büyüğü olmak üzere, **Ac ≥ Ndm / (0.35 fck)** koşulunu sağlayacaktır. Bağ kirişli
    (boşluklu) perdelerde Ac ve Ndm değerlerinin hesabında, boşluklu perde kesitinin tümü (perde
    parçalarının toplamı) gözönüne alınacaktır.
    """)

# COM kütüphanesini kapatma
comtypes.CoUninitialize()