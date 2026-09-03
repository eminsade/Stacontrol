import io
import streamlit as st
# Sayfa konfigürasyonu
st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
from etabs_bridge.streamlit_ui import connect_etabs
import pandas as pd
import json
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

# COM kütüphanesini başlatma

st.title("Kolon Eksenel Kuvvet Kontrolü")

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

    # AG Grid ayarları
    grid_options = {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter", "maxWidth": 80, "minWidth": 80},
            {"headerName": "Kolon", "field": "Column", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Kesit", "field": "SectProp", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Alan", "field": "Area", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
            "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(concrete_mapping.keys())}},
            {"headerName": "TS500 Komb", "field": "Düşey Kombinasyon", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Nd", "field": "Düşey Yük", "editable": True, "filter": "agSetColumnFilter",
            "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "0,9.fcd.Ac ", "field": "Düşey Kapasite", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                return 0.5 * cv * parseFloat(data.Area || 0);
            """},
            {"headerName": "%Nd/0,9.fcd.Ac", "field": "Düşey Yük Kapasite Yüzdesi", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.5 * cv * parseFloat(data.Area || 0);
                return (data['Düşey Yük'] != null && capacity != 0) ?
                        (Math.abs(parseFloat(data['Düşey Yük']) / capacity * 100)).toFixed(1) + '%' : '';
            """},
            {"headerName": "Nd < 0,9.fcd.Ac", "field": "Durum Düşey", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.5 * cv * parseFloat(data.Area || 0);
                return (data['Düşey Yük'] != null && capacity != 0) ?
                        (parseFloat(data['Düşey Yük']) < capacity ? '✅' : '❌') : '';
            """},
            {"headerName": "TBDY2018 Komb", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Ndm", "field": "Deprem Yük", "editable": True, "filter": "agSetColumnFilter",
            "valueFormatter": "function(params){ return params.value != null ? Math.abs(params.value).toFixed(2) : ''; }"},
            {"headerName": "0,4.fck.Ach", "field": "Deprem Kapasite", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                return 0.4 * cv * parseFloat(data.Area || 0);
            """},
            {"headerName": "%Ndm/0,4.fck.Ach", "field": "Deprem Yük Kapasite Yüzdesi", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.4 * cv * parseFloat(data.Area || 0);
                return (data['Deprem Yük'] != null && capacity != 0) ?
                        (Math.abs(parseFloat(data['Deprem Yük']) / capacity * 100)).toFixed(1) + '%' : '';
            """},
            {"headerName": "Ndm < 0,4.fck.Ach", "field": "Durum Deprem", "editable": False, "filter": "agSetColumnFilter",
            "valueGetter": """
                var mapping = {""" + ",".join([f"'{k}':{v}" for k, v in concrete_mapping.items()]) + """};
                var cv = mapping[data['Beton Sınıfı']] || 0;
                var capacity = 0.4 * cv * parseFloat(data.Area || 0);
                return (data['Deprem Yük'] != null && capacity != 0) ?
                        (parseFloat(data['Deprem Yük']) < capacity ? '✅' : '❌') : '';
            """}
        ],
        "suppressContextMenu": False,
        "sideBar": {"toolPanels": ["columns", "filters"]},
        "getContextMenuItems": "function(params) { var defaultItems = params.defaultItems; defaultItems.push({ name: 'Export CSV', action: function() { params.api.exportDataAsCsv(); } }); return defaultItems; }"
    }

    # Excel export fonksiyonu
    def to_excel(df):
        """DataFrame'i Excel formatına çevirir ve bayt olarak döndürür."""
        ordered_columns = [
            "Story", "Column", "SectProp", "Area", "Beton Sınıfı", "Düşey Kombinasyon", "Düşey Yük",
            "Düşey Kapasite", "Düşey Yük Kapasite Yüzdesi", "Durum Düşey", "Deprem Kombinasyonu",
            "Deprem Yük", "Deprem Kapasite", "Deprem Yük Kapasite Yüzdesi", "Durum Deprem"
        ]
        df = df[ordered_columns]
        column_name_mapping = {'Story': 'Kat', 'Column': 'Kolon', 'SectProp': 'Kesit', 'Area': 'Alan',
                            'Düşey Kombinasyon': 'TS500 Kombinasyon','Düşey Yük': 'Nd', 'Düşey Kapasite': '0,9.fcd.Ac',
                            'Düşey Yük Kapasite Yüzdesi': 'TS500 Kapasite Yüzdesi', 'Durum Düşey': 'TS500 Durum', 'Deprem Kombinasyonu': 'TBDY2018 Kombinasyon',
                                'Deprem Yük': 'Ndm', 'Deprem Kapasite': '0,4.fck.Ach', 'Deprem Yük Kapasite Yüzdesi': 'TBDY2018 Kapasite Yüzdesi', 'Durum Deprem': 'TBDY2018 Durum' }
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
        # Kullanıcının bilgisayarındaki ajan üzerinden bağlanılır; bağlantı
        # yoksa connect_etabs kurulum panelini gösterip sayfayı durdurur.
        SapModel = connect_etabs(units=6)  # kN-m

        ret_combos = SapModel.RespCombo.GetNameList()
        num_combos, combo_names = ret_combos[0], ret_combos[1]

        if num_combos <= 0:
            st.error("ETABS'te yük kombinasyonları bulunamadı.")
            st.stop()

        def get_table_for_combination(combo):
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            ret = SapModel.DatabaseTables.GetTableForDisplayArray(
                'Element Forces - Columns', [], 'All', 1, [], 0, []
            )
            columns, data_list = ret[2], ret[4]
            if not columns:
                st.error(f"ETABS'ten sütun verisi alınamadı ({combo})")
                return None
            rows = [data_list[i:i + len(columns)] for i in range(0, len(data_list), len(columns))]
            df = pd.DataFrame(rows, columns=columns).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            df['P'] = pd.to_numeric(df['P'], errors='coerce')
            max_idx = df.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
            filtered_df = df.loc[max_idx].sort_index().reset_index(drop=True)
            return filtered_df[['Story', 'Column', 'OutputCase', 'P']]

        def get_frame_section_properties():
            ret = SapModel.DatabaseTables.GetTableForDisplayArray(
                'Frame Assignments - Section Properties', [], 'All', 1, [], 0, []
            )
            columns, data_list = ret[2], ret[4]
            if not columns:
                st.error("Frame Assignments tablosu alınamadı.")
                return None
            rows = [data_list[i:i + len(columns)] for i in range(0, len(data_list), len(columns))]
            return pd.DataFrame(rows, columns=columns).apply(lambda x: x.str.strip() if x.dtype == "object" else x)

        def get_frame_section_property_definitions_summary():
            ret = SapModel.DatabaseTables.GetTableForDisplayArray(
                'Frame Section Property Definitions - Summary', [], 'All', 1, [], 0, []
            )
            columns, data_list = ret[2], ret[4]
            if not columns:
                st.error("Frame Section Summary tablosu alınamadı.")
                return None
            rows = [data_list[i:i + len(columns)] for i in range(0, len(data_list), len(columns))]
            return pd.DataFrame(rows, columns=columns).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
        
        st.subheader("Kombinasyon Seçimleri")
        main_dusey_combo = st.selectbox("TS500 Kombinasyon", combo_names, key="main_combo1")
        main_deprem_combo = st.selectbox("TBDY2018 Kombinasyon", combo_names, key="main_combo2")
        is_basement = st.checkbox("YAPI BODRUMLU MU?")

        if is_basement:
            st.subheader("Bodrum Seçenekleri")
            df_temp = get_table_for_combination(main_dusey_combo)
            story_options = df_temp['Story'].drop_duplicates().tolist() if df_temp is not None else []
            basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", options=story_options, key="basement_stories")
            basement_dusey_combo = st.selectbox("Bodrum TS500 Kombinasyon", combo_names, key="basement_combo1")
            basement_deprem_combo = st.selectbox("Bodrum TBDY2018 Kombinasyon", combo_names, key="basement_combo2")

        st.subheader("Beton Sınıfı Seçimi")
        selected_concrete = st.selectbox("Beton Sınıfı", list(concrete_mapping.keys()), key="concrete_class")
        concrete_value = concrete_mapping.get(selected_concrete, 0)

        if st.button("Kontrol Et"):
            df_dusey = get_table_for_combination(main_dusey_combo)
            df_deprem = get_table_for_combination(main_deprem_combo)
            if df_dusey is None or df_deprem is None:
                st.error("Ana tablo oluşturulamadı.")
                st.stop()

            df_dusey = df_dusey.rename(columns={'OutputCase': 'Düşey Kombinasyon', 'P': 'Düşey Yük'})
            df_deprem = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'P': 'Deprem Yük'})
            merged_df = pd.merge(df_dusey, df_deprem, on=['Story', 'Column'], how='left').sort_index().reset_index(drop=True)

            if is_basement:
                df_bodrum_dusey = get_table_for_combination(basement_dusey_combo)
                df_bodrum_deprem = get_table_for_combination(basement_deprem_combo)
                if df_bodrum_dusey is None or df_bodrum_deprem is None:
                    st.error("Bodrum kombinasyonları için veri alınamadı.")
                    st.stop()
                if basement_stories:
                    df_bodrum_dusey = df_bodrum_dusey[df_bodrum_dusey["Story"].isin(basement_stories)]
                    df_bodrum_deprem = df_bodrum_deprem[df_bodrum_deprem["Story"].isin(basement_stories)]
                df_bodrum_dusey = df_bodrum_dusey.rename(columns={'OutputCase': 'Bodrum Düşey Kombinasyon', 'P': 'Bodrum Düşey Yük'})
                df_bodrum_deprem = df_bodrum_deprem.rename(columns={'OutputCase': 'Bodrum Deprem Kombinasyonu', 'P': 'Bodrum Deprem Yük'})
                basement_merged = pd.merge(df_bodrum_dusey, df_bodrum_deprem, on=['Story', 'Column'], how='outer')
                merged_final = pd.merge(merged_df, basement_merged, on=['Story', 'Column'], how='left')
                merged_final["Düşey Kombinasyon"] = merged_final["Bodrum Düşey Kombinasyon"].combine_first(merged_final["Düşey Kombinasyon"])
                merged_final["Düşey Yük"] = merged_final["Bodrum Düşey Yük"].combine_first(merged_final["Düşey Yük"])
                merged_final["Deprem Kombinasyonu"] = merged_final["Bodrum Deprem Kombinasyonu"].combine_first(merged_final["Deprem Kombinasyonu"])
                merged_final["Deprem Yük"] = merged_final["Bodrum Deprem Yük"].combine_first(merged_final["Deprem Yük"])
                main_table = merged_final.drop(columns=['Bodrum Düşey Kombinasyon', 'Bodrum Düşey Yük', 'Bodrum Deprem Kombinasyonu', 'Bodrum Deprem Yük'])
            else:
                main_table = merged_df

            df_frame_section = get_frame_section_properties()
            df_frame_summary = get_frame_section_property_definitions_summary()
            if df_frame_section is None or df_frame_summary is None:
                st.error("Frame Section tabloları alınamadı.")
                st.stop()

            df_A = df_frame_section[['Story', 'Label', 'SectProp']]
            df_B = df_frame_summary[['Name', 'Area']]
            frame_section_table = pd.merge(df_A, df_B, left_on='SectProp', right_on='Name', how='left').drop(columns=['Name'])
            final_table = pd.merge(main_table, frame_section_table, left_on=['Story', 'Column'], right_on=['Story', 'Label'], how='left').drop(columns=['Label'])
            final_table['Beton Sınıfı'] = selected_concrete
            final_table['Düşey Yük'] = pd.to_numeric(final_table['Düşey Yük'], errors='coerce').abs().round(2)
            final_table['Deprem Yük'] = pd.to_numeric(final_table['Deprem Yük'], errors='coerce').abs().round(2)

            st.session_state["final_table"] = final_table

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
            
            updated_df = pd.DataFrame(grid_response["data"])
            updated_df["Area"] = pd.to_numeric(updated_df["Area"], errors="coerce")
            updated_df["Düşey Yük"] = pd.to_numeric(updated_df["Düşey Yük"], errors="coerce")
            updated_df["Deprem Yük"] = pd.to_numeric(updated_df["Deprem Yük"], errors="coerce")
            
            updated_df["Düşey Kapasite"] = (0.5 * concrete_value * updated_df["Area"]).round(2)
            updated_df["Düşey Yük Kapasite Yüzdesi"] = ((updated_df["Düşey Yük"].abs() / updated_df["Düşey Kapasite"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum Düşey"] = updated_df["Düşey Yük"] < updated_df["Düşey Kapasite"]
            updated_df["Durum Düşey"] = updated_df["Durum Düşey"].map({True: "✅", False: "❌"})
            
            updated_df["Deprem Kapasite"] = (0.4 * concrete_value * updated_df["Area"]).round(2)
            updated_df["Deprem Yük Kapasite Yüzdesi"] = ((updated_df["Deprem Yük"].abs() / updated_df["Deprem Kapasite"]) * 100).round(1).astype(str) + '%'
            updated_df["Durum Deprem"] = updated_df["Deprem Yük"] < updated_df["Deprem Kapasite"]
            updated_df["Durum Deprem"] = updated_df["Durum Deprem"].map({True: "✅", False: "❌"})
            
            st.divider()
            st.subheader("Sonuç Kaydetme")

            # Yan yana iki sütun oluştur
            col1, col2 = st.columns([1, 1])  # İki sütunu eşit genişlikte ayırdık

            with col1:  # Sol sütun: Kayıt işlemi
                record_name = st.text_input("Kayıt için bir isim giriniz:", value="Kolon Kapasite Kontrolü", key="record_name_input")
                kaydet_button = st.button("Sonucu Kaydet")
                
                if kaydet_button:
                    hesap_tipi = record_name
                    sonuc_dict = {
                        "final_table": updated_df.to_dict(orient="records"),
                        "concrete_class": selected_concrete,
                        "main_dusey_combo": main_dusey_combo,
                        "main_deprem_combo": main_deprem_combo
                    }
                    if is_basement:
                        sonuc_dict.update({
                            "basement_stories": basement_stories,
                            "basement_dusey_combo": basement_dusey_combo,
                            "basement_deprem_combo": basement_deprem_combo
                        })
                    sonuc_str = json.dumps(sonuc_dict, ensure_ascii=False, indent=2)
                    save_hesaplama(hesap_tipi, sonuc_str, st.session_state["username"], "kolon_kapasite")
                    st.success("Sonuç başarıyla kaydedildi!")

            with col2:  # Sağ sütun: Excel indirme butonu
                st.download_button(
                    "Excel Olarak İndir",
                    data=to_excel(updated_df),
                    file_name="final_table.xlsx",
                    mime="application/vnd.ms-excel",
                )

        with tabs[1]:
            st.markdown("""
            ## Nasıl Çalışır?
            - **ETABS Bağlantısı:** ETABS'in açık ve aktif olduğundan emin olun.
            - **Kombinasyon Seçimleri:** TS500 için tasarım eksenel kombinasyonunu, TBDY2018 için ise G+Q+E kombinasyonunu seçin.
            - **Bodrum Seçenekleri:** Yapı bodrumlu ise, ilgili bodrum katlarını seçin ve bodrum katlar için kombinasyonunu belirleyin.
            - **Beton Sınıfı Seçimi:** Kullandığınız beton sınıfını seçin.
            - **Sonuç:** Gerekli seçimleri yaptıktan sonra **"Kontrol Et"** butonuna basın.
            - **Kayıt:** Hesaplama sonuçlarını kaydedebilir veya Excel formatında indirebilirsiniz.
                        
            ## TS 500 
            **Madde 7.4.1:** Dikdörtgen kesitli kolonlarda kesit genişliği 250 mm den az olamaz. Ancak, I, T ve L kesitli kolonlarda
            en küçük kalınlık 200 mm, kutu kesitli kolonlarda ise en küçük et kalınlığı 120 mm olabilir. Daire kesitli
            kolonlarda, kolon çapı 300 mm den az olamaz. Ayrıca tüm kolonlarda, **Nd ≤ 0,9 fcd Ac** koşulu sağlanmalıdır.
            
            ## TBDY 2018 
            **Madde 7.3.1.2:** Kolonun brüt enkesit alanı, Ndm TS 498'de hareketli yükler için tanımlanmış olan
            hareketli yük azaltma katsayıları da dikkate alınarak, G ve Q düşey yükler ve E deprem
            etkisinin ortak etkisi **G+Q+E** altında hesaplanan eksenel basınç kuvvetlerinin en büyüğü
            olmak üzere, **Ac ≥ Ndm / (0.40 fck)**  koşulunu sağlayacaktır.
            """)
            

        # COM kütüphanesini kapatma
