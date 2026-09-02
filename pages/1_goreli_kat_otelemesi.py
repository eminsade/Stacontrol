import streamlit as st
st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)
from sidebar import setup_sidebar
import pandas as pd
import plotly.graph_objects as go
import json
import io
import etabs_service

from database import save_hesaplama, get_hesaplamalar
from utils import top_right_login
from session_config import init_session_state



# Session state'i başlatıyoruz
init_session_state()



setup_sidebar()

# Üyelik sistemini sağ üstte gösteriyoruz
top_right_login()

st.title("Göreli Kat Ötelemesi Kontrolü")

tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:

    # -------------------------------------------------------------------------
    # URL'deki saved_id kontrolü (Query Params)
    # -------------------------------------------------------------------------
    if "saved_id" in st.query_params:
        try:
            saved_id = int(st.query_params["saved_id"])  # String'i integer'a çeviriyoruz
            
            # Kullanıcı girişi kontrolü
            if st.session_state.get("logged_in"):
                username = st.session_state["username"]
                df_saved = get_hesaplamalar(username)
            else:
                df_saved = get_hesaplamalar()
            
            # ID'ye göre filtreleme
            saved_record = df_saved[df_saved["id"] == saved_id]
            
            if not saved_record.empty:
                try:
                    saved_result = saved_record["sonuc"].iloc[0]
                    data = json.loads(saved_result)
                    
                    # Kaydedilmiş verilerden DataFrame'ler oluşturuluyor
                    df_x_saved = pd.DataFrame(data["df_x_final"])
                    df_y_saved = pd.DataFrame(data["df_y_final"])
                    
                    st.info("Bu kayıt daha önce kaydedildi. Aşağıda kaydedilmiş veriler görüntülenmektedir.")
                    
                    st.subheader("Göreli Kat Ötelemesi Kontrolü - X Yönü")
                    st.dataframe(df_x_saved)
                    st.subheader("Göreli Kat Ötelemesi Kontrolü - Y Yönü")
                    st.dataframe(df_y_saved)
                    
                    # Grafik oluşturma
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=df_x_saved["λ * δᵢ,ₘₐₓ / hᵢ"],
                        y=df_x_saved["Kat"],
                        mode="lines+markers",
                        name="Öteleme (X)",
                        line=dict(color="blue")
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_x_saved["Sınır Değeri"],
                        y=df_x_saved["Kat"],
                        mode="lines+markers",
                        name="Sınır Değeri (X)",
                        line=dict(color="red")
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_y_saved["λ * δᵢ,ₘₐₓ / hᵢ"],
                        y=df_y_saved["Kat"],
                        mode="lines+markers",
                        name="Öteleme (Y)",
                        line=dict(color="green")
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_y_saved["Sınır Değeri"],
                        y=df_y_saved["Kat"],
                        mode="lines+markers",
                        name="Sınır Değeri (Y)",
                        line=dict(color="orange")
                    ))
                    story_order = df_x_saved["Kat"].tolist()
                    fig.update_layout(
                        title="X ve Y Yönü İçin Öteleme ve Sınır Değeri Grafiği",
                        xaxis_title="Öteleme",
                        yaxis_title="Kat",
                        yaxis=dict(categoryorder="array", categoryarray=story_order),
                        height=600,
                        width=800
                    )
                    st.plotly_chart(fig, use_container_width=False)
                    
                    # Grafiği export edebilmek için session_state'e kaydediyoruz
                    st.session_state["fig"] = fig
                except Exception as e:
                    st.error(f"Kaydedilen veriler çözümlenemedi: {str(e)}")
                st.stop()
            else:
                st.error(f"Belirtilen ID ({saved_id}) için kayıt bulunamadı.")
                st.stop()
        except ValueError:
            st.error("Geçersiz saved_id parametresi")
            st.stop()

    # =============================================================================
    # 1. ETABS'e Bağlanma
    # =============================================================================
    with st.container():
        SapModel = etabs_service.get_active_sap_model()
        if SapModel is None:
            st.error("ETABS'e bağlanılamadı. Lütfen STACONT Bridge'in ve ETABS modelinizin açık olduğundan emin olun.")
            st.stop()

    # =============================================================================
    # 2. Story Drifts Yük Durumları ve Modal Participating Mass Ratios Verisinin Hazırlanması
    # =============================================================================
    ret_cases = SapModel.LoadCases.GetNameList()
    number_of_cases = ret_cases[0]
    case_names = ret_cases[1]

    if number_of_cases <= 0:
        st.error("ETABS'te Story Drifts için yük durumları bulunamadı.")
        st.stop()

    # Modal tablo verileri
    TableKey_modal = 'Modal Participating Mass Ratios'
    FieldKeyList = []
    GroupName = 'All'
    TableVersion = 1
    FieldsKeysIncluded = []
    NumberRecords = 0

    SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
    SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
    SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

    TableData_modal = []
    ret_modal = SapModel.DatabaseTables.GetTableForDisplayArray(
        TableKey_modal, FieldKeyList, GroupName, TableVersion,
        FieldsKeysIncluded, NumberRecords, TableData_modal
    )
    columns_modal = ret_modal[2]
    data_list_modal = ret_modal[4]
    num_columns_modal = len(columns_modal)
    rows_modal = [data_list_modal[i: i + num_columns_modal] for i in range(0, len(data_list_modal), num_columns_modal)]
    df_modal = pd.DataFrame(rows_modal, columns=columns_modal)
    df_modal.columns = df_modal.columns.str.strip()

    if "Case" in df_modal.columns:
        unique_modal_cases = sorted(df_modal["Case"].unique())
    else:
        st.warning("Modal Participating Mass Ratios tablosunda 'Case' sütunu bulunamadı!")
        unique_modal_cases = []

    # =============================================================================
    # 3. Gerekli Girişlerin Tek Formda Toplanması
    # =============================================================================
    with st.form("input_form"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown('<h3 style="font-size:20px;">Yük Durumu Seçimi</h3>', unsafe_allow_html=True)
            selected_cases_x = st.multiselect("X Yönü için Yük Durumunu Seçin:", case_names)
            st.markdown('<h3 style="font-size:20px;">DD2</h3>', unsafe_allow_html=True)
            Sds_DD2 = st.number_input("Sds Değeri", min_value=0.0, format="%.3f")
            Sd1_DD2 = st.number_input("Sd1 Değeri", min_value=0.0, format="%.3f")
            st.markdown('<h3 style="font-size:20px;">DD3</h3>', unsafe_allow_html=True)
            Sds_DD3 = st.number_input(" Sds Değeri", min_value=0.0, format="%.3f")
            Sd1_DD3 = st.number_input(" Sd1 Değeri", min_value=0.0, format="%.3f")
        with col2:
            selected_cases_y = st.multiselect("Y Yönü için Yük Durumunu Seçin:", case_names)
            selected_modal_cases = st.multiselect("Modal Case Seçin:", unique_modal_cases)
            st.markdown('<h3 style="font-size:20px;">Yapı Bilgileri</h3>', unsafe_allow_html=True)
            R = st.number_input("R Değeri", value=0.0, format="%.1f")
            I = st.number_input("I Değeri", value=0.0, format="%.1f")
            K_option = st.selectbox("K Değeri", options=["1 (Betonarme)", "0.5 (Çelik)"])
            K = 1.0 if K_option == "1 (Betonarme)" else 0.5
            Ks_option = st.selectbox("Ks Değeri", options=["0.008 (4.34a)", "0.016 (4.34b)"])
            Ks = 0.008 if Ks_option == "0.008 (4.34a)" else 0.016

        hesapla_button = st.form_submit_button(label="Kontrol Et")

    # =============================================================================
    # 4. Hesaplamaların Yapılması (Form gönderildikten sonra)
    # =============================================================================
    if hesapla_button:
        if not selected_cases_x:
            st.error("Lütfen X yönü için en az bir yük durumu seçiniz.")
        elif not selected_cases_y:
            st.error("Lütfen Y yönü için en az bir yük durumu seçiniz.")
        elif not selected_modal_cases:
            st.error("Lütfen Modal Participating Mass Ratios için en az bir Case seçiniz.")
        elif Sds_DD2 == 0 or Sds_DD3 == 0:
            st.error("Hata: Sds değerleri sıfır olamaz.")
        else:
            # 4.1 ETABS'ten Story Drifts verisinin çekilmesi
            TableKey = 'Story Drifts'
            FieldKeyList = []
            GroupName = 'All'
            TableVersion = 1
            FieldsKeysIncluded = []
            NumberRecords = 0

            # X yönü için veriler:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay(selected_cases_x)
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            TableData = []
            ret_x = SapModel.DatabaseTables.GetTableForDisplayArray(
                TableKey, FieldKeyList, GroupName, TableVersion,
                FieldsKeysIncluded, NumberRecords, TableData
            )
            columns_x = ret_x[2]
            data_list_x = ret_x[4]
            num_columns_x = len(columns_x)
            rows_x = [data_list_x[i: i + num_columns_x] for i in range(0, len(data_list_x), num_columns_x)]
            df_x = pd.DataFrame(rows_x, columns=columns_x)
            df_x.columns = df_x.columns.str.strip()
            df_x["Direction"] = df_x["Direction"].astype(str).str.strip().str.upper()
            df_x_filtered = df_x[df_x["Direction"] == "X"]
            required_columns = ["Story", "OutputCase", "Direction", "Drift"]
            df_x_final = df_x_filtered[required_columns] if set(required_columns).issubset(df_x_filtered.columns) else df_x_filtered

            # Y yönü için veriler:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay(selected_cases_y)
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            TableData = []
            ret_y = SapModel.DatabaseTables.GetTableForDisplayArray(
                TableKey, FieldKeyList, GroupName, TableVersion,
                FieldsKeysIncluded, NumberRecords, TableData
            )
            columns_y = ret_y[2]
            data_list_y = ret_y[4]
            num_columns_y = len(columns_y)
            rows_y = [data_list_y[i: i + num_columns_y] for i in range(0, len(data_list_y), num_columns_y)]
            df_y = pd.DataFrame(rows_y, columns=columns_y)
            df_y.columns = df_y.columns.str.strip()
            df_y["Direction"] = df_y["Direction"].astype(str).str.strip().str.upper()
            df_y_filtered = df_y[df_y["Direction"] == "Y"]
            df_y_final = df_y_filtered[required_columns] if set(required_columns).issubset(df_y_filtered.columns) else df_y_filtered

            # 4.2 Modal Participating Mass Ratios ile Tx ve Ty hesaplanması
            df_modal_filtered = df_modal[df_modal["Case"].isin(selected_modal_cases)]
            Tx = None
            Ty = None
            if "UX" in df_modal_filtered.columns and "Period" in df_modal_filtered.columns:
                df_modal_filtered["UX_numeric"] = pd.to_numeric(df_modal_filtered["UX"], errors='coerce')
                max_ux = df_modal_filtered["UX_numeric"].max()
                Tx_array = df_modal_filtered.loc[df_modal_filtered["UX_numeric"] == max_ux, "Period"].unique()
                if len(Tx_array) > 0:
                    try:
                        Tx = float(Tx_array[0])
                    except:
                        Tx = None
            if "UY" in df_modal_filtered.columns and "Period" in df_modal_filtered.columns:
                df_modal_filtered["UY_numeric"] = pd.to_numeric(df_modal_filtered["UY"], errors='coerce')
                max_uy = df_modal_filtered["UY_numeric"].max()
                Ty_array = df_modal_filtered.loc[df_modal_filtered["UY_numeric"] == max_uy, "Period"].unique()
                if len(Ty_array) > 0:
                    try:
                        Ty = float(Ty_array[0])
                    except:
                        Ty = None
            if Tx is None or Ty is None:
                st.error("Tx veya Ty değeri hesaplanamadı. Lütfen Modal Participating Mass Ratios tablosundaki Case değerlerini kontrol ediniz.")
            else:
                # 4.3 DD2 ve DD3 hesaplamaları (Sae ve λ değerleri)
                Tl = 6
                Tb_DD2 = Sd1_DD2 / Sds_DD2
                Ta_DD2 = 0.2 * Tb_DD2
                Tb_DD3 = Sd1_DD3 / Sds_DD3
                Ta_DD3 = 0.2 * Tb_DD3

                if 0 <= Tx <= Ta_DD2:
                    Sae_x_DD2 = (0.4 + 0.6 * (Tx / Ta_DD2)) * Sds_DD2
                elif Ta_DD2 < Tx <= Tb_DD2:
                    Sae_x_DD2 = Sds_DD2
                elif Tb_DD2 < Tx <= Tl:
                    Sae_x_DD2 = Sd1_DD2 / Tx
                else:
                    Sae_x_DD2 = (Sd1_DD2 * Tl) / (Tx ** 2)
                if 0 <= Ty <= Ta_DD2:
                    Sae_y_DD2 = (0.4 + 0.6 * (Ty / Ta_DD2)) * Sds_DD2
                elif Ta_DD2 < Ty <= Tb_DD2:
                    Sae_y_DD2 = Sds_DD2
                elif Tb_DD2 < Ty <= Tl:
                    Sae_y_DD2 = Sd1_DD2 / Ty
                else:
                    Sae_y_DD2 = (Sd1_DD2 * Tl) / (Ty ** 2)

                if 0 <= Tx <= Ta_DD3:
                    Sae_x_DD3 = (0.4 + 0.6 * (Tx / Ta_DD3)) * Sds_DD3
                elif Ta_DD3 < Tx <= Tb_DD3:
                    Sae_x_DD3 = Sds_DD3
                elif Tb_DD3 < Tx <= Tl:
                    Sae_x_DD3 = Sd1_DD3 / Tx
                else:
                    Sae_x_DD3 = (Sd1_DD3 * Tl) / (Tx ** 2)
                if 0 <= Ty <= Ta_DD3:
                    Sae_y_DD3 = (0.4 + 0.6 * (Ty / Ta_DD3)) * Sds_DD3
                elif Ta_DD3 < Ty <= Tb_DD3:
                    Sae_y_DD3 = Sds_DD3
                elif Tb_DD3 < Ty <= Tl:
                    Sae_y_DD3 = Sd1_DD3 / Ty
                else:
                    Sae_y_DD3 = (Sd1_DD3 * Tl) / (Ty ** 2)

                lambda_x = Sae_x_DD3 / Sae_x_DD2
                lambda_y = Sae_y_DD3 / Sae_y_DD2

                # 4.4 Sınır Değeri ve Öteleme Hesaplamaları
                limit_value = Ks * K
                df_x_final["Sınır Değeri"] = limit_value
                df_y_final["Sınır Değeri"] = limit_value

                df_x_final["Drift_numeric"] = pd.to_numeric(df_x_final["Drift"], errors="coerce")
                df_x_final["λ * δᵢ,ₘₐₓ / hᵢ"] = (lambda_x * R * df_x_final["Drift_numeric"]) / I

                df_y_final["Drift_numeric"] = pd.to_numeric(df_y_final["Drift"], errors="coerce")
                df_y_final["λ * δᵢ,ₘₐₓ / hᵢ"] = (lambda_y * R * df_y_final["Drift_numeric"]) / I

                output_columns = ["Story", "OutputCase", "Direction", "Drift", "λ * δᵢ,ₘₐₓ / hᵢ", "Sınır Değeri"]
                df_x_final = df_x_final[output_columns]
                df_y_final = df_y_final[output_columns]

                df_x_final["Durum"] = df_x_final.apply(
                    lambda row: "✅" if row["λ * δᵢ,ₘₐₓ / hᵢ"] < row["Sınır Değeri"] else "❌", axis=1
                )
                df_y_final["Durum"] = df_y_final.apply(
                    lambda row: "✅" if row["λ * δᵢ,ₘₐₓ / hᵢ"] < row["Sınır Değeri"] else "❌", axis=1
                )

                final_columns = ["Story", "OutputCase", "Direction", "Drift", "λ * δᵢ,ₘₐₓ / hᵢ", "Sınır Değeri", "Durum"]
                df_x_final = df_x_final[final_columns]
                df_y_final = df_y_final[final_columns]

                # Sütun isimlerini güncelleyelim: Story -> Kat, OutputCase -> Yük, Direction -> Yön
                rename_mapping = {"Story": "Kat", "OutputCase": "Yük", "Direction": "Yön"}
                df_x_final = df_x_final.rename(columns=rename_mapping)
                df_y_final = df_y_final.rename(columns=rename_mapping)

                # Hesaplama sonuçlarını session_state'e kaydediyoruz
                st.session_state["df_x_final"] = df_x_final
                st.session_state["df_y_final"] = df_y_final
                st.session_state["calculation_done"] = True

    # =============================================================================
    # Hesaplama Sonuçlarının (Kontrol Ekranının) Gösterilmesi
    # =============================================================================
    if st.session_state.get("calculation_done", False):
        tab1, tab2 = st.columns(2)
        with tab1:
            st.subheader("Göreli  Kat Ötelemesi Kontrolü - X Yönü")
            st.dataframe(st.session_state["df_x_final"])
        with tab2:
            st.subheader("Göreli Kat Ötelemesi Kontrolü - Y Yönü")
            st.dataframe(st.session_state["df_y_final"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=st.session_state["df_x_final"]["λ * δᵢ,ₘₐₓ / hᵢ"],
            y=st.session_state["df_x_final"]["Kat"],
            mode="lines+markers",
            name="Öteleme (X)",
            line=dict(color="blue")
        ))
        fig.add_trace(go.Scatter(
            x=st.session_state["df_x_final"]["Sınır Değeri"],
            y=st.session_state["df_x_final"]["Kat"],
            mode="lines+markers",
            name="Sınır Değeri (X)",
            line=dict(color="red")
        ))
        fig.add_trace(go.Scatter(
            x=st.session_state["df_y_final"]["λ * δᵢ,ₘₐₓ / hᵢ"],
            y=st.session_state["df_y_final"]["Kat"],
            mode="lines+markers",
            name="Öteleme (Y)",
            line=dict(color="green")
        ))
        fig.add_trace(go.Scatter(
            x=st.session_state["df_y_final"]["Sınır Değeri"],
            y=st.session_state["df_y_final"]["Kat"],
            mode="lines+markers",
            name="Sınır Değeri (Y)",
            line=dict(color="orange")
        ))
        kat_order = st.session_state["df_x_final"]["Kat"].tolist()
        fig.update_layout(
            title="X ve Y Yönü İçin Öteleme ve Sınır Değeri Grafiği",
            xaxis_title="Öteleme",
            yaxis_title="Kat",
            yaxis=dict(categoryorder="array", categoryarray=kat_order),
            height=600,
            width=800
        )
        st.plotly_chart(fig, use_container_width=False)
        st.session_state["fig"] = fig

    # =============================================================================
    # 5. Sonucu Kaydet Butonu ve Excel İndirme
    # =============================================================================
    if "df_x_final" in st.session_state and "df_y_final" in st.session_state:
        col1, col2 = st.columns(2)
        with col1:
            record_name = st.text_input(
                "Kayıt için bir isim giriniz:", 
                value="Göreli Kat Ötelemesi - X ve Y", 
                key="record_name_input"
            )
            kaydet_button = st.button("Sonucu Kaydet")
            if kaydet_button:
                if st.session_state.get("logged_in"):
                    hesap_tipi = record_name
                    sonuc_dict = {
                        "df_x_final": st.session_state["df_x_final"].to_dict(orient="records"),
                        "df_y_final": st.session_state["df_y_final"].to_dict(orient="records")
                    }
                    sonuc_str = json.dumps(sonuc_dict, ensure_ascii=False, indent=2)
                    save_hesaplama(hesap_tipi, sonuc_str, st.session_state["username"], "goreli_kat_otelemesi")
                    st.success("Sonuç başarıyla kaydedildi!")
                else:
                    st.warning("Kayıt özelliğini kullanabilmek için lütfen giriş yapınız.")
        with col2:
            output = io.BytesIO()
            
            # DataFrame'lerin indekslerini sıfırlıyoruz
            df_x_final_reset = st.session_state["df_x_final"].reset_index(drop=True)
            df_y_final_reset = st.session_state["df_y_final"].reset_index(drop=True)
            
            # Araya boş sütun ekleyerek birleştiriyoruz
            empty_column = pd.DataFrame({"" : [""] * len(df_x_final_reset)})
            combined_df = pd.concat([df_x_final_reset, empty_column, df_y_final_reset], axis=1)
            
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                combined_df.to_excel(writer, index=False, sheet_name="Sonuçlar")
            
            output.seek(0)
            st.download_button(
                label="Sonuçları Excel Olarak İndir",
                data=output.getvalue(),
                file_name="Göreli Kat Ötelemesi Kontrolü.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    with tabs[1]:         
        st.markdown(r"""         
        ## Nasıl Çalışır?         
        - **ETABS Bağlantısı:** ETABS'in açık ve aktif olduğundan emin olun.         
        - **Yük Durumu Seçimi:** X ve Y yönü için yük durumlarını seçin.         
        - **Modal Seçimi:** Yapıya ait Modal'ı seçin.         
        - **Yapı Bilgileri:** Yapıya ait gerekli bilgileri girin.          
        - **Sonuç:** Gerekli seçimleri yaptıktan sonra **"Kontrol Et"** butonuna basın.         
        - **Kayıt:** Hesaplama sonuçlarını kaydedebilir veya Excel formatında indirebilirsiniz.                  

        ## TBDY 2018                  

        ### 4.9.1. Etkin Göreli Kat Ötelemelerinin Hesaplanması ve Sınırlandırılması                  

        #### 4.9.1.1         
        (X) deprem doğrultusunda herhangi bir kolon veya perde için, ardışık iki kat arasındaki yerdeğiştirme farkını ifade eden azaltılmış göreli kat ötelemesi, $\Delta_i^{(X)}$, DENK.(4.32) ile elde edilecektir.                  

        $$\Delta_i^{(X)} = u_i^{(X)} - u_{i-1}^{(X)}$$             **(4.32)**            

        DENK.(4.32)'de $u_i^{(X)}$ ve $u_{i-1}^{(X)}$, tipik (X) deprem doğrultusu için binanın i'inci ve (i-1)'inci katlarında herhangi bir kolon veya perdenin uçlarında azaltılmış deprem yükleri'ne göre hesaplanan yatay yerdeğiştirmeleri göstermektedir. Ancak bu hesapta 4.7.3.2'de verilen koşul ve ayrıca DENK.(4.19)'da tanımlanan minimum eşdeğer deprem yükü koşulu göz önüne alınmayacaktır.                  

        #### 4.9.1.2         
        Tipik (X) deprem doğrultusu için, binanın i'inci katındaki kolon veya perdeler için etkin göreli kat ötelemesi, $\delta_i^{(X)}$, DENK.(4.33) ile elde edilecektir.                  

        $$\delta_i^{(X)} = \frac{R}{\Gamma} \Delta_i^{(X)}$$                **(4.33)**                

        #### 4.9.1.3         
        Her bir deprem doğrultusu için, binanın herhangi bir i'inci katındaki kolon veya perdelerde, DENK.(4.33) ile hesaplanan $\delta_i^{(X)}$ etkin göreli kat ötelemesinin kat yüksekliği $h_i$'deki en büyük değeri $\delta_{i,\max}^{(X)}$ , aşağıda (a) veya (b)'de verilen koşulları sağlayacaktır.          

        (a) **Gevrek malzemeden yapılmış boşluklu veya boşluksuz dolgu duvarlarının ve cephe elemanlarının çerçeve elemanlarına, aralarında herhangi bir esnek derz veya bağlantı olmaksızın, tamamen bitişik olması durumunda:**          

        $$\frac{\delta_{i,\max}^{(X)}}{h_i} \leq 0.008 \, \kappa$$     **(4.34a)**         

        (b) **Gevrek malzemeden yapılmış dolgu duvarları ile çerçeve elemanlarının aralarında esnek derzler yapılmışı, cephe elemanlarının dış çerçevelere esnek bağlantılarla bağlanmışı veya dolgu duvar elemanının çerçeveden bağımsız olması durumunda:**          

        $$\frac{\delta_{i,\max}^{(X)}}{h_i} \leq 0.016 \, \kappa$$       **(4.34b)**       

        Ancak, bu durumda derzli dolgu duvar elemanlarının, esnek dolgu duvar elemanlarının ve esnek bağlantılı cephe elemanlarının düzlem içi yatay öteleme kapasitelerinin DENK.(4.34b)'de verilen sınır değeri sağladığı 1.4'e göre deneye dayalı olarak belgelendirilecektir. Dolgu duvarları için önemli bir esnek derz uygulaması EK 4C'de verilmiştir.          

        #### 4.9.1.4         
        DENK.(4.34)'te yer alan $\kappa$ katsayısı, binanın göz önüne alınan deprem doğrultusundaki hakim titreşim periyodu için 2.2'de tanımlanan DD-3 deprem yer hareketinin 2.3.4.1'e göre hesaplanan elastik tasarım spektral ivmesi'nin, DD-2 deprem yer hareketinin elastik tasarım spektral ivmesi'ne oranıdır. DENK.(4.34)'te yer alan $\kappa$ katsayısı ise betonarme binalarda $\kappa = 1$ , çelik binalarda $\kappa = 0.5$ alınacaktır.          

        #### 4.9.1.5         
        Deprem yüklerinin tamamının bağlantıları tersinir momentler aktarabilen çelik çerçevelerle taşındığı tek katlı binalarda, DENK.(4.34) ile tanımlanan sınırlar en çok %50 artırılabilir.          

        #### 4.9.1.6         
        DENK.(4.34)'de verilen koşulun binanın herhangi bir katında sağlanamaması durumunda, taşıyıcı sistemin rijitliği artırılmak ve deprem hesabı tekrarlanacaktır.         
        """)
