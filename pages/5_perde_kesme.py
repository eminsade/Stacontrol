import os
import json
import streamlit as st
import pandas as pd
import numpy as np
from st_aggrid import AgGrid, GridUpdateMode, DataReturnMode

st.set_page_config(
    page_title="Betonarme Hesap Aracı",
    page_icon="🔨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from sidebar import setup_sidebar
from database import save_hesaplama, get_hesaplama_by_id
from utils import top_right_login, to_excel
from session_config import init_session_state
from constants import CONCRETE_OPTIONS, STEEL_OPTIONS, BOSLUK_OPTIONS, BV_OPTIONS
from bridge_client import render_bridge_status, render_bridge_fetcher
import etabs_service

# Sayfa konfigürasyonu
init_session_state()
setup_sidebar()
top_right_login()

st.title("Perde Kesme")
render_bridge_status(key="perde_kesme_status_widget")


def recalculate_single_row(row_dict: dict, calc_params: dict) -> dict:
    """
    Sadece tek bir satır için hesaplanmış sütunları yeniden hesaplar.
    """
    row = dict(row_dict)
    
    try:
        hw = float(row.get('HW', 0))
    except (ValueError, TypeError):
        hw = 0.0
        
    try:
        width = float(row.get('WidthBot', 0))
    except (ValueError, TypeError):
        width = 0.0
        
    try:
        thick = float(row.get('ThickBot', 0))
    except (ValueError, TypeError):
        thick = 0.0
        
    try:
        deprem_yuk = abs(float(row.get('Deprem Yük', 0)))
    except (ValueError, TypeError):
        deprem_yuk = 0.0
        
    try:
        kol = float(row.get('KOL', 2))
    except (ValueError, TypeError):
        kol = 2.0
        
    try:
        cap = float(row.get('ÇAP', 10))
    except (ValueError, TypeError):
        cap = 10.0
        
    try:
        aralik = float(row.get('ARALIK', 20))
    except (ValueError, TypeError):
        aralik = 20.0

    bs_str = str(row.get('Beton Sınıfı', calc_params.get('concrete_class', 'C25')))
    concrete_value = CONCRETE_OPTIONS.get(bs_str, calc_params.get('concrete_value', 25000))
    steel_value = calc_params.get('steel_value', 420000)
    bosluk_value = calc_params.get('bosluk_value', 0.85)
    bv_value = calc_params.get('bv_value', 1.0)
    Mp_Md = calc_params.get('Mp_Md', 0.0)
    
    hw_lw = (hw / width) if width > 0 else 0.0
    if hw_lw < 2.0:
        ve1 = abs(deprem_yuk * min(3.0 / (1.0 + hw_lw), 2.0))
    else:
        ve1 = abs(deprem_yuk * bv_value * Mp_Md)
        
    ve2 = deprem_yuk
    
    if 'VE1_min_allowed' in row:
        ve1 = max(ve1, float(row['VE1_min_allowed']))
    if 'VE2_min_allowed' in row:
        ve2 = max(ve2, float(row['VE2_min_allowed']))

    ve = min(ve1, ve2)
    
    # VR (Gövde ezilme sınırı)
    fck = concrete_value / 1000.0
    sqrt_fck = np.sqrt(fck) if fck >= 0 else 0.0
    vr = 1000.0 * bosluk_value * width * thick * sqrt_fck
    
    pct_ve_vr = f"{(ve / vr * 100.0):.1f}%" if vr > 0 else "0.0%"
    durum = "✅" if ve < vr else "❌"
    
    # Vrc (Beton kesme katkısı)
    fctk = 0.35 * np.sqrt(fck) if fck >= 0 else 0.0
    fctd = fctk / 1.5
    vrc = 0.65 * fctd * 1000.0 * width * thick
    
    # Vrw (Donatı kesme katkısı)
    ach = width * thick
    fyk = steel_value / 1000.0
    fywd = fyk / 1.15
    
    if aralik > 0 and thick > 0:
        as_val = kol * (np.pi * (cap / 2.0)**2) * (1000.0 / (aralik * 10.0))
        ach_1m = 1.0 * thick
        rho_sh = as_val / (ach_1m * 1e6)
        vrw = ach * rho_sh * fywd * 1000.0
    else:
        vrw = 0.0
        
    vrt = vrw + vrc
    pct_ve_vrt = f"{(ve / vrt * 100.0):.1f}%" if vrt > 0 else "0.0%"
    durum1 = "✅" if ve < vrt else "❌"
    
    row['VE1'] = round(ve1, 1)
    row['VE2'] = round(ve2, 1)
    row['VE'] = round(ve, 1)
    row['VR'] = round(vr, 1)
    row['Vrc'] = round(vrc, 1)
    row['%VE/VR'] = pct_ve_vr
    row['Durum'] = durum
    row['Vrw'] = round(vrw, 1)
    row['Vrt'] = round(vrt, 1)
    row['%VE/Vrt'] = pct_ve_vrt
    row['Durum1'] = durum1
    
    return row


def update_dataframe_row_by_row(new_df: pd.DataFrame, prev_df: pd.DataFrame, calc_params: dict) -> pd.DataFrame:
    """
    AgGrid'den dönen verileri önceki verilerle kıyaslar.
    Yalnızca girdileri değişen satırları hesaplar, değişmeyen satırların hesap değerlerini aynen korur.
    """
    if prev_df is None or prev_df.empty:
        res_list = []
        for _, r in new_df.iterrows():
            res_list.append(recalculate_single_row(r.to_dict(), calc_params))
        return pd.DataFrame(res_list)

    input_cols = ['WidthBot', 'ThickBot', 'Beton Sınıfı', 'Deprem Kombinasyonu', 'Deprem Yük', 'KOL', 'ÇAP', 'ARALIK']
    res_list = []

    for idx, new_row_series in new_df.iterrows():
        new_row = new_row_series.to_dict()
        if idx < len(prev_df):
            prev_row = prev_df.iloc[idx].to_dict()
            changed = False
            for col in input_cols:
                val_new = str(new_row.get(col, '')).strip()
                val_prev = str(prev_row.get(col, '')).strip()
                if val_new != val_prev:
                    changed = True
                    break
            if changed:
                res_row = recalculate_single_row(new_row, calc_params)
            else:
                res_row = new_row
                calc_cols = ['VE1', 'VE2', 'VE', 'VR', 'Vrc', '%VE/VR', 'Durum', 'Vrw', 'Vrt', '%VE/Vrt', 'Durum1']
                for c in calc_cols:
                    if c in prev_row:
                        res_row[c] = prev_row[c]
        else:
            res_row = recalculate_single_row(new_row, calc_params)

        res_list.append(res_row)

    return pd.DataFrame(res_list)


def build_grid_options(calc_params: dict) -> dict:
    c_val = calc_params.get("concrete_value", 25000)
    s_val = calc_params.get("steel_value", 420000)
    b_val = calc_params.get("bosluk_value", 0.85)
    bv_val = calc_params.get("bv_value", 1.0)
    mp_md_val = calc_params.get("Mp_Md", 0.0)

    mapping_str = ','.join([f"'{k}':{v}" for k, v in CONCRETE_OPTIONS.items()])

    return {
        "columnDefs": [
            {"headerName": "Kat", "field": "Story", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Perde", "field": "Pier", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "Yükseklik (m)", "field": "HW", "editable": False, "filter": "agSetColumnFilter", 
             "valueFormatter": "value.toFixed(1)"},
            {"headerName": "Uzunluk (m)", "field": "WidthBot", "editable": True, "filter": "agSetColumnFilter", 
             "valueFormatter": "value.toFixed(1)"},
            {"headerName": "Kalınlık (m)", "field": "ThickBot", "editable": True, "filter": "agSetColumnFilter", 
             "valueFormatter": "value.toFixed(1)"},
            {"headerName": "BS", "field": "Beton Sınıfı", "editable": True, "filter": "agSetColumnFilter",
             "cellEditor": "agSelectCellEditor", "cellEditorParams": {"values": list(CONCRETE_OPTIONS.keys())}},
            {"headerName": "Kombinasyon", "field": "Deprem Kombinasyonu", "editable": True, "filter": "agSetColumnFilter"},
            {"headerName": "VE1 (kN)", "field": "VE1", "editable": False, "filter": "agSetColumnFilter",
             "valueFormatter": "value.toFixed(1)",
             "valueGetter": f"""
                 var hw_lw = parseFloat(data.HW) / parseFloat(data.WidthBot || 1);
                 var deprem_yuk = Math.abs(parseFloat(data['Deprem Yük']) || 0);
                 return hw_lw < 2 ? deprem_yuk * Math.min(3 / (1 + hw_lw), 2) : deprem_yuk * {bv_val} * {mp_md_val};
             """},
            {"headerName": "VE2 (kN)", "field": "VE2", "editable": False, "filter": "agSetColumnFilter",
             "valueFormatter": "value.toFixed(1)",
             "valueGetter": "Math.abs(parseFloat(data['Deprem Yük']) || 0)"},
            {"headerName": "VE (kN)", "field": "VE", "editable": False, "filter": "agSetColumnFilter",
             "valueFormatter": "value.toFixed(1)",
             "valueGetter": "Math.min(data.VE1, data.VE2)"},
            {"headerName": "VR (kN)", "field": "VR", "editable": False, "filter": "agSetColumnFilter",
             "valueFormatter": "value.toFixed(1)",
             "valueGetter": f"""
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var sqrt_cv = Math.sqrt(cv / 1000);
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 return 1000 * {b_val} * width * thick * sqrt_cv;
             """},
            {"headerName": "%VE/VR", "field": "%VE/VR", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var sqrt_cv = Math.sqrt(cv / 1000);
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 var vr = 1000 * {b_val} * width * thick * sqrt_cv;
                 return (data.VE != null && vr != 0) ? ((data.VE / vr) * 100).toFixed(1) + '%' : '';
             """},
            {"headerName": "VE < VR", "field": "Durum", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var sqrt_cv = Math.sqrt(cv / 1000);
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 var vr = 1000 * {b_val} * width * thick * sqrt_cv;
                 return (data.VE != null && vr != 0) ? (data.VE < vr ? '✅' : '❌') : '';
             """},
            {"headerName": "KOL", "field": "KOL", "editable": True, "filter": "agSetColumnFilter",
             "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "ÇAP (mm)", "field": "ÇAP", "editable": True, "filter": "agSetColumnFilter",
             "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "ARALIK (cm)", "field": "ARALIK", "editable": True, "filter": "agSetColumnFilter",
             "enableFillHandle": True, "fillHandleDirection": "y"},
            {"headerName": "∑VR (kN)", "field": "Vrt", "editable": False, "filter": "agSetColumnFilter",
             "valueFormatter": "value.toFixed(1)",
             "valueGetter": f"""
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var fck = cv / 1000;
                 var fctk = 0.35 * Math.sqrt(fck);
                 var fctd = fctk / 1.5;
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 var vrc = 0.65 * fctd * 1000 * width * thick;

                 var ach = width * thick;
                 var fyk = {s_val} / 1000;
                 var fywd = fyk / 1.15;
                 var as = parseFloat(data.KOL || 0) * (Math.PI * Math.pow(parseFloat(data['ÇAP'] || 0) / 2, 2)) * (1000 / (parseFloat(data.ARALIK || 1) * 10));
                 var ach_1m = 1 * thick;
                 var rho_sh = as / (ach_1m * 1e6);
                 var vrw = ach * rho_sh * fywd * 1000;

                 return vrc + vrw;
             """},
            {"headerName": "%VE/∑VR", "field": "%VE/Vrt", "editable": False, "filter": "agSetColumnFilter",
             "valueGetter": f"""
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var fck = cv / 1000;
                 var fctk = 0.35 * Math.sqrt(fck);
                 var fctd = fctk / 1.5;
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 var vrc = 0.65 * fctd * 1000 * width * thick;
                 var ach = width * thick;
                 var fyk = {s_val} / 1000;
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
                 var mapping = {{ {mapping_str} }};
                 var cv = mapping[data['Beton Sınıfı']] || {c_val};
                 var fck = cv / 1000;
                 var fctk = 0.35 * Math.sqrt(fck);
                 var fctd = fctk / 1.5;
                 var width = parseFloat(data.WidthBot || 0);
                 var thick = parseFloat(data.ThickBot || 0);
                 var vrc = 0.65 * fctd * 1000 * width * thick;
                 var ach = width * thick;
                 var fyk = {s_val} / 1000;
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


tabs = st.tabs(["Hesaplama", "ℹ️"])

with tabs[0]:
    query_params = st.query_params
    saved_id = query_params.get("saved_id")

    # Kayıtlı Sonuç Gösterme
    if saved_id:
        username = st.session_state["username"]
        record = get_hesaplama_by_id(saved_id, username)
        if record is not None:
            st.subheader(f"Kayıt: {record['hesap_tipi']} - {record['hesap_tarihi']}")
            sonuc_dict = json.loads(record["sonuc"])
            loaded_df = pd.DataFrame(sonuc_dict["final_table"])

            selected_concrete = sonuc_dict.get("concrete_class", "C25")
            selected_steel = sonuc_dict.get("steel_class", "S420")
            main_deprem_combo = sonuc_dict.get("main_deprem_combo", "")
            selected_bosluk = sonuc_dict.get("bosluk_option", "Boşluksuz Perde: 0.85")
            bv_value = sonuc_dict.get("bv_value", 1.0)
            Mp_Md = sonuc_dict.get("Mp_Md", 0.0)
            is_sekil_712c = sonuc_dict.get("is_sekil_712c", False)
            is_basement = "basement_deprem_combo" in sonuc_dict
            basement_deprem_combo = sonuc_dict.get("basement_deprem_combo", "")
            basement_stories = sonuc_dict.get("basement_stories", [])

            concrete_value = CONCRETE_OPTIONS.get(selected_concrete, 25000)
            steel_value = STEEL_OPTIONS.get(selected_steel, 420000)
            bosluk_value = BOSLUK_OPTIONS.get(selected_bosluk, 0.85)

            saved_calc_params = {
                "concrete_class": selected_concrete,
                "steel_class": selected_steel,
                "concrete_value": concrete_value,
                "steel_value": steel_value,
                "bosluk_option": selected_bosluk,
                "bosluk_value": bosluk_value,
                "bv_value": bv_value,
                "Mp_Md": Mp_Md,
                "is_sekil_712c": is_sekil_712c
            }

            grid_options = build_grid_options(saved_calc_params)

            saved_key = f"saved_df_{saved_id}"
            if saved_key not in st.session_state:
                st.session_state[saved_key] = loaded_df

            grid_response = AgGrid(
                st.session_state[saved_key],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key=f"aggrid_saved_{saved_id}"
            )

            grid_df = pd.DataFrame(grid_response["data"])
            updated_df = update_dataframe_row_by_row(grid_df, st.session_state[saved_key], saved_calc_params)
            st.session_state[saved_key] = updated_df

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
        
        combo_names = st.session_state.get("etabs_combinations", [])
        if not combo_names:
            combo_names = etabs_service.get_load_combinations()
        if not combo_names:
            st.warning("⚠️ ETABS açık değil veya kombinasyonlar okunamadı. Lütfen STACONT Bridge'i çalıştırınız.")
            st.stop()

        col1, col2 = st.columns(2)
        with col1:
            main_deprem_combo = st.selectbox("Kombinasyon", combo_names, key="main_deprem_combo")
            is_basement = st.checkbox("YAPI BODRUMLU MU?")
            if is_basement:
                basement_deprem_combo = st.selectbox("Bodrum Kombinasyon", combo_names, key="basement_deprem_combo")
                story_options = st.session_state.get("etabs_stories", [])
                if not story_options:
                    story_options = etabs_service.get_story_names()
                basement_stories = st.multiselect("Bodrum Katlarını Seçiniz", story_options, key="basement_stories")
            
            selected_concrete = st.selectbox("Beton Sınıfı", list(CONCRETE_OPTIONS.keys()), key="concrete_class")
            concrete_value = CONCRETE_OPTIONS[selected_concrete]
            selected_steel = st.selectbox("Çelik Sınıfı", list(STEEL_OPTIONS.keys()), key="steel_class")
            steel_value = STEEL_OPTIONS[selected_steel]

        with col2:
            selected_bosluk = st.selectbox("Boşluklu/Boşluksuz", list(BOSLUK_OPTIONS.keys()), key="bosluk_class")
            bosluk_value = BOSLUK_OPTIONS[selected_bosluk]
            selected_bv = st.selectbox("Bv Değeri", list(BV_OPTIONS.keys()), key="bv_class")
            bv_value = BV_OPTIONS[selected_bv]
            Mp_Md = st.number_input("Mp/Md Değeri", value=0.0, format="%.1f")
            is_sekil_712c = st.checkbox("Kesme Kuvvetini Şekil 7.12c'ye Göre Artır")

        if st.button("Final Tabloyu Getir", key="btn_run_perde_kesme"):
            st.session_state["fetching_perde_kesme_active"] = True

        if st.session_state.get("fetching_perde_kesme_active"):
            bundle = None
            SapModel = etabs_service.get_active_sap_model()
            if SapModel:
                bundle = etabs_service.get_pier_bundle(main_deprem_combo)
            else:
                bundle = render_bridge_fetcher(
                    endpoint="/api/pier_bundle",
                    params={
                        "combo": main_deprem_combo,
                        "basement_combo": basement_deprem_combo if is_basement else ""
                    },
                    bundle_name="pier_bundle",
                    key="perde_kesme_fetcher_widget"
                )

            if bundle and isinstance(bundle, dict) and bundle.get("success"):
                st.session_state["fetching_perde_kesme_active"] = False
                df_deprem = pd.DataFrame(bundle.get("pier_forces", []))
                df_pier_section = pd.DataFrame(bundle.get("pier_section", []))
                df_bodrum = pd.DataFrame(bundle.get("basement_forces", []))

                if df_deprem.empty or df_pier_section.empty:
                    st.error(f"'{main_deprem_combo}' kombinasyonu için veri çekilemedi. Modelinizin çözülmüş olduğundan emin olun.")
                else:
                    main_table = df_deprem.rename(columns={'OutputCase': 'Deprem Kombinasyonu', 'V2': 'Deprem Yük'})
                    if is_basement and 'basement_stories' in locals() and basement_stories and not df_bodrum.empty:
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

                # Yükseklik hesapları
                df_pier_section[['CGTopZ', 'CGBotZ']] = df_pier_section[['CGTopZ', 'CGBotZ']].apply(pd.to_numeric, errors='coerce')
                pier_height_df = df_pier_section.groupby('Pier').agg({'CGTopZ': 'max', 'CGBotZ': 'min'})
                pier_height_df['HW'] = pier_height_df['CGTopZ'] - pier_height_df['CGBotZ']
                min_cgbotz_df = df_pier_section.groupby('Pier')['CGBotZ'].min().rename('MinCGBotZ')

                main_table["Beton Sınıfı"] = selected_concrete
                main_table = pd.merge(main_table, min_cgbotz_df, on='Pier', how='left')
                main_table['HW*'] = pd.to_numeric(main_table['CGTopZ'], errors='coerce') - main_table['MinCGBotZ']
                main_table = pd.merge(main_table, pier_height_df[['HW']], on='Pier', how='left')

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
                    
                    main_table['VE1_min_allowed'] = 0.0
                    main_table['VE2_min_allowed'] = 0.0
                    main_table.loc[mask, 'VE1_min_allowed'] = main_table.loc[mask, 'VE1_max'] / 2
                    main_table.loc[mask, 'VE2_min_allowed'] = main_table.loc[mask, 'VE2_max'] / 2
                    
                    main_table.loc[mask & (main_table['VE1_max'] / 2 > main_table['VE1']), 'VE1'] = main_table['VE1_max'] / 2
                    main_table.loc[mask & (main_table['VE2_max'] / 2 > main_table['VE2']), 'VE2'] = main_table['VE2_max'] / 2
                    main_table = main_table.drop(columns=['HW/3', 'VE1_max', 'VE2_max'])

                main_table['KOL'] = 2
                main_table['ÇAP'] = 10
                main_table['ARALIK'] = 20

                current_calc_params = {
                    "concrete_class": selected_concrete,
                    "steel_class": selected_steel,
                    "concrete_value": concrete_value,
                    "steel_value": steel_value,
                    "bosluk_option": selected_bosluk,
                    "bosluk_value": bosluk_value,
                    "bv_value": bv_value,
                    "Mp_Md": Mp_Md,
                    "is_sekil_712c": is_sekil_712c
                }
                st.session_state["calc_params"] = current_calc_params

                display_columns = ["Story", "Pier", "HW", "WidthBot", "ThickBot", "Beton Sınıfı", 
                                "Deprem Kombinasyonu", "Deprem Yük", "VE1", "VE2", "VE", "VR", "Vrc", 
                                "%VE/VR", "Durum", "KOL", "ÇAP", "ARALIK", "Vrw", "Vrt", "%VE/Vrt", "Durum1"]
                if 'VE1_min_allowed' in main_table.columns:
                    display_columns.extend(['VE1_min_allowed', 'VE2_min_allowed'])

                final_raw = main_table[display_columns]
                
                computed_rows = []
                for _, r in final_raw.iterrows():
                    computed_rows.append(recalculate_single_row(r.to_dict(), current_calc_params))
                
                final_table = pd.DataFrame(computed_rows)
                st.session_state["final_table"] = final_table
                st.rerun()

        if "final_table" in st.session_state:
            active_calc_params = st.session_state.get("calc_params", {
                "concrete_class": selected_concrete,
                "steel_class": selected_steel,
                "concrete_value": concrete_value,
                "steel_value": steel_value,
                "bosluk_option": selected_bosluk,
                "bosluk_value": bosluk_value,
                "bv_value": bv_value,
                "Mp_Md": Mp_Md,
                "is_sekil_712c": is_sekil_712c
            })

            grid_options = build_grid_options(active_calc_params)

            disp_df = st.session_state["final_table"].copy()
            visible_cols = [c for c in disp_df.columns if c not in ['VE1_min_allowed', 'VE2_min_allowed']]

            grid_response = AgGrid(
                disp_df[visible_cols],
                gridOptions=grid_options,
                update_mode=GridUpdateMode.VALUE_CHANGED | GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.AS_INPUT,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=True,
                key="aggrid_perde_kesme_main"
            )

            grid_df = pd.DataFrame(grid_response["data"])
            
            if 'VE1_min_allowed' in disp_df.columns:
                grid_df['VE1_min_allowed'] = disp_df['VE1_min_allowed'].values
            if 'VE2_min_allowed' in disp_df.columns:
                grid_df['VE2_min_allowed'] = disp_df['VE2_min_allowed'].values

            updated_df = update_dataframe_row_by_row(grid_df, st.session_state["final_table"], active_calc_params)
            st.session_state["final_table"] = updated_df

            st.divider()
            st.subheader("Sonuç Kaydetme")

            col1, col2 = st.columns([1, 1])

            with col1:
                record_name = st.text_input("Kayıt için bir isim giriniz:", value="Perde Kesme", key="record_name_input")
                kaydet_button = st.button("Sonucu Kaydet")
                
                if kaydet_button:
                    hesap_tipi = record_name
                    sonuc_dict = {
                        "final_table": updated_df[visible_cols].to_dict(orient="records"),
                        "concrete_class": active_calc_params.get("concrete_class", selected_concrete),
                        "steel_class": active_calc_params.get("steel_class", selected_steel),
                        "main_deprem_combo": main_deprem_combo,
                        "bosluk_option": active_calc_params.get("bosluk_option", selected_bosluk),
                        "bv_value": active_calc_params.get("bv_value", bv_value),
                        "Mp_Md": active_calc_params.get("Mp_Md", Mp_Md),
                        "is_sekil_712c": active_calc_params.get("is_sekil_712c", is_sekil_712c)
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
                    data=to_excel(updated_df[visible_cols]),
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

    $$ V_e = β_v \left( \frac{(M_p)_t}{(M_d)_t} \right) V_d $$ **(7.16)**
                

    Bu denklemde yer alan kesme kuvveti dinamik büyütme katsayısı $(Β_v = 1.5)$ alınacaktır. Ancak, deprem yükünün tamamının betonarme perdelerle taşındığı binalarda $(Β_v = 1.0)$ alınabilir. Daha kesin hesap yapılmadığı durumlarda burada $((M_p)_t \leq 1.25 (M_d)_t)$ kabul edilebilir. Düşey yükler ile Bölüm 4'e göre depremden hesaplanan kesme kuvvetinin 1.2D (boşluksuz perdeler) veya 1.4D (bağ kirişli perdeler) katı ile büyütülmesi ile elde edilen değerin, Denk.(7.16) ile hesaplanan $(V_e)$'den küçük olması durumunda, $(V_e)$ yerine bu kesme kuvveti kullanılacaktır.
                
   

    ### 7.6.7. Perdelerin Kesme Güvenliği

    #### 7.6.7.1 
    Perde kesitlerinin kesme dayanımı, $ V_r $, Denk.(7.17) ile hesaplanacaktır.

    $$
    V_r = A_{ch} (0.65 f_{ctd} + \rho_{sh} f_{ywd})
    $$

    7.6.7.3’te tanımlanan $ V_e $ tasarım kesme kuvveti Denk.(7.18)’de verilen koşulları sağlayacaktır:

    $$
    V_e \leq V_r
    $$

    $$
    V_e \leq 0.85 A_{ch} \sqrt{f_{ck}} \quad (\text{Boşluksuz perdeler})
    $$

    $$
    V_e \leq 0.65 A_{ch} \sqrt{f_{ck}} \quad (\text{Bağ kirişli perdeler})
    $$

    Aksi durumda, perde enine donatısı ve/veya perde kesit boyutları bu koşulları sağlamak üzere artırılacaktır.

    #### 7.6.7.2
    Temele bağlantı düzeyinde ve üst katlarda yapılacak yatay inşaat derzlerindeki düşey donatıya kesitte aktarılan kesme kuvveti gövdeyi oluşturan kesme bölgesinde yöntem ile kontrol edilecektir. Kesme sürtünmesi hesabında perde gövde ve bağlantı düşey donatısının tamamı $ A_v $ ve pürüzlendirilmiş yüzey ile betonun katkısı $ f_{ctd} $ ile çözümü alınacaktır. $ V_e $ sürtünme kesme kuvveti Denk.(7.19)’da verilen koşulları sağlayacaktır:
    
    $$
    V_e \leq f_{ctd} A_c + \mu A_v f_{yd}
    $$

    $$
    V_e \leq \min[0.2 f_{ck} A_c; \ (3.3 + 0.08 f_{ck}) A_c]
    $$

    
    **Şekil 7.12**
    """)
    
    img_path = os.path.join(os.path.dirname(__file__), "..", "assets", "7_12.png")
    if os.path.exists(img_path):
        st.image(img_path, caption="Şekil 7.12: Tasarım eğilme momenti ve kesme kuvveti diyagramları")