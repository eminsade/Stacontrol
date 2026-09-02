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

            # 4. Pier Section Properties
            elif path == "/api/pier_section_properties":
                ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Section Properties', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    self._send_json({"success": False, "error": "Pier Section Properties tablosu boş veya alınamadı."})
                    return
                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                records = [dict(zip(cols, raw_data[i:i + num_cols])) for i in range(0, len(raw_data), num_cols)]
                self._send_json({"success": True, "data": records, "columns": cols})

            # 5. Pier Forces (Seçilen kombinasyon için maksimum V2)
            elif path == "/api/pier_forces":
                combo = query_params.get("combo", [""])[0]
                if not combo:
                    self._send_json({"success": False, "error": "combo parametresi gerekli."}, status_code=400)
                    return
                
                SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([])
                SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
                SapModel.DatabaseTables.SetLoadPatternsSelectedForDisplay([])
                ret = SapModel.DatabaseTables.GetTableForDisplayArray('Pier Forces', [], 'All', 1, [], 0, [])
                if not ret[2]:
                    self._send_json({"success": False, "error": f"Tablo verisi alınamadı: {combo}"})
                    return
                
                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                rows = [raw_data[i:i + num_cols] for i in range(0, len(raw_data), num_cols)]
                df = pd.DataFrame(rows, columns=cols)
                df['V2'] = pd.to_numeric(df['V2'], errors='coerce')
                max_idx = df.groupby(['Story', 'Pier'])['V2'].apply(lambda x: x.abs().idxmax())
                res_df = df.loc[max_idx].sort_index().reset_index(drop=True)[['Story', 'Pier', 'OutputCase', 'V2']]
                
                self._send_json({
                    "success": True, 
                    "data": res_df.to_dict(orient="records"),
                    "columns": list(res_df.columns)
                })

            # 6. Genel Tablo Sorgulama (Table by Name)
            elif path == "/api/table":
                table_name = query_params.get("name", [""])[0]
                group_name = query_params.get("group", ["All"])[0]
                combo = query_params.get("combo", [""])[0]
                case = query_params.get("case", [""])[0]

                if not table_name:
                    self._send_json({"success": False, "error": "name parametresi gerekli."}, status_code=400)
                    return

                if combo:
                    SapModel.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
                if case:
                    SapModel.DatabaseTables.SetLoadCasesSelectedForDisplay([case])

                ret = SapModel.DatabaseTables.GetTableForDisplayArray(table_name, [], group_name, 1, [], 0, [])
                if not ret[2]:
                    self._send_json({"success": False, "error": f"Tablo boş veya bulunamadı: {table_name}"})
                    return

                cols = [c.strip() for c in ret[2]]
                num_cols = len(cols)
                raw_data = ret[4]
                records = [dict(zip(cols, raw_data[i:i + num_cols])) for i in range(0, len(raw_data), num_cols)]
                self._send_json({"success": True, "data": records, "columns": cols})

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
