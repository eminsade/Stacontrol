"""Ajan <-> sunucu <-> web arasindaki ortak protokol.

Sadece standart kutuphane kullanir; ajan tarafinda oldugu gibi kopyalanabilir.

Tel formati
-----------
Is (job) ve sonuc govdeleri her zaman ``gzip(json.dumps(...).encode("utf-8"))``
olarak tasinir. Buyuk ETABS tablolari (yuz binlerce hucre) icin base64
kullanmiyoruz; ham gzip govdesi hem CPU hem bant genisligi acisindan ucuzdur.
"""

from __future__ import annotations

import gzip
import json
from typing import Any

# ---------------------------------------------------------------------------
# Desteklenen islemler (beyaz liste)
# ---------------------------------------------------------------------------
# Ajan SADECE bu islemleri yerine getirir. Sunucu ele gecirilse bile ajana
# rastgele kod calistirtilamaz; her islem sabit bir ETABS API cagrisina eslenir.

OP_PING = "ping"
OP_GET_MODEL_FILENAME = "get_model_filename"
OP_SET_PRESENT_UNITS = "set_present_units"
OP_GET_COMBO_NAME_LIST = "get_combo_name_list"
OP_GET_LOAD_CASE_NAME_LIST = "get_load_case_name_list"
OP_SET_CASES_FOR_DISPLAY = "set_load_cases_selected_for_display"
OP_SET_COMBOS_FOR_DISPLAY = "set_load_combinations_selected_for_display"
OP_SET_PATTERNS_FOR_DISPLAY = "set_load_patterns_selected_for_display"
OP_GET_TABLE = "get_table_for_display_array"
OP_GET_AVAILABLE_TABLES = "get_available_tables"
OP_GET_WEIGHT_AND_MASS = "get_material_weight_and_mass"

ALLOWED_OPS = frozenset(
    {
        OP_PING,
        OP_GET_MODEL_FILENAME,
        OP_SET_PRESENT_UNITS,
        OP_GET_COMBO_NAME_LIST,
        OP_GET_LOAD_CASE_NAME_LIST,
        OP_SET_CASES_FOR_DISPLAY,
        OP_SET_COMBOS_FOR_DISPLAY,
        OP_SET_PATTERNS_FOR_DISPLAY,
        OP_GET_TABLE,
        OP_GET_AVAILABLE_TABLES,
        OP_GET_WEIGHT_AND_MASS,
    }
)

# Sonuc durum basligi
STATUS_HEADER = "X-Result-Status"
STATUS_OK = "ok"
STATUS_ERROR = "error"

# Ajanin uzun yoklama (long-poll) suresi. Ters vekil sunucu (nginx) zaman
# asimindan kisa tutulmalidir.
AGENT_POLL_SECONDS = 25

# Web tarafinin bir isin sonucunu beklerken kullandigi varsayilan zaman asimi.
# Buyuk modellerde 'Object Connectivity' tablolari uzun surebilir.
DEFAULT_CALL_TIMEOUT = 180

# Tek bir sonuc govdesi icin ust sinir (sikistirilmis).
MAX_RESULT_BYTES = 64 * 1024 * 1024


class BridgeError(Exception):
    """Kopru katmaninda olusan, kullaniciya gosterilebilir hata."""


class AgentOfflineError(BridgeError):
    """Kullaniciya bagli calisan bir ajan yok."""


class AgentBusyError(BridgeError):
    """Ajan baska bir oturum/sekme tarafindan kullaniliyor."""


class AgentTimeoutError(BridgeError):
    """Ajan verilen sure icinde yanit vermedi."""


class EtabsError(BridgeError):
    """Ajan ETABS'e ulasti ama ETABS hata dondurdu."""


def encode(payload: Any) -> bytes:
    """Python nesnesini tel formatina cevirir."""
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, compresslevel=6)


def decode(blob: bytes) -> Any:
    """Tel formatindaki govdeyi Python nesnesine cevirir."""
    if not blob:
        return None
    return json.loads(gzip.decompress(blob).decode("utf-8"))
