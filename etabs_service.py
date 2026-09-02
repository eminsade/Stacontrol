"""
STACONT - ETABS Entegrasyon ve Veri Servisi
-------------------------------------------
Hem Web SaaS ortamında (STACONT Bridge HTTP API üzerinden)
hem de Yerel Masaüstü ortamında (Doğrudan COM API üzerinden)
şeffaf olarak veri çekmeyi sağlayan birleşik servis katmanı.
"""

import os
import urllib.request
import urllib.parse
import json
import pandas as pd
from constants import BRIDGE_URL

# Doğrudan COM desteği kontrolü (Lokal çalışma için)
try:
    import comtypes.client
    import comtypes
    COMTYPES_AVAILABLE = True
except ImportError:
    COMTYPES_AVAILABLE = False


def _fetch_from_bridge(endpoint: str, params: dict = None, timeout: float = 3.0):
    """Bridge yerel HTTP sunucusundan JSON veri çeker."""
    url = f"{BRIDGE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}"
    
    req = urllib.request.Request(url, headers={"User-Agent": "STACONT-Web"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if response.status == 200:
            content = response.read().decode('utf-8')
            return json.loads(content)
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
    """
    ETABS bağlantı durumunu kontrol eder.
    Öncelikle yerel Bridge Agent'ı (127.0.0.1:8765) dener,
    ulaşamazsa doğrudan COM bağlantısını dener.
    """
    # 1. Bridge Agent'ı Kontrol Et
    try:
        data = _fetch_from_bridge("/status", timeout=1.5)
        if data and data.get("etabs_connected"):
            return {
                "connected": True,
                "mode": "bridge",
                "model_name": data.get("model_name", "Aktif Model"),
                "model_path": data.get("model_path", ""),
                "message": f"Yerel Köprü (Bridge) üzerinden '{data.get('model_name')}' modeline bağlı."
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

    # 2. Doğrudan COM API'yi Kontrol Et
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
            return {"connected": False, "mode": "error", "message": str(e)}

    return {
        "connected": False,
        "mode": "disconnected",
        "model_name": "",
        "message": "ETABS veya STACONT Bridge bağlantısı bulunamadı."
    }


def get_load_combinations() -> list:
    """ETABS'teki yük kombinasyonlarının listesini döndürür."""
    # 1. Bridge'den dene
    try:
        resp = _fetch_from_bridge("/api/combinations", timeout=5.0)
        if resp and resp.get("success"):
            return resp.get("combinations", [])
    except Exception:
        pass

    # 2. Doğrudan COM'dan dene
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_combos = SapModel.RespCombo.GetNameList()
            return list(ret_combos[1]) if ret_combos[0] > 0 else []
        except Exception:
            return []

    return []


def get_load_cases() -> list:
    """ETABS'teki yük durumlarının listesini döndürür."""
    # 1. Bridge'den dene
    try:
        resp = _fetch_from_bridge("/api/load_cases", timeout=5.0)
        if resp and resp.get("success"):
            return resp.get("load_cases", [])
    except Exception:
        pass

    # 2. Doğrudan COM'dan dene
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret_cases = SapModel.LoadCases.GetNameList()
            return list(ret_cases[1]) if ret_cases[0] > 0 else []
        except Exception:
            return []

    return []


def get_pier_section_properties() -> pd.DataFrame:
    """Pier Section Properties tablosunu DataFrame olarak döndürür."""
    # 1. Bridge'den dene
    try:
        resp = _fetch_from_bridge("/api/pier_section_properties", timeout=10.0)
        if resp and resp.get("success") and resp.get("data"):
            return pd.DataFrame(resp.get("data"))
    except Exception:
        pass

    # 2. Doğrudan COM'dan dene
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Section Properties', [], 'All', 1, [], 0, [])
            if ret[2]:
                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                rows = [raw_data[i:i + num_cols] for i in range(0, len(raw_data), num_cols)]
                return pd.DataFrame(rows, columns=cols)
        except Exception:
            return None

    return None


def get_pier_forces_for_combination(combo: str) -> pd.DataFrame:
    """Belirtilen kombinasyon için maksimum mutlak V2 perde kesme kuvvetlerini döndürür."""
    # 1. Bridge'den dene
    try:
        resp = _fetch_from_bridge("/api/pier_forces", params={"combo": combo}, timeout=15.0)
        if resp and resp.get("success") and resp.get("data"):
            df = pd.DataFrame(resp.get("data"))
            df['V2'] = pd.to_numeric(df['V2'], errors='coerce')
            return df
    except Exception:
        pass

    # 2. Doğrudan COM'dan dene
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
            ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Forces', [], 'All', 1, [], 0, [])
            if ret[2]:
                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                rows = [raw_data[i:i + num_cols] for i in range(0, len(raw_data), num_cols)]
                df = pd.DataFrame(rows, columns=cols)
                df['V2'] = pd.to_numeric(df['V2'], errors='coerce')
                max_idx = df.groupby(['Story', 'Pier'])['V2'].apply(lambda x: x.abs().idxmax())
                return df.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Pier', 'OutputCase', 'V2']]
        except Exception:
            return None

    return None


def get_etabs_table(table_name: str, group: str = "All", combo: str = None, case: str = None) -> pd.DataFrame:
    """Herhangi bir ETABS tablosunu DataFrame olarak çeker."""
    # 1. Bridge'den dene
    try:
        params = {"name": table_name, "group": group}
        if combo:
            params["combo"] = combo
        if case:
            params["case"] = case
        resp = _fetch_from_bridge("/api/table", params=params, timeout=20.0)
        if resp and resp.get("success") and resp.get("data"):
            return pd.DataFrame(resp.get("data"))
    except Exception:
        pass

    # 2. Doğrudan COM'dan dene
    SapModel = get_active_sap_model()
    if SapModel is not None:
        try:
            if combo:
                SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            if case:
                SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([case])
            ret = SapModel.DatabaseTables.GetTableForDisplayArray(table_name, [], group, 1, [], 0, [])
            if ret[2]:
                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                rows = [raw_data[i:i + num_cols] for i in range(0, len(raw_data), num_cols)]
                return pd.DataFrame(rows, columns=cols)
        except Exception:
            return None

    return None
