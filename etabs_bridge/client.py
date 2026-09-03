"""Streamlit tarafinin kullandigi uzak ETABS istemcisi.

Buradaki ``RemoteSapModel``, ``comtypes`` ile alinan gercek ``SapModel``
nesnesinin **kullandigimiz alt kumesini birebir taklit eder**: ayni metot
adlari, ayni argumanlar ve en onemlisi ayni donus demeti (tuple) duzeni.

Bu sayede sayfalardaki 4000 satirlik hesap kodu hic degismez; yalnizca
baglanti satiri degisir::

    # onceki (yalnizca ayni makinede calisir)
    etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    SapModel = etabs_object.SapModel

    # simdi (kullanicinin bilgisayarindaki ajan uzerinden)
    SapModel = connect_etabs()

Onemli iki tasarim karari
-------------------------
1. ``Set...SelectedForDisplay`` cagrilari **aga gonderilmez**. Yerelde
   biriktirilir ve ilk ``GetTableForDisplayArray`` cagrisinda tablo istegiyle
   birlikte tek pakette gonderilir. Boylece hem gidis-donus sayisi yariya iner
   hem de "once kombinasyonu sec, sonra tabloyu oku" ikilisi bolunmez bir islem
   haline gelir -- iki sekme ayni ajani kullansa bile yanlis kombinasyonun
   tablosu okunamaz.
2. Okunan tablolar kisa sureli onbellege alinir. Streamlit her etkilesimde
   sayfayi bastan calistirdigi icin bu olmadan her tiklamada model yeniden
   okunurdu. Onbellegin yasi arayuzde gosterilir ve elle yenilenebilir.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import requests

from . import protocol
from .protocol import (
    AgentBusyError,
    AgentOfflineError,
    AgentTimeoutError,
    BridgeError,
    EtabsError,
)

#: Okunan tablolarin onbellekte kalma suresi (saniye).
DEFAULT_CACHE_TTL = 300


class BridgeTransport:
    """Kopru API'si ile konusan ince HTTP katmani."""

    def __init__(self, base_url: str, internal_key: str, timeout: int = 620) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"X-Internal-Key": internal_key}
        self._timeout = timeout
        self._session = requests.Session()

    # -- durum -----------------------------------------------------------
    def status(self, username: str) -> dict[str, Any]:
        resp = self._session.get(
            f"{self.base_url}/api/web/status",
            params={"username": username},
            headers=self._headers,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def pair(self, username: str, code: str) -> dict[str, Any]:
        resp = self._session.post(
            f"{self.base_url}/api/web/pair",
            json={"username": username, "code": code},
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 404:
            raise BridgeError("Kod gecersiz, suresi dolmus veya baska bir hesaba baglanmis.")
        resp.raise_for_status()
        return resp.json()

    def disconnect(self, username: str) -> None:
        self._session.post(
            f"{self.base_url}/api/web/disconnect",
            json={"username": username},
            headers=self._headers,
            timeout=15,
        )

    def release(self, username: str, client_id: str) -> None:
        try:
            self._session.post(
                f"{self.base_url}/api/web/release",
                json={"username": username, "client_id": client_id},
                headers=self._headers,
                timeout=10,
            )
        except requests.RequestException:
            pass  # kira zaten zaman asimiyla duser

    # -- islem cagrisi ---------------------------------------------------
    def call(
        self,
        username: str,
        client_id: str,
        op: str,
        args: dict[str, Any],
        timeout: int = protocol.DEFAULT_CALL_TIMEOUT,
    ) -> Any:
        try:
            resp = self._session.post(
                f"{self.base_url}/api/web/call",
                json={
                    "username": username,
                    "client_id": client_id,
                    "op": op,
                    "args": args,
                    "timeout": timeout,
                },
                headers=self._headers,
                timeout=timeout + 20,
            )
        except requests.Timeout as exc:
            raise AgentTimeoutError(
                "Ajan zamaninda yanit vermedi. Model cok buyuk olabilir ya da "
                "ETABS mesgul."
            ) from exc
        except requests.RequestException as exc:
            raise BridgeError(f"Kopru sunucusuna ulasilamadi: {exc}") from exc

        if resp.status_code == 409:
            raise AgentOfflineError(
                "Bilgisayarinizdaki ETABS ajani calismiyor. Ajani baslatip tekrar deneyin."
            )
        if resp.status_code == 423:
            raise AgentBusyError(
                "Ajan baska bir sekme tarafindan kullaniliyor. Diger sekmedeki islem "
                "bitince tekrar deneyin."
            )
        if resp.status_code == 504:
            raise AgentTimeoutError("Ajan zamaninda yanit vermedi.")
        if resp.status_code == 401:
            raise BridgeError("Kopru ic anahtari gecersiz (sunucu yapilandirmasi).")
        resp.raise_for_status()

        payload = protocol.decode(resp.content)
        if resp.headers.get(protocol.STATUS_HEADER) != protocol.STATUS_OK:
            message = (payload or {}).get("message", "Bilinmeyen ajan hatasi")
            raise EtabsError(message)
        return payload


@dataclass
class _DisplaySelection:
    """ETABS'in 'goruntulenecek yuk secimi' durumunun yerel kopyasi."""

    cases: list[str] = field(default_factory=list)
    combos: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)

    def key(self) -> str:
        return json.dumps(
            [sorted(self.cases), sorted(self.combos), sorted(self.patterns)],
            ensure_ascii=False,
        )


def _as_list(value: Any) -> list[str]:
    """COM cagrilarina gecen ``None``/tuple/list degerlerini normallestirir."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(v) for v in value]
    return [str(value)]


class _DatabaseTables:
    """``SapModel.DatabaseTables`` karsiligi."""

    def __init__(self, model: "RemoteSapModel") -> None:
        self._model = model

    # -- secim: aga gonderilmez, yerelde biriktirilir ---------------------
    def SetLoadCasesSelectedForDisplay(self, cases: Any) -> int:
        self._model._selection.cases = _as_list(cases)
        return 0

    def SetLoadCombinationsSelectedForDisplay(self, combos: Any) -> int:
        self._model._selection.combos = _as_list(combos)
        return 0

    def SetLoadPatternsSelectedForDisplay(self, patterns: Any) -> int:
        self._model._selection.patterns = _as_list(patterns)
        return 0

    def GetAvailableTables(self) -> tuple:
        data = self._model._call(protocol.OP_GET_AVAILABLE_TABLES, {}, cacheable=True)
        names = data["table_keys"]
        return (len(names), tuple(names), tuple(data["import_types"]), tuple(data["is_empty"]), 0)

    # -- asil veri okuma --------------------------------------------------
    def GetTableForDisplayArray(
        self,
        TableKey: str,
        FieldKeyList: Any = None,
        GroupName: str = "All",
        TableVersion: int = 1,
        FieldsKeysIncluded: Any = None,
        NumberRecords: int = 0,
        TableData: Any = None,
    ) -> tuple:
        """Gercek COM cagrisiyla ayni demeti dondurur.

        Donus duzeni (comtypes'in ``[in,out]`` parametreleri sirasiyla):
        ``(FieldKeyList, TableVersion, FieldsKeysIncluded, NumberRecords,
        TableData, ret)`` -- yani sutunlar ``[2]``, veri ``[4]`` indisindedir.
        """
        args = {
            "table_key": TableKey,
            "field_key_list": _as_list(FieldKeyList),
            "group_name": GroupName or "All",
            "table_version": int(TableVersion or 1),
            "cases": self._model._selection.cases,
            "combos": self._model._selection.combos,
            "patterns": self._model._selection.patterns,
        }
        data = self._model._call(
            protocol.OP_GET_TABLE,
            args,
            cacheable=True,
            label=f"'{TableKey}' tablosu",
        )
        columns = tuple(data["columns"])
        table_data = tuple(data["data"])
        return (
            tuple(data.get("field_key_list") or ()),
            int(data.get("table_version", TableVersion or 1)),
            columns,
            int(data.get("number_records", 0)),
            table_data,
            int(data.get("ret", 0)),
        )


class _NameList:
    """``RespCombo`` / ``LoadCases`` gibi yalnizca isim listesi veren nesneler."""

    def __init__(self, model: "RemoteSapModel", op: str) -> None:
        self._model = model
        self._op = op

    def GetNameList(self) -> tuple:
        data = self._model._call(self._op, {}, cacheable=True)
        names = tuple(data["names"])
        return (len(names), names, 0)


class _PropMaterial:
    def __init__(self, model: "RemoteSapModel") -> None:
        self._model = model

    def GetWeightAndMass(self, name: str) -> tuple:
        data = self._model._call(
            protocol.OP_GET_WEIGHT_AND_MASS, {"name": name}, cacheable=True
        )
        return (data["weight_per_volume"], data["mass_per_volume"], 0)


class RemoteSapModel:
    """Uzaktaki ETABS oturumunu temsil eden, COM ile ayni sekilli proxy."""

    def __init__(
        self,
        transport: BridgeTransport,
        username: str,
        client_id: str,
        cache: Optional[dict] = None,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        progress=None,
    ) -> None:
        self._transport = transport
        self._username = username
        self._client_id = client_id
        self._cache = cache if cache is not None else {}
        self._cache_ttl = cache_ttl
        self._selection = _DisplaySelection()
        self._progress = progress  # opsiyonel: (mesaj) -> None

        self.DatabaseTables = _DatabaseTables(self)
        self.RespCombo = _NameList(self, protocol.OP_GET_COMBO_NAME_LIST)
        self.LoadCases = _NameList(self, protocol.OP_GET_LOAD_CASE_NAME_LIST)
        self.PropMaterial = _PropMaterial(self)

    # -- COM'daki dogrudan metotlar --------------------------------------
    def SetPresentUnits(self, units: int) -> int:
        """Rapor birimini ayarlar.

        Ayni birim tekrar istenirse ag trafigi olusmaz; Streamlit her
        etkilesimde sayfayi bastan calistirdigi icin bu onemli. Birim
        gercekten degistiginde onbellekteki tablolar gecersiz kilinir --
        aksi halde kN-m okunmus bir tablo ton-m sanilarak kullanilirdi.
        """
        units = int(units)
        if self._cache.get("__units__") == units:
            return 0
        self.clear_cache()
        self._call(protocol.OP_SET_PRESENT_UNITS, {"units": units})
        self._cache["__units__"] = units
        return 0

    def GetModelFilename(self, IncludePath: bool = True) -> str:
        data = self._call(protocol.OP_GET_MODEL_FILENAME, {}, cacheable=True)
        return data.get("filename") or ""

    # -- yardimcilar ------------------------------------------------------
    def ping(self) -> dict[str, Any]:
        return self._call(protocol.OP_PING, {}, timeout=30)

    def clear_cache(self) -> None:
        units = self._cache.get("__units__")
        self._cache.clear()
        if units is not None:
            self._cache["__units__"] = units

    def cache_age(self) -> Optional[float]:
        """En eski onbellek girdisinin yasi (saniye); bos ise ``None``."""
        stamps = [v[0] for k, v in self._cache.items() if k != "__units__"]
        return time.time() - min(stamps) if stamps else None

    def release(self) -> None:
        """Ajan uzerindeki ozel kullanim hakkini birakir."""
        self._transport.release(self._username, self._client_id)

    # -- ic cagri ---------------------------------------------------------
    def _call(
        self,
        op: str,
        args: dict[str, Any],
        cacheable: bool = False,
        timeout: int = protocol.DEFAULT_CALL_TIMEOUT,
        label: str = "",
    ) -> Any:
        cache_key = ""
        if cacheable:
            cache_key = op + "|" + json.dumps(args, sort_keys=True, ensure_ascii=False)
            hit = self._cache.get(cache_key)
            if hit is not None and (time.time() - hit[0]) < self._cache_ttl:
                return hit[1]

        if self._progress and label:
            self._progress(f"ETABS'ten {label} okunuyor...")

        result = self._transport.call(
            self._username, self._client_id, op, args, timeout=timeout
        )

        if cacheable:
            self._cache[cache_key] = (time.time(), result)
        return result
