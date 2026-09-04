"""
STACONT - ETABS Entegrasyon ve Veri Servisi
-------------------------------------------
Hem Web SaaS ortamında (Cloudflare HTTPS Tüneli / Local Bridge üzerinden)
hem de Yerel Masaüstü ortamında (Doğrudan COM API üzerinden)
şeffaf olarak veri çekmeyi sağlayan birleşik servis katmanı.
"""

import os
import urllib.request
import urllib.parse
import json
import streamlit as st
import pandas as pd
from constants import BRIDGE_URL

# Doğrudan COM desteği kontrolü (Lokal çalışma için)
try:
    import comtypes.client
    import comtypes
    COMTYPES_AVAILABLE = True
except ImportError:
    COMTYPES_AVAILABLE = False


def _get_base_bridge_url() -> str:
    """Aktif köprü URL'sini döndürür (Query Param -> Session State -> Varsayılan)."""
    try:
        if "bridge" in st.query_params and st.query_params["bridge"]:
            return st.query_params["bridge"]
    except Exception:
        pass

    if "bridge_url" in st.session_state and st.session_state["bridge_url"]:
        return st.session_state["bridge_url"]

    return BRIDGE_URL


def _fetch_from_bridge(endpoint: str, params: dict = None, timeout: float = 30.0):
    """Bridge yerel HTTP sunucusundan veya HTTPS tünelinden JSON veri çeker."""
    base_url = _get_base_bridge_url()
    url = f"{base_url}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}"
    
    try:
        req = urllib.request.Request(
            url, 
            headers={
                "User-Agent": "STACONT-Web",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                content = response.read().decode('utf-8')
                return json.loads(content)
    except Exception as e:
        print(f"Bridge sorgu hatası ({url}): {e}")
    return None


def get_active_sap_model():
    """Doğrudan yerel COM SapModel nesnesine bağlanır (Lokal masaüstü modu)."""
    if not COMTYPES_AVAILABLE:
        return None
    try:
        comtypes.CoInitialize()
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        SapModel = etabs_object.SapModel
        SapModel.SetPresentUnits(6)  # kN-m
        return SapModel
    except Exception:
        return None


def check_etabs_status() -> dict:
    """ETABS bağlantı durumunu kontrol eder."""
    # 1. Doğrudan COM API'yi Kontrol Et
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            file_path = SapModel.GetModelFilename()
            file_name = os.path.basename(file_path) if file_path else "Kaydedilmemiş Model"
            return {
                "connected": True,
                "mode": "direct",
                "model_name": file_name,
                "model_path": file_path,
                "message": f"Doğrudan COM ile '{file_name}' modeline bağlı."
            }
        except Exception as e:
            pass

    # 2. Bridge Agent'ı Kontrol Et
    try:
        data = _fetch_from_bridge("/status", timeout=4.0)
        if data and data.get("etabs_connected"):
            return {
                "connected": True,
                "mode": "bridge",
                "model_name": data.get("model_name", "Aktif Model"),
                "model_path": data.get("model_path", ""),
                "tunnel_url": data.get("tunnel_url", ""),
                "message": f"Köprü üzerinden '{data.get('model_name')}' modeline bağlı."
            }
        elif data:
            return {
                "connected": False,
                "mode": "bridge_no_etabs",
                "model_name": "",
                "message": "STACONT Bridge çalışıyor ancak ETABS açık değil."
            }
    except Exception:
        pass

    return {
        "connected": False,
        "mode": "disconnected",
        "model_name": "",
        "message": "ETABS veya STACONT Bridge bağlantısı bulunamadı."
    }


def get_load_combinations() -> list:
    """ETABS'teki yük kombinasyonlarının listesini döndürür."""
    # 1. Session State
    if "etabs_combinations" in st.session_state and st.session_state["etabs_combinations"]:
        return st.session_state["etabs_combinations"]

    # 2. Doğrudan COM
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_combos = SapModel.RespCombo.GetNameList()
            combos = list(ret_combos[1]) if ret_combos[0] > 0 else []
            ret_cases = SapModel.LoadCases.GetNameList()
            cases = list(ret_cases[1]) if ret_cases[0] > 0 else []
            all_c = sorted(list(dict.fromkeys(combos + cases)))
            st.session_state["etabs_combinations"] = all_c
            return all_c
        except Exception:
            pass

    # 3. Bridge
    try:
        resp = _fetch_from_bridge("/api/combinations", timeout=6.0)
        if resp and resp.get("success"):
            combos = resp.get("combinations", [])
            st.session_state["etabs_combinations"] = combos
            return combos
    except Exception:
        pass

    return []


def get_load_cases() -> list:
    """ETABS'teki yük durumlarının listesini döndürür."""
    if "etabs_load_cases" in st.session_state and st.session_state["etabs_load_cases"]:
        return st.session_state["etabs_load_cases"]

    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_cases = SapModel.LoadCases.GetNameList()
            cases = list(ret_cases[1]) if ret_cases[0] > 0 else []
            st.session_state["etabs_load_cases"] = cases
            return cases
        except Exception:
            pass

    try:
        resp = _fetch_from_bridge("/api/load_cases", timeout=6.0)
        if resp and resp.get("success"):
            cases = resp.get("load_cases", [])
            st.session_state["etabs_load_cases"] = cases
            return cases
    except Exception:
        pass

    return []


def get_story_names() -> list:
    """Kat isimlerini döndürür."""
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_stories = SapModel.Story.GetNameList()
            return list(ret_stories[1]) if ret_stories[0] > 0 else []
        except Exception:
            pass

    try:
        resp = _fetch_from_bridge("/api/stories", timeout=6.0)
        if resp and resp.get("success"):
            return resp.get("stories", [])
    except Exception:
        pass

    return []


def get_column_bundle(combo: str, ts500_combo: str = "", basement_combo: str = "", basement_ts500_combo: str = "") -> dict:
    """Kolon kapasite hesabı için gerekli tüm tabloları tek seferde döndürür."""
    # 1. Doğrudan COM (Masaüstü Modu - En Hızlı)
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            def _get_forces(c):
                if not c:
                    return pd.DataFrame()
                SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([c])
                SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([c])
                SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
                ret = SapModel.DatabaseTables.GetTableForDisplayArray('Element Forces - Columns', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    return pd.DataFrame()
                cols = [col.strip() for col in ret[2]]
                raw = ret[4]
                rows = [raw[i:i + len(cols)] for i in range(0, len(raw), len(cols))]
                df = pd.DataFrame(rows, columns=cols).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
                df['P'] = pd.to_numeric(df['P'], errors='coerce')
                max_idx = df.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                return df.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]

            def _get_assign():
                ret = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Assignments - Section Properties', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    return pd.DataFrame()
                cols = [col.strip() for col in ret[2]]
                raw = ret[4]
                rows = [raw[i:i + len(cols)] for i in range(0, len(raw), len(cols))]
                df_a = pd.DataFrame(rows, columns=cols).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
                col_col = next((c for c in ['Column', 'FrameObjectName', 'Label', 'Frame'] if c in df_a.columns), None)
                if col_col and col_col != 'Column':
                    df_a['Column'] = df_a[col_col]
                if 'SectProp' not in df_a.columns and 'AutoSelect' in df_a.columns:
                    df_a['SectProp'] = df_a['AutoSelect']
                return df_a

            def _get_defs():
                ret = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Section Property Definitions - Summary', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    ret = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Section Property Definitions - Concrete Rectangular', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    return pd.DataFrame()
                cols = [col.strip() for col in ret[2]]
                raw = ret[4]
                rows = [raw[i:i + len(cols)] for i in range(0, len(raw), len(cols))]
                return pd.DataFrame(rows, columns=cols).apply(lambda x: x.str.strip() if x.dtype == "object" else x)

            return {
                "column_forces": _get_forces(combo),
                "ts500_forces": _get_forces(ts500_combo) if ts500_combo else pd.DataFrame(),
                "basement_column_forces": _get_forces(basement_combo) if basement_combo else pd.DataFrame(),
                "basement_ts500_forces": _get_forces(basement_ts500_combo) if basement_ts500_combo else pd.DataFrame(),
                "frame_assignments": _get_assign(),
                "section_definitions": _get_defs()
            }
        except Exception as e:
            print(f"COM kolon verisi hatası: {e}")

    # 2. Bridge (Web / Bulut Modu)
    try:
        resp = _fetch_from_bridge("/api/column_bundle", params={
            "combo": combo, 
            "ts500_combo": ts500_combo,
            "basement_combo": basement_combo,
            "basement_ts500_combo": basement_ts500_combo
        }, timeout=30.0)
        if resp and resp.get("success"):
            return {
                "column_forces": pd.DataFrame(resp.get("column_forces", [])),
                "ts500_forces": pd.DataFrame(resp.get("ts500_forces", [])),
                "basement_column_forces": pd.DataFrame(resp.get("basement_column_forces", [])),
                "basement_ts500_forces": pd.DataFrame(resp.get("basement_ts500_forces", [])),
                "frame_assignments": pd.DataFrame(resp.get("frame_assignments", [])),
                "section_definitions": pd.DataFrame(resp.get("section_definitions", []))
            }
    except Exception as e:
        print(f"Bridge kolon paketi hatası: {e}")

    return {
        "column_forces": pd.DataFrame(),
        "ts500_forces": pd.DataFrame(),
        "basement_column_forces": pd.DataFrame(),
        "basement_ts500_forces": pd.DataFrame(),
        "frame_assignments": pd.DataFrame(),
        "section_definitions": pd.DataFrame()
    }


def get_pier_bundle(combo: str, basement_combo: str = "") -> dict:
    """Perde hesabı için gerekli tabloları döndürür."""
    # 1. Doğrudan COM
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_p = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Section Properties', [], 'All', 1, [], 0, [])
            cols_p = [c.strip() for c in ret_p[2]] if ret_p[2] else []
            raw_p = ret_p[4] if ret_p[2] else []
            df_props = pd.DataFrame([raw_p[i:i + len(cols_p)] for i in range(0, len(raw_p), len(cols_p))], columns=cols_p) if cols_p else pd.DataFrame()

            def _get_pier_forces(c):
                if not c:
                    return pd.DataFrame()
                SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([c])
                SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([c])
                SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
                ret_f = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Forces', [], 'All', 1, [], 0, [])
                cols_f = [col.strip() for col in ret_f[2]] if ret_f[2] else []
                raw_f = ret_f[4] if ret_f[2] else []
                df_f = pd.DataFrame([raw_f[i:i + len(cols_f)] for i in range(0, len(raw_f), len(cols_f))], columns=cols_f) if cols_f else pd.DataFrame()
                if not df_f.empty and 'V2' in df_f.columns:
                    df_f['V2'] = pd.to_numeric(df_f['V2'], errors='coerce')
                    max_idx = df_f.groupby(['Story', 'Pier'])['V2'].apply(lambda x: x.abs().idxmax())
                    return df_f.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Pier', 'OutputCase', 'V2', 'P']]
                return pd.DataFrame()

            return {
                "pier_section": df_props,
                "pier_forces": _get_pier_forces(combo),
                "basement_forces": _get_pier_forces(basement_combo) if basement_combo else pd.DataFrame()
            }
        except Exception:
            pass

    # 2. Bridge
    try:
        resp = _fetch_from_bridge("/api/pier_bundle", params={"combo": combo, "basement_combo": basement_combo}, timeout=30.0)
        if resp and resp.get("success"):
            return {
                "pier_section": pd.DataFrame(resp.get("pier_section", [])),
                "pier_forces": pd.DataFrame(resp.get("pier_forces", [])),
                "basement_forces": pd.DataFrame(resp.get("basement_forces", []))
            }
    except Exception:
        pass

    return {"pier_section": pd.DataFrame(), "pier_forces": pd.DataFrame(), "basement_forces": pd.DataFrame()}


def get_beam_bundle(combo: str) -> dict:
    """Kiriş kesme hesabı için gerekli tabloları döndürür."""
    # 1. Doğrudan COM
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            ret_b = SapModel.DatabaseTables.GetTableForDisplayArray('Element Forces - Beams', [], 'All', 1, [], 0, [])
            cols_b = [col.strip() for col in ret_b[2]] if ret_b[2] else []
            raw_b = ret_b[4] if ret_b[2] else []
            df_b = pd.DataFrame([raw_b[i:i + len(cols_b)] for i in range(0, len(raw_b), len(cols_b))], columns=cols_b) if cols_b else pd.DataFrame()
            if not df_b.empty and 'V2' in df_b.columns:
                df_b['V2'] = pd.to_numeric(df_b['V2'], errors='coerce')
                max_idx = df_b.groupby(['Story', 'Beam'], sort=False)['V2'].apply(lambda x: x.abs().idxmax())
                df_b = df_b.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Beam', 'OutputCase', 'V2']]

            ret_a = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Assignments - Section Properties', [], 'All', 1, [], 0, [])
            cols_a = [col.strip() for col in ret_a[2]] if ret_a[2] else []
            raw_a = ret_a[4] if ret_a[2] else []
            df_a = pd.DataFrame([raw_a[i:i + len(cols_a)] for i in range(0, len(raw_a), len(cols_a))], columns=cols_a) if cols_a else pd.DataFrame()
            if not df_a.empty:
                beam_col = next((c for c in ['Beam', 'FrameObjectName', 'Label', 'Frame'] if c in df_a.columns), None)
                if beam_col and beam_col != 'Beam':
                    df_a['Beam'] = df_a[beam_col]
                if 'SectProp' not in df_a.columns and 'AutoSelect' in df_a.columns:
                    df_a['SectProp'] = df_a['AutoSelect']

            ret_d = SapModel.DatabaseTables.GetTableForDisplayArray('Frame Section Property Definitions - Concrete Rectangular', [], 'All', 1, [], 0, [])
            cols_d = [col.strip() for col in ret_d[2]] if ret_d[2] else []
            raw_d = ret_d[4] if ret_d[2] else []
            df_d = pd.DataFrame([raw_d[i:i + len(cols_d)] for i in range(0, len(raw_d), len(cols_d))], columns=cols_d) if cols_d else pd.DataFrame()

            return {
                "beam_forces": df_b,
                "frame_assignments": df_a,
                "section_definitions": df_d
            }
        except Exception:
            pass

    # 2. Bridge
    try:
        resp = _fetch_from_bridge("/api/beam_bundle", params={"combo": combo}, timeout=30.0)
        if resp and resp.get("success"):
            return {
                "beam_forces": pd.DataFrame(resp.get("beam_forces", [])),
                "frame_assignments": pd.DataFrame(resp.get("frame_assignments", [])),
                "section_definitions": pd.DataFrame(resp.get("section_definitions", []))
            }
    except Exception:
        pass

    return {"beam_forces": pd.DataFrame(), "frame_assignments": pd.DataFrame(), "section_definitions": pd.DataFrame()}


def get_drift_bundle(case_x: str, case_y: str) -> dict:
    """Göreli kat ötelemesi için gerekli tabloları döndürür."""
    # 1. Doğrudan COM
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            cases = [c for c in list(dict.fromkeys([case_x, case_y])) if c]
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay(cases)
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

            ret_d = SapModel.DatabaseTables.GetTableForDisplayArray('Story Drifts', [], 'All', 1, [], 0, [])
            cols_d = [col.strip() for col in ret_d[2]] if ret_d[2] else []
            raw_d = ret_d[4] if ret_d[2] else []
            df_d = pd.DataFrame([raw_d[i:i + len(cols_d)] for i in range(0, len(raw_d), len(cols_d))], columns=cols_d) if cols_d else pd.DataFrame()

            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            ret_m = SapModel.DatabaseTables.GetTableForDisplayArray('Modal Participating Mass Ratios', [], 'All', 1, [], 0, [])
            cols_m = [col.strip() for col in ret_m[2]] if ret_m[2] else []
            raw_m = ret_m[4] if ret_m[2] else []
            df_m = pd.DataFrame([raw_m[i:i + len(cols_m)] for i in range(0, len(raw_m), len(cols_m))], columns=cols_m) if cols_m else pd.DataFrame()

            return {"story_drifts": df_d, "modal_ratios": df_m}
        except Exception:
            pass

    # 2. Bridge
    try:
        resp = _fetch_from_bridge("/api/drift_bundle", params={"case_x": case_x, "case_y": case_y}, timeout=30.0)
        if resp and resp.get("success"):
            return {
                "story_drifts": pd.DataFrame(resp.get("story_drifts", [])),
                "modal_ratios": pd.DataFrame(resp.get("modal_ratios", []))
            }
    except Exception:
        pass

    return {"story_drifts": pd.DataFrame(), "modal_ratios": pd.DataFrame()}
