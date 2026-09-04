"""
STACONT Bridge Agent
--------------------
Kullanicinin yerel bilgisayarinda calisan, acik ETABS oturumuna baglanan
ve web uzerindeki STACONT platformuna guvenli HTTPS tuneli uzerinden veri sunan kopru servisi.

Calistirma: python bridge_agent.py
"""

import json
import os
import sys
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import pandas as pd

# Windows COM destegi
try:
    import comtypes.client
    import comtypes
    COMTYPES_AVAILABLE = True
except ImportError:
    COMTYPES_AVAILABLE = False

# Cloudflare Tunnel destegi
TUNNEL_URL = ""
try:
    from pycloudflared import try_cloudflare
    CLOUDFLARED_AVAILABLE = True
except ImportError:
    CLOUDFLARED_AVAILABLE = False

PORT = 8765
HOST = "127.0.0.1"

def start_tunnel_async():
    global TUNNEL_URL
    if CLOUDFLARED_AVAILABLE:
        try:
            print("[INFO] Cloudflare HTTPS Tuneli baslatiliyor...")
            t = try_cloudflare(port=PORT)
            if hasattr(t, 'tunnel') and t.tunnel:
                TUNNEL_URL = t.tunnel
                print(f"[OK] Genel Kopru Adresi (Tunnel): {TUNNEL_URL}")
        except Exception as e:
            print(f"[WARN] Tunel uyarisi: {e}")

def get_sap_model():
    """Aktif ETABS SapModel nesnesine baglanir."""
    if not COMTYPES_AVAILABLE:
        return None, "comtypes kutuphanesi yuklu degil."
    try:
        comtypes.CoInitialize()
        etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
        SapModel = etabs_object.SapModel
        SapModel.SetPresentUnits(6)  # kN-m
        return SapModel, None
    except Exception as e:
        return None, f"ETABS baglanti hatasi: {str(e)}"

def get_table_df(SapModel, table_name, group="All", combo=None, case=None):
    """ETABS DatabaseTables uzerinden tabloyu pandas DataFrame olarak ceker."""
    try:
        selection_list = []
        if combo:
            selection_list = [combo] if isinstance(combo, str) else list(combo)
        elif case:
            selection_list = [case] if isinstance(case, str) else list(case)

        if selection_list:
            SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay(selection_list)
            SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay(selection_list)
            SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay(selection_list)
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
        print(f"[WARN] Tablo cekme hatasi ({table_name}): {e}")
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
            print(f"[ERROR] Yanit gonderme hatasi: {e}")

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # 1. Health / Status Kontrolu
        if path in ["/", "/health", "/status", "/api/status"]:
            SapModel, err = get_sap_model()
            if SapModel is not None:
                try:
                    file_path = SapModel.GetModelFilename()
                    file_name = os.path.basename(file_path) if file_path else "Kaydedilmemis Model"
                    self._send_json({
                        "status": "ok",
                        "etabs_connected": True,
                        "model_name": file_name,
                        "model_path": file_path,
                        "tunnel_url": TUNNEL_URL,
                        "version": "1.0.0"
                    })
                except Exception as e:
                    self._send_json({
                        "status": "warning",
                        "etabs_connected": False,
                        "tunnel_url": TUNNEL_URL,
                        "error": str(e)
                    })
            else:
                self._send_json({
                    "status": "disconnected",
                    "etabs_connected": False,
                    "tunnel_url": TUNNEL_URL,
                    "error": err or "ETABS acik degil."
                })
            return

        # ETABS baglantisini al
        SapModel, err = get_sap_model()
        if SapModel is None:
            self._send_json({"success": False, "error": err or "ETABS baglanilamadi."}, status_code=503)
            return

        try:
            # 2. Yuk Kombinasyonlari ve Durumlari
            if path == "/api/combinations":
                ret_combos = SapModel.RespCombo.GetNameList()
                combos = list(ret_combos[1]) if ret_combos[0] > 0 else []
                ret_cases = SapModel.LoadCases.GetNameList()
                cases = list(ret_cases[1]) if ret_cases[0] > 0 else []
                all_combos = sorted(list(dict.fromkeys(combos + cases)))
                self._send_json({"success": True, "combinations": all_combos})

            # 3. Yuk Durumlari (Load Cases)
            elif path == "/api/load_cases":
                ret_cases = SapModel.LoadCases.GetNameList()
                cases = list(ret_cases[1]) if ret_cases[0] > 0 else []
                self._send_json({"success": True, "load_cases": cases})

            # 4. Kat Isimleri (Stories)
            elif path == "/api/stories":
                ret_stories = SapModel.Story.GetNameList()
                stories = list(ret_stories[1]) if ret_stories[0] > 0 else []
                self._send_json({"success": True, "stories": stories})

            # 5. Perde Kesme / Kapasite Paketi (Pier Bundle)
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

            # 6. Kolon Kapasite Paketi (Column Bundle) - Hizli Tekil Sorgu
            elif path == "/api/column_bundle":
                combo = query_params.get("combo", [""])[0]
                ts500_combo = query_params.get("ts500_combo", [""])[0]

                combos_to_query = [c for c in list(dict.fromkeys([combo, ts500_combo])) if c]
                df_raw = get_table_df(SapModel, 'Element Forces - Columns', combo=combos_to_query) if combos_to_query else pd.DataFrame()
                
                df_forces = pd.DataFrame()
                df_ts500 = pd.DataFrame()

                if not df_raw.empty and 'P' in df_raw.columns:
                    df_raw['P'] = pd.to_numeric(df_raw['P'], errors='coerce')
                    
                    if combo:
                        df_c = df_raw[df_raw['OutputCase'] == combo]
                        if not df_c.empty:
                            max_idx = df_c.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                            df_forces = df_c.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]
                            
                    if ts500_combo:
                        df_t = df_raw[df_raw['OutputCase'] == ts500_combo]
                        if not df_t.empty:
                            max_idx2 = df_t.groupby(['Story', 'Column'], sort=False)['P'].apply(lambda x: x.abs().idxmax())
                            df_ts500 = df_t.loc[max_idx2].sort_index().reset_index(drop=True)[['Story', 'Column', 'OutputCase', 'P']]

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
                self._send_json({
                    "success": True, 
                    "data": df.to_dict(orient="records"), 
                    "columns": list(df.columns)
                })

            else:
                self._send_json({"error": "Endpoint bulunamadi.", "path": path}, status_code=404)

        except Exception as e:
            self._send_json({"success": False, "error": f"Islem hatasi: {str(e)}"}, status_code=500)

def run_server():
    server_address = (HOST, PORT)
    httpd = ThreadingHTTPServer(server_address, BridgeRequestHandler)
    
    # Cloudflare HTTPS tünelini sunucu başlamadan önce hazırla
    start_tunnel_async()

    print("=" * 60)
    print("STACONT Bridge Agent Baslatildi!")
    print(f"Lokal Adres: http://{HOST}:{PORT}")
    if TUNNEL_URL:
        print(f"Bulut Tunel Adresi: {TUNNEL_URL}")
    print("STACONT web arayuzu acikken bu pencereyi acik tutun.")
    print("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nSTACONT Bridge durduruluyor...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
