"""Stacontrol ETABS Ajani -- kullanicinin bilgisayarinda calisir.

Ne yapar
--------
Acik olan ETABS oturumuna COM ile baglanir ve Stacontrol web sitesinden gelen
**onceden tanimli** okuma isteklerini yerine getirir. Okudugu tabloyu siteye
gonderir; hesaplama sitede yapilir.

Guvenlik
--------
* Yalnizca **giden** (outbound) HTTPS baglantisi kurar. Bilgisayarinizda
  hicbir port acilmaz, disaridan baglanti kabul edilmez.
* Sunucudan gelen istekler sabit bir **beyaz listeye** (bkz. ``protocol.ALLOWED_OPS``)
  gore islenir. Liste disinda hicbir sey calistirilmaz; kod calistirma,
  dosya okuma/yazma, model degistirme yetenegi yoktur.
* Modeliniz uzerinde **degisiklik yapmaz**; yalnizca okur. Tek istisna,
  raporlama birimini ayarlayan ``SetPresentUnits`` cagrisidir.

Bagimliliklar: yalnizca standart kutuphane + ``comtypes``.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

try:
    # Dagitim duzeni: protocol.py agent.py ile ayni klasore kopyalanir
    # (bkz. tools/build_agent.py).
    import protocol
except ImportError:  # depo icinden calistirilirken
    from etabs_bridge import protocol

AGENT_VERSION = "1.0.0"
HERE = Path(__file__).resolve().parent

# Kurulum paketine gomulen varsayilan adres; agent_config.json ile degistirilebilir.
DEFAULT_BRIDGE_URL = "https://stacontrol.com/bridge"

_ETABS_PROGIDS = (
    "CSI.ETABS.API.ETABSObject",   # ETABS 18+
    "CSI.ETABS2016.API.ETABSObject",
    "ETABS2015.API.ETABSObject",
)


# ---------------------------------------------------------------------------
# Konsol yardimcilari (ASCII -- Windows konsol kod sayfasi sorun cikarmasin)
# ---------------------------------------------------------------------------

def say(message: str = "") -> None:
    print(message, flush=True)


def banner(lines: list[str]) -> None:
    width = max(len(line) for line in lines) + 4
    say("+" + "-" * width + "+")
    for line in lines:
        say("| " + line.ljust(width - 2) + " |")
    say("+" + "-" * width + "+")


def stamp() -> str:
    return time.strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Yapilandirma
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    cfg: dict[str, Any] = {"bridge_url": DEFAULT_BRIDGE_URL, "verify_tls": True}
    path = HERE / "agent_config.json"
    if path.exists():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            say(f"[!] agent_config.json okunamadi ({exc}); varsayilanlar kullaniliyor.")
    env_url = os.environ.get("STACONTROL_BRIDGE_URL")
    if env_url:
        cfg["bridge_url"] = env_url
    cfg["bridge_url"] = str(cfg["bridge_url"]).rstrip("/")
    return cfg


# ---------------------------------------------------------------------------
# ETABS baglantisi
# ---------------------------------------------------------------------------

class EtabsSession:
    """Acik ETABS oturumuna baglanir; kopan baglantiyi kendi kendine tazeler."""

    def __init__(self) -> None:
        self._sap = None
        self._initialised = False

    def _ensure_com(self) -> None:
        if not self._initialised:
            import comtypes

            comtypes.CoInitialize()
            self._initialised = True

    def _attach(self):
        import comtypes.client

        last_error: Optional[Exception] = None
        for prog_id in _ETABS_PROGIDS:
            try:
                etabs_object = comtypes.client.GetActiveObject(prog_id)
                return etabs_object.SapModel
            except Exception as exc:  # sonraki ProgID'yi dene
                last_error = exc
        raise RuntimeError(
            "Acik bir ETABS bulunamadi. ETABS'i acip modelinizi yukleyin, "
            "sonra tekrar deneyin."
        ) from last_error

    def model(self):
        """Gecerli ``SapModel`` nesnesini dondurur."""
        self._ensure_com()
        if self._sap is not None:
            try:
                self._sap.GetModelFilename()   # canlilik testi
                return self._sap
            except Exception:
                self._sap = None               # ETABS kapanmis/yeniden acilmis
        self._sap = self._attach()
        return self._sap

    def model_filename(self) -> Optional[str]:
        try:
            return self.model().GetModelFilename() or ""
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Islem uygulayicilar (beyaz liste)
# ---------------------------------------------------------------------------

def _apply_display_selection(sap, args: dict[str, Any]) -> None:
    """Tablo okumadan hemen once yuk secimini uygular.

    Secim ve okuma tek is icinde yapildigi icin araya baska bir istek giremez;
    yanlis kombinasyonun tablosunun okunmasi mumkun degildir.
    """
    sap.DatabaseTables.SetLoadCasesSelectedForDisplay(list(args.get("cases") or []))
    sap.DatabaseTables.SetLoadCombinationsSelectedForDisplay(list(args.get("combos") or []))
    sap.DatabaseTables.SetLoadPatternsSelectedForDisplay(list(args.get("patterns") or []))


def op_ping(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_version": AGENT_VERSION,
        "model_file": sap_session.model_filename(),
        "time": time.time(),
    }


def op_get_model_filename(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    return {"filename": sap_session.model().GetModelFilename() or ""}


def op_set_present_units(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    units = int(args.get("units", 6))
    ret = sap_session.model().SetPresentUnits(units)
    return {"ret": int(ret) if isinstance(ret, int) else 0}


def op_get_combo_name_list(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    ret = sap_session.model().RespCombo.GetNameList()
    return {"names": list(ret[1] or [])}


def op_get_load_case_name_list(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    ret = sap_session.model().LoadCases.GetNameList()
    return {"names": list(ret[1] or [])}


def op_set_cases(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    sap_session.model().DatabaseTables.SetLoadCasesSelectedForDisplay(
        list(args.get("names") or [])
    )
    return {"ok": True}


def op_set_combos(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    sap_session.model().DatabaseTables.SetLoadCombinationsSelectedForDisplay(
        list(args.get("names") or [])
    )
    return {"ok": True}


def op_set_patterns(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    sap_session.model().DatabaseTables.SetLoadPatternsSelectedForDisplay(
        list(args.get("names") or [])
    )
    return {"ok": True}


def op_get_available_tables(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    ret = sap_session.model().DatabaseTables.GetAvailableTables()
    return {
        "table_keys": list(ret[1] or []),
        "import_types": list(ret[2] or []),
        "is_empty": list(ret[3] or []),
    }


def op_get_table(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    sap = sap_session.model()
    _apply_display_selection(sap, args)

    table_key = str(args["table_key"])
    field_key_list = list(args.get("field_key_list") or [])
    group_name = str(args.get("group_name") or "All")
    table_version = int(args.get("table_version") or 1)

    ret = sap.DatabaseTables.GetTableForDisplayArray(
        table_key, field_key_list, group_name, table_version, [], 0, []
    )

    columns = list(ret[2] or [])
    data = list(ret[4] or [])
    if not columns:
        raise RuntimeError(
            f"'{table_key}' tablosu bos dondu. Analiz calistirilmamis olabilir "
            "ya da bu tablo modelde bulunmuyor."
        )
    return {
        "field_key_list": list(ret[0] or []),
        "table_version": int(ret[1] or table_version),
        "columns": columns,
        "number_records": int(ret[3] or 0),
        "data": data,
        "ret": int(ret[5] or 0) if len(ret) > 5 else 0,
    }


def op_get_weight_and_mass(sap_session: EtabsSession, args: dict[str, Any]) -> dict[str, Any]:
    ret = sap_session.model().PropMaterial.GetWeightAndMass(str(args["name"]))
    return {"weight_per_volume": float(ret[0]), "mass_per_volume": float(ret[1])}


HANDLERS = {
    protocol.OP_PING: op_ping,
    protocol.OP_GET_MODEL_FILENAME: op_get_model_filename,
    protocol.OP_SET_PRESENT_UNITS: op_set_present_units,
    protocol.OP_GET_COMBO_NAME_LIST: op_get_combo_name_list,
    protocol.OP_GET_LOAD_CASE_NAME_LIST: op_get_load_case_name_list,
    protocol.OP_SET_CASES_FOR_DISPLAY: op_set_cases,
    protocol.OP_SET_COMBOS_FOR_DISPLAY: op_set_combos,
    protocol.OP_SET_PATTERNS_FOR_DISPLAY: op_set_patterns,
    protocol.OP_GET_TABLE: op_get_table,
    protocol.OP_GET_AVAILABLE_TABLES: op_get_available_tables,
    protocol.OP_GET_WEIGHT_AND_MASS: op_get_weight_and_mass,
}


# ---------------------------------------------------------------------------
# Kopru istemcisi (yalnizca urllib)
# ---------------------------------------------------------------------------

def _lower_headers(headers) -> dict[str, str]:
    """HTTP basliklarini kucuk harfli bir sozluge cevirir."""
    if not headers:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


class BridgeClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session_id = ""
        self.token = ""

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[bytes] = None,
        headers: Optional[dict[str, str]] = None,
        timeout: int = 40,
    ) -> tuple[int, bytes, dict[str, str]]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("User-Agent", f"StacontrolAgent/{AGENT_VERSION}")
        if self.session_id:
            req.add_header("X-Session-Id", self.session_id)
            req.add_header("X-Agent-Token", self.token)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        # HTTP baslik adlari buyuk/kucuk harf duyarsizdir ve sunucu (uvicorn)
        # bunlari kucuk harfle gonderir. Anahtarlari kucuk harfe indirgeyip
        # oyle okuyoruz; aksi halde "X-Job-Id" aramasi bosa duser ve is
        # kimliksiz kalir.
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read(), _lower_headers(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), _lower_headers(exc.headers)

    def register(self) -> dict[str, Any]:
        body = json.dumps(
            {
                "hostname": socket.gethostname(),
                "agent_version": AGENT_VERSION,
                "os": platform.platform(),
            }
        ).encode("utf-8")
        status, payload, _ = self._request(
            "POST", "/api/agent/register", body, {"Content-Type": "application/json"}
        )
        if status != 200:
            raise RuntimeError(f"Kayit basarisiz (HTTP {status}): {payload[:200]!r}")
        data = json.loads(payload.decode("utf-8"))
        self.session_id = data["session_id"]
        self.token = data["token"]
        return data

    def poll(self) -> Optional[dict[str, Any]]:
        status, payload, headers = self._request(
            "GET", "/api/agent/poll", timeout=protocol.AGENT_POLL_SECONDS + 15
        )
        if status == 204:
            return {"paired": headers.get("x-paired") == "1", "job": None}
        if status == 401:
            raise PermissionError("Oturum gecersiz")
        if status != 200:
            raise RuntimeError(f"Yoklama hatasi HTTP {status}")

        job_id = headers.get("x-job-id", "")
        if not job_id:
            raise RuntimeError("Sunucu is kimligi gondermedi (x-job-id bos)")
        return {
            "paired": headers.get("x-paired") == "1",
            "job": {
                "job_id": job_id,
                "op": headers.get("x-job-op", ""),
                "payload": payload,
            },
        }

    def send_result(self, job_id: str, status_text: str, payload: Any) -> None:
        """Sonucu sunucuya birakir.

        Basarisiz gonderimi sessizce yutmayiz: web tarafi bosuna bekler ve
        kullanici sebebini goremez.
        """
        blob = protocol.encode(payload)
        status, body, _ = self._request(
            "POST",
            f"/api/agent/result/{job_id}",
            blob,
            {
                "Content-Type": "application/octet-stream",
                protocol.STATUS_HEADER: status_text,
            },
            timeout=120,
        )
        if status != 200:
            raise RuntimeError(f"Sonuc gonderilemedi (HTTP {status}): {body[:200]!r}")

    def report_state(self, model_file: Optional[str]) -> None:
        body = json.dumps({"model_file": model_file or ""}).encode("utf-8")
        self._request(
            "POST", "/api/agent/state", body, {"Content-Type": "application/json"}
        )


# ---------------------------------------------------------------------------
# Ana dongu
# ---------------------------------------------------------------------------

def run_job(sap_session: EtabsSession, client: BridgeClient, job: dict[str, Any]) -> None:
    job_id = job["job_id"]
    try:
        request = protocol.decode(job["payload"]) or {}
        op = request.get("op", "")
        args = request.get("args") or {}
    except Exception as exc:
        client.send_result(job_id, protocol.STATUS_ERROR, {"message": f"Istek cozulemedi: {exc}"})
        return

    if op not in protocol.ALLOWED_OPS or op not in HANDLERS:
        say(f"[{stamp()}] REDDEDILDI: bilinmeyen islem '{op}'")
        client.send_result(
            job_id, protocol.STATUS_ERROR, {"message": f"Desteklenmeyen islem: {op}"}
        )
        return

    label = args.get("table_key") or op
    started = time.time()
    try:
        result = HANDLERS[op](sap_session, args)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        say(f"[{stamp()}] HATA {label}: {message}")
        _send(client, job_id, protocol.STATUS_ERROR, {"message": message})
        return

    if _send(client, job_id, protocol.STATUS_OK, result):
        columns = result.get("columns") or []
        rows = len(result.get("data", [])) // len(columns) if columns else 0
        extra = f" ({rows} satir)" if op == protocol.OP_GET_TABLE else ""
        say(f"[{stamp()}] OK   {label}{extra} - {time.time() - started:.1f} sn")


def _send(client: BridgeClient, job_id: str, status_text: str, payload: Any) -> bool:
    """Sonucu gonderir; basarisizlik ajani dusurmez, sadece raporlanir."""
    try:
        client.send_result(job_id, status_text, payload)
        return True
    except Exception as exc:
        say(f"[{stamp()}] Sonuc gonderilemedi: {exc}")
        return False


def main() -> int:
    cfg = load_config()
    client = BridgeClient(cfg["bridge_url"])
    sap_session = EtabsSession()

    say()
    banner(
        [
            "STACONTROL - ETABS AJANI",
            f"surum {AGENT_VERSION}",
            "",
            "Bu pencereyi ACIK BIRAKIN.",
            "Kapatirsaniz site ETABS'e ulasamaz.",
        ]
    )
    say()
    say(f"Sunucu : {cfg['bridge_url']}")

    model_file = sap_session.model_filename()
    if model_file:
        say(f"ETABS  : {os.path.basename(model_file)}")
    else:
        say("ETABS  : su an acik degil (model acinca otomatik baglanir)")
    say()

    # -- kayit ve eslestirme ---------------------------------------------
    try:
        info = client.register()
    except Exception as exc:
        say(f"[!] Sunucuya baglanilamadi: {exc}")
        say("    Internet baglantinizi ve guvenlik duvari ayarlarinizi kontrol edin.")
        input("\nCikmak icin Enter'a basin...")
        return 1

    code = info["pairing_code"]
    say()
    banner(["ESLESTIRME KODUNUZ", "", f"      {code}      ", "",
            "Bu kodu sitedeki 'ETABS Baglantisi'", "sayfasina girin."])
    say(f"\nKodun gecerlilik suresi: {info['expires_in'] // 60} dakika")
    say("Eslestirme bekleniyor...\n")

    paired = False
    idle_since = time.time()
    last_state_report = 0.0
    backoff = 1.0

    while True:
        try:
            poll = client.poll()
            backoff = 1.0

            if poll["paired"] and not paired:
                paired = True
                say(f"[{stamp()}] Eslestirme tamamlandi. Site artik ETABS'e erisebilir.")
                say("            Bu pencereyi acik birakin.\n")

            job = poll.get("job")
            if job:
                idle_since = time.time()
                run_job(sap_session, client, job)
            elif not paired and (time.time() - idle_since) > info["expires_in"]:
                say("[!] Kodun suresi doldu. Ajani kapatip yeniden baslatin.")
                input("\nCikmak icin Enter'a basin...")
                return 1

            # Acik model adini periyodik bildir (sitede gosterilir)
            if paired and (time.time() - last_state_report) > 30:
                last_state_report = time.time()
                try:
                    client.report_state(sap_session.model_filename())
                except Exception:
                    pass

        except PermissionError:
            say(f"[{stamp()}] Oturum dustu, yeniden kayit olunuyor...")
            try:
                info = client.register()
                paired = False
                say()
                banner(["YENI ESLESTIRME KODU", "", f"      {info['pairing_code']}      "])
                say()
            except Exception as exc:
                say(f"[!] Yeniden kayit basarisiz: {exc}")
                time.sleep(10)

        except KeyboardInterrupt:
            say("\nAjan kapatiliyor. Iyi calismalar!")
            return 0

        except Exception as exc:
            say(f"[{stamp()}] Baglanti sorunu: {exc} ({backoff:.0f} sn sonra tekrar)")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:  # pragma: no cover - beklenmeyen cokme
        traceback.print_exc()
        input("\nBeklenmeyen hata. Cikmak icin Enter'a basin...")
        raise SystemExit(1)
