"""
STACONT Bridge Agent
--------------------
Kullanıcının yerel bilgisayarında arka planda çalışan, açık ETABS oturumuna
bağlanan ve web tarayıcısındaki STACONT uygulamasına veri aktaran yerel HTTP köprü servisi.

Çalıştırma: python bridge_agent.py
Varsayılan Port: 8765
"""

import json
import os
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import pandas as pd

# Windows COM desteği
try:
    import comtypes.client
    import comtypes
    COMTYPES_AVAILABLE = True
except ImportError:
    COMTYPES_AVAILABLE = False

PORT = 8765
HOST = "127.0.0.1"

def get_sap_model():
    """Aktif ETABS SapModel nesnesine bağlanır."""
    if not COMTYPES_AVAILABLE:
        return None, "comtypes kütüphanesi yüklü değil."
    try:
        comtypes.CoInitialize()
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        SapModel = etabs_object.SapModel
        SapModel.SetPresentUnits(6)  # kN-m
        return SapModel, None
    except Exception as e:
        return None, f"ETABS bağlantı hatası: {str(e)}"

def get_table_df(SapModel, table_name, group="All", combo=None, case=None):
    """ETABS DatabaseTables üzerinden tabloyu pandas DataFrame olarak çeker."""
    try:
        if combo:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo] if isinstance(combo, str) else combo)
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
        elif case:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([case] if isinstance(case, str) else case)
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
        else:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

        ret = SapModel.DatabaseTables.GetTableForDisplayArray(table_name, [], group, 1, [], 0, [])
        if not ret[2]:
            return pd.DataFrame()
        cols = [c.strip() for c in ret[2]]
        num_cols = len(cols)
        raw_data = ret[4]
        rows = [raw_data[i:i + num_cols] for i in range(0, len(raw_data), num_cols)]
        return pd.DataFrame(rows, columns=cols).apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    except Exception as e:
        print(f"Tablo çekme hatası ({table_name}): {e}")
        return pd.DataFrame()

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class BridgeRequestHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, data, status_code=200):
        try:
            response_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
            self.send_response(status_code)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_bytes)))
            self.end_headers()
            self.wfile.write(response_bytes)
        except Exception as e:
            print(f"Yanıt gönderme hatası: {e}")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. Health / Status Kontrolü
        if path in ["/", "/health", "/status", "/api/status"]:
            SapModel, err = get_sap_model()
            if SapModel is not None:
                try:
                    file_path = SapModel.GetModelFilename()
                    file_name = os.path.basename(file_path) if file_path else "Kaydedilmemiş Model"
                    self._send_json({
                        "status": "ok",
                        "etabs_connected": True,
                        "model_name": file_name,
                        "model_path": file_path,
                        "version": "1.0.0"
                    })
                except Exception as e:
                    self._send_json({
                        "status": "warning",
                        "etabs_connected": False,
                        "error": str(e)
                    })
            else:
                self._send_json({
                    "status": "disconnected",
                    "etabs_connected": False,
                    "error": err or "ETABS açık değil."
                })
            return

        # ETABS bağlantısını al
        SapModel, err = get_sap_model()
        if SapModel is None:
            self._send_json({"success": False, "error": err or "ETABS'e bağlanılamadı."}, status_code=503)
            return

        try:
            # 2. Yük Kombinasyonları
            if path == "/api/combinations":
                ret_combos = SapModel.RespCombo.GetNameList()
                combos = list(ret_combos[1]) if ret_combos[0] > 0 else []
                self._send_json({"success": True, "combinations": combos})

            # 3. Yük Durumları (Load Cases)
            elif path == "/api/load_cases":
                ret_cases = SapModel.LoadCases.GetNameList()
                cases = list(ret_cases[1]) if ret_cases[0] > 0 else []
                self._send_json({"success": True, "load_cases": cases})

            # 4. Perde Kesme / Kapasite Paketi (Pier Bundle)
            elif path == "/api/pier_bundle":
                combo = query_params.get("combo", [""])[0]
                df_props = get_table_df(SapModel, 'Pier Section Properties')
                df_forces = pd.DataFrame()
                if combo:
                    df_raw_forces = get_table_df(SapModel, 'Pier Forces', combo=combo)
                    if not df_raw_forces.empty and 'V2' in df_raw_forces.columns:
                        df_raw_forces['V2'] = pd.to_numeric(df_raw_forces['V2'], errors='coerce')
                        max_idx = df_raw_forces.groupby(['Story', 'Pier'])['V2'].apply(lambda x: x.abs().idxmax())
                        df_forces = df_raw_forces.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Pier', 'OutputCase', 'V2', 'P']]
                
                self._send_json({
                    "success": True,
                    "pier_section": df_props.to_dict(orient="records"),
                    "pier_forces": df_forces.to_dict(orient="records")
                })

            # 5. Kolon Kapasite Paketi (Column Bundle)
            elif path == "/api/column_bundle":
                combo = query_params.get("combo", [""])[0]
                ts500_combo = query_params.get("ts500_combo", [""])[0]

                df_forces = pd.DataFrame()
                if combo:
                    df_raw = get_table_df(SapModel, 'Element Forces - Columns', combo=combo)
                    if not df_raw.empty and 'P' in df_raw.columns:
                        df_raw['P'] = pd.to_numeric(df_raw['P'], errors='coerce')
                        max_idx = df_raw.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                        df_forces = df_raw.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]

                df_ts500 = pd.DataFrame()
                if ts500_combo:
                    df_raw_ts500 = get_table_df(SapModel, 'Element Forces - Columns', combo=ts500_combo)
                    if not df_raw_ts500.empty and 'P' in df_raw_ts500.columns:
                        df_raw_ts500['P'] = pd.to_numeric(df_raw_ts500['P'], errors='coerce')
                        max_idx2 = df_raw_ts500.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                        df_ts500 = df_raw_ts500.loc[max_idx2].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]

                df_assignments = get_table_df(SapModel, 'Frame Assignments - Section Properties')
                df_defs = get_table_df(SapModel, 'Frame Section Property Definitions - Summary')
                if df_defs.empty:
                    df_defs = get_table_df(SapModel, 'Frame Section Property Definitions - Concrete Rectangular')

                self._send_json({
                    "success": True,
                    "column_forces": df_forces.to_dict(orient="records"),
                    "ts500_forces": df_ts500.to_dict(orient="records"),
                    "frame_assignments": df_assignments.to_dict(orient="records"),
                    "section_definitions": df_defs.to_dict(orient="records")
                })

            # 6. Göreli Kat Ötelemesi Paketi (Drift Bundle)
            elif path == "/api/drift_bundle":
                case_x = query_params.get("case_x", [""])[0]
                case_y = query_params.get("case_y", [""])[0]
                
                df_drifts = pd.DataFrame()
                cases = [c for c in [case_x, case_y] if c]
                if cases:
                    df_drifts = get_table_df(SapModel, 'Story Drifts', case=cases)
                else:
                    df_drifts = get_table_df(SapModel, 'Story Drifts')

                df_modal = get_table_df(SapModel, 'Modal Participating Mass Ratios')

                self._send_json({
                    "success": True,
                    "story_drifts": df_drifts.to_dict(orient="records"),
                    "modal_ratios": df_modal.to_dict(orient="records")
                })

            # 7. Genel Tablo Sorgulama
            elif path == "/api/table":
                table_name = query_params.get("name", [""])[0]
                group_name = query_params.get("group", ["All"])[0]
                combo = query_params.get("combo", [""])[0]
                case = query_params.get("case", [""])[0]

                if not table_name:
                    self._send_json({"success": False, "error": "name parametresi gerekli."}, status_code=400)
                    return

                df = get_table_df(SapModel, table_name, group=group_name, combo=combo or None, case=case or None)
                self._send_json({"success": True, "data": df.to_dict(orient="records"), "columns": list(df.columns)})

            else:
                self._send_json({"error": "Endpoint bulunamadı.", "path": path}, status_code=404)

        except Exception as e:
            self._send_json({"success": False, "error": f"İşlem hatası: {str(e)}"}, status_code=500)

def run_server():
    server_address = (HOST, PORT)
    httpd = ThreadingHTTPServer(server_address, BridgeRequestHandler)
    print("=" * 60)
    print(f"🚀 STACONT Bridge Agent Başlatıldı!")
    print(f"📍 Adres: http://{HOST}:{PORT}")
    print(f"💡 STACONT web arayüzü açıkken bu pencereyi açık tutun.")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 STACONT Bridge durduruluyor...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
