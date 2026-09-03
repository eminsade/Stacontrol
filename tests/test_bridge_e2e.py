"""Ucdan uca kopru testi -- ETABS olmadan.

Bu test gercek sunucuyu bir is parcaciginda calistirir, gercek ajan kodunu
sahte bir ``SapModel`` ile besler ve web tarafindaki ``RemoteSapModel``
proxy'sini kullanir. Amaci tek bir soruyu kesin cevaplamak:

    "Sayfalardaki hesap kodu, uzak proxy ile yerel COM nesnesinden ayirt
     edilemez bir sekilde calisiyor mu?"

Ozellikle donus demetlerinin (tuple) indis duzeni onemlidir: sayfalar
``ret[2]`` ile sutunlari, ``ret[4]`` ile veriyi okur. Bu duzen bozulursa
tum sayfalar sessizce yanlis calisir -- bu yuzden dogrudan test edilir.

Calistirma:  python -m pytest tests/test_bridge_e2e.py -v
"""

from __future__ import annotations

import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "etabs_bridge"))  # ajanin "import protocol" satiri icin

# Sunucu yapilandirmasi icte import edilmeden once verilmeli.
_TMP_DB = Path(tempfile.gettempdir()) / f"bridge_test_{os.getpid()}.db"
os.environ["BRIDGE_INTERNAL_KEY"] = "test-internal-key-0123456789"
os.environ["BRIDGE_DB"] = str(_TMP_DB)

from etabs_bridge import protocol  # noqa: E402
from etabs_bridge.agent import agent as agent_mod  # noqa: E402
from etabs_bridge.client import BridgeTransport, RemoteSapModel  # noqa: E402
from etabs_bridge.protocol import (  # noqa: E402
    AgentBusyError,
    AgentOfflineError,
    EtabsError,
)

USERNAME = "test.kullanici"


# ---------------------------------------------------------------------------
# Sahte ETABS
# ---------------------------------------------------------------------------

class FakeDatabaseTables:
    """Gercek ``SapModel.DatabaseTables`` ile ayni sekle sahip sahte nesne."""

    def __init__(self, owner):
        self.owner = owner

    def SetLoadCasesSelectedForDisplay(self, names):
        self.owner.selection["cases"] = list(names)
        return 0

    def SetLoadCombinationsSelectedForDisplay(self, names):
        self.owner.selection["combos"] = list(names)
        return 0

    def SetLoadPatternsSelectedForDisplay(self, names):
        self.owner.selection["patterns"] = list(names)
        return 0

    def GetTableForDisplayArray(
        self, table_key, field_key_list, group_name, table_version,
        fields_included, number_records, table_data
    ):
        self.owner.calls.append((table_key, dict(self.owner.selection)))

        if table_key == "Bos Tablo":
            return ((), 1, (), 0, (), 0)

        columns = ("Story", "Pier", "OutputCase", "V2")
        combo = (self.owner.selection.get("combos") or ["YOK"])[0]
        rows = [
            ("Kat1", "P1", combo, "120.5"),
            ("Kat1", "P2", combo, "-88.25"),
            ("Kat2", "P1", combo, "64.0"),
        ]
        flat = tuple(cell for row in rows for cell in row)
        # COM ile ayni duzen: (FieldKeyList, TableVersion, FieldsKeysIncluded,
        #                      NumberRecords, TableData, ret)
        return ((), 1, columns, len(rows), flat, 0)

    def GetAvailableTables(self):
        return (2, ("Pier Forces", "Story Drifts"), (0, 0), (0, 0), 0)


class FakeNameList:
    def __init__(self, names):
        self.names = tuple(names)

    def GetNameList(self):
        return (len(self.names), self.names, 0)


class FakePropMaterial:
    def GetWeightAndMass(self, name):
        if name == "YOK":
            raise RuntimeError("Malzeme bulunamadi")
        return (2.5, 0.2548, 0)


class FakeSapModel:
    def __init__(self):
        self.selection = {"cases": [], "combos": [], "patterns": []}
        self.calls = []
        self.units = None
        self.DatabaseTables = FakeDatabaseTables(self)
        self.RespCombo = FakeNameList(["G+Q", "DEPREM_X", "DEPREM_Y"])
        self.LoadCases = FakeNameList(["G", "Q", "EX", "EY", "MODAL"])
        self.PropMaterial = FakePropMaterial()

    def SetPresentUnits(self, units):
        self.units = units
        return 0

    def GetModelFilename(self):
        return r"C:\Projeler\ornek_bina.EDB"


class FakeEtabsSession:
    """``agent.EtabsSession`` yerine gecer; COM yerine sahte modeli dondurur."""

    def __init__(self, sap):
        self.sap = sap

    def model(self):
        return self.sap

    def model_filename(self):
        return self.sap.GetModelFilename()


# ---------------------------------------------------------------------------
# Sunucu ve ajan yardimcilari
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServerThread:
    def __init__(self, port: int):
        import uvicorn

        from etabs_bridge.server.app import app

        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        for _ in range(200):
            if getattr(self.server, "started", False):
                return
            time.sleep(0.05)
        raise RuntimeError("Sunucu baslamadi")

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


class AgentThread:
    """Gercek ajan dongusunun test surumu (sahte ETABS ile)."""

    def __init__(self, base_url: str, sap: FakeSapModel):
        self.client = agent_mod.BridgeClient(base_url)
        self.session = FakeEtabsSession(sap)
        self.pairing_code = ""
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.errors: list[str] = []

    def start(self):
        info = self.client.register()
        self.pairing_code = info["pairing_code"]
        self.thread.start()

    def _loop(self):
        while not self._stop.is_set():
            try:
                poll = self.client.poll()
                job = poll.get("job") if poll else None
                if job:
                    agent_mod.run_job(self.session, self.client, job)
            except Exception as exc:  # pragma: no cover
                self.errors.append(str(exc))
                time.sleep(0.2)

    def stop(self):
        self._stop.set()


@pytest.fixture(scope="module")
def bridge():
    if _TMP_DB.exists():
        _TMP_DB.unlink()

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"

    server = ServerThread(port)
    server.start()

    sap = FakeSapModel()
    agent = AgentThread(base_url, sap)
    agent.start()

    transport = BridgeTransport(base_url, os.environ["BRIDGE_INTERNAL_KEY"])
    transport.pair(USERNAME, agent.pairing_code)

    yield {"transport": transport, "sap": sap, "agent": agent, "base_url": base_url}

    agent.stop()
    server.stop()
    if _TMP_DB.exists():
        try:
            _TMP_DB.unlink()
        except OSError:
            pass


#: Test sirasinda uretilen proxy'ler; her testten sonra kiralari birakilir.
_MODELS: list[RemoteSapModel] = []


@pytest.fixture(autouse=True)
def _kira_temizligi():
    """Her testten sonra ajan kirasini birak.

    Kiralama, ayni ajani iki tarayici sekmesinin ayni anda kullanmasini
    engeller. Testler farkli ``client_id`` degerleri kullandigi icin
    birakilmazsa sonraki test 'ajan mesgul' hatasi alir.
    """
    yield
    while _MODELS:
        try:
            _MODELS.pop().release()
        except Exception:
            pass


def make_model(bridge, client_id="istemci-1", cache=None, cache_ttl=300) -> RemoteSapModel:
    model = RemoteSapModel(
        transport=bridge["transport"],
        username=USERNAME,
        client_id=client_id,
        cache=cache if cache is not None else {},
        cache_ttl=cache_ttl,
    )
    _MODELS.append(model)
    return model


# ---------------------------------------------------------------------------
# Testler
# ---------------------------------------------------------------------------

def test_eslestirme_ve_durum(bridge):
    status = bridge["transport"].status(USERNAME)
    assert status["connected"] is True
    assert status["online"] is True


def test_model_dosya_adi(bridge):
    model = make_model(bridge)
    assert model.GetModelFilename().endswith("ornek_bina.EDB")


def test_kombinasyon_listesi_com_ile_ayni_sekilde(bridge):
    model = make_model(bridge)
    ret = model.RespCombo.GetNameList()
    # Sayfalar: num = ret[0], names = ret[1]
    assert ret[0] == 3
    assert "DEPREM_X" in ret[1]

    ret_cases = model.LoadCases.GetNameList()
    assert ret_cases[0] == 5
    assert "MODAL" in ret_cases[1]


def test_tablo_donus_duzeni_com_ile_ayni(bridge):
    """En kritik test: ret[2] sutunlar, ret[4] duz veri listesi olmali."""
    model = make_model(bridge)
    model.DatabaseTables.SetLoadCasesSelectedForDisplay([])
    model.DatabaseTables.SetLoadCombinationsSelectedForDisplay(["DEPREM_X"])
    model.DatabaseTables.SetLoadPatternsSelectedForDisplay([])

    ret = model.DatabaseTables.GetTableForDisplayArray(
        "Pier Forces", [], "All", 1, [], 0, []
    )

    columns = ret[2]
    data = ret[4]
    assert list(columns) == ["Story", "Pier", "OutputCase", "V2"]
    assert len(data) % len(columns) == 0

    # Sayfalardaki cozumlemenin birebir aynisi
    rows = [data[i:i + len(columns)] for i in range(0, len(data), len(columns))]
    assert len(rows) == 3
    assert rows[0][0] == "Kat1"
    assert rows[0][2] == "DEPREM_X"  # secim gercekten uygulanmis


def test_secim_tablo_okumayla_ayni_iste_gonderilir(bridge):
    """Kombinasyon secimi ve tablo okuma ajanda bolunmez sekilde calismali."""
    sap = bridge["sap"]
    sap.calls.clear()
    model = make_model(bridge, client_id="istemci-secim")

    for combo in ("G+Q", "DEPREM_Y"):
        model.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
        ret = model.DatabaseTables.GetTableForDisplayArray(
            "Pier Forces", [], "All", 1, [], 0, []
        )
        rows = [ret[4][i:i + len(ret[2])] for i in range(0, len(ret[4]), len(ret[2]))]
        assert rows[0][2] == combo

    assert [call[1]["combos"] for call in sap.calls] == [["G+Q"], ["DEPREM_Y"]]


def test_onbellek_tekrar_okumayi_engeller(bridge):
    sap = bridge["sap"]
    sap.calls.clear()
    cache: dict = {}
    model = make_model(bridge, client_id="istemci-onbellek", cache=cache)

    model.DatabaseTables.SetLoadCombinationsSelectedForDisplay(["G+Q"])
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 1, "ikinci okuma onbellekten gelmeliydi"

    # Farkli kombinasyon -> farkli onbellek anahtari -> yeni okuma
    model.DatabaseTables.SetLoadCombinationsSelectedForDisplay(["DEPREM_X"])
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 2

    # Elle yenileme onbellegi bosaltmali
    model.clear_cache()
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 3


def test_birim_degisimi_onbellegi_dusurur(bridge):
    sap = bridge["sap"]
    sap.calls.clear()
    cache: dict = {}
    model = make_model(bridge, client_id="istemci-birim", cache=cache)

    model.SetPresentUnits(6)
    assert sap.units == 6
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 1

    # Ayni birim tekrar istenirse aga cikilmaz
    model.SetPresentUnits(6)
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 1

    # Birim degisince eski tablolar gecersiz -- yeniden okunmali
    model.SetPresentUnits(12)
    assert sap.units == 12
    model.DatabaseTables.GetTableForDisplayArray("Pier Forces", [], "All", 1, [], 0, [])
    assert len(sap.calls) == 2


def test_malzeme_agirligi(bridge):
    model = make_model(bridge)
    ret = model.PropMaterial.GetWeightAndMass("C25")
    assert ret[0] == pytest.approx(2.5)   # sayfalar ret[0] kullanir


def test_etabs_hatasi_kullaniciya_tasinir(bridge):
    model = make_model(bridge, client_id="istemci-hata")
    with pytest.raises(EtabsError) as exc:
        model.DatabaseTables.GetTableForDisplayArray("Bos Tablo", [], "All", 1, [], 0, [])
    assert "Bos Tablo" in str(exc.value)


def test_ikinci_sekme_kilitlenir(bridge):
    """Ayni ajani iki istemci ayni anda kullanamaz."""
    first = make_model(bridge, client_id="sekme-A")
    first.GetModelFilename()  # kirayi alir

    second = make_model(bridge, client_id="sekme-B")
    with pytest.raises(AgentBusyError):
        second.GetModelFilename()

    first.release()
    # Kira birakilinca ikinci sekme calisabilmeli
    assert second.GetModelFilename().endswith("ornek_bina.EDB")
    second.release()


def test_ajan_yoksa_anlasilir_hata(bridge):
    model = RemoteSapModel(
        transport=bridge["transport"],
        username="hic-olmayan-kullanici",
        client_id="istemci-x",
        cache={},
    )
    with pytest.raises(AgentOfflineError):
        model.GetModelFilename()


def test_beyaz_liste_disi_islem_reddedilir(bridge):
    """Sunucu, protokolde tanimsiz bir islemi ajana hic iletmemeli."""
    import requests

    resp = requests.post(
        f"{bridge['base_url']}/api/web/call",
        json={
            "username": USERNAME,
            "client_id": "istemci-guvenlik",
            "op": "os.system",
            "args": {"cmd": "calc.exe"},
        },
        headers={"X-Internal-Key": os.environ["BRIDGE_INTERNAL_KEY"]},
        timeout=15,
    )
    assert resp.status_code == 400
    assert "Desteklenmeyen" in resp.json()["detail"]


def test_ic_anahtarsiz_erisim_reddedilir(bridge):
    import requests

    resp = requests.get(
        f"{bridge['base_url']}/api/web/status",
        params={"username": USERNAME},
        headers={"X-Internal-Key": "yanlis-anahtar"},
        timeout=15,
    )
    assert resp.status_code == 401


def test_protokol_gidis_donus(bridge):
    payload = {"columns": ["Story", "Pier"], "data": ["Kat1", "P1"] * 5000}
    assert protocol.decode(protocol.encode(payload)) == payload
