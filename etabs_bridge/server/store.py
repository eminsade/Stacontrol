"""Kopru sunucusunun kalici durumu (SQLite).

Neden SQLite? Ek bir altyapi (Redis/Postgres) zorunlu kilmadan tek sunucuda
guvenilir calisir. Yuk artarsa ayni arayuz Redis ile degistirilebilir --
disaridan sadece bu modulun fonksiyonlari kullanilir.

Es zamanlilik notlari
---------------------
* WAL modu + ``busy_timeout`` ile okuma/yazma cakismasi engellenir.
* Baglantilar is parcaciklarina (thread) ozeldir; FastAPI bu fonksiyonlari
  ``asyncio.to_thread`` icinde cagirir, boylece olay dongusu bloke olmaz.
* Is alma (``next_job``) ``BEGIN IMMEDIATE`` ile atomiktir; ayni is iki kez
  dagitilmaz.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from typing import Any, Optional

from . import config

# Karistirilmasi kolay karakterler (0/O, 1/I/L) cikarildi.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 6

#: Sonucu alinmamis isler icin ust yas siniri (saniye).
JOB_TTL = 900

_local = threading.local()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    session_id    TEXT PRIMARY KEY,
    token_hash    TEXT NOT NULL,
    pairing_code  TEXT,
    code_expires  REAL,
    username      TEXT,
    hostname      TEXT,
    agent_version TEXT,
    model_file    TEXT,
    created_at    REAL NOT NULL,
    last_seen     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_agents_user ON agents(username);
CREATE INDEX IF NOT EXISTS idx_agents_code ON agents(pairing_code);

CREATE TABLE IF NOT EXISTS jobs (
    seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     TEXT UNIQUE NOT NULL,
    session_id TEXT NOT NULL,
    client_id  TEXT NOT NULL,
    op         TEXT NOT NULL,
    payload    BLOB NOT NULL,
    state      TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(session_id, state, seq);

CREATE TABLE IF NOT EXISTS results (
    job_id     TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    status     TEXT NOT NULL,
    blob       BLOB,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS leases (
    session_id TEXT PRIMARY KEY,
    client_id  TEXT NOT NULL,
    expires_at REAL NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(config.DB_PATH), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        _local.conn = conn
    return conn


def init() -> None:
    """Semayi olusturur. Uygulama acilisinda bir kez cagrilir."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _conn().executescript(_SCHEMA)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    now = time.time()
    return {
        "session_id": row["session_id"],
        "username": row["username"],
        "hostname": row["hostname"],
        "agent_version": row["agent_version"],
        "model_file": row["model_file"],
        "pairing_code": row["pairing_code"],
        "paired": row["username"] is not None,
        "last_seen": row["last_seen"],
        "online": (now - row["last_seen"]) <= config.AGENT_IDLE_TIMEOUT,
    }


# ---------------------------------------------------------------------------
# Ajan yasam dongusu
# ---------------------------------------------------------------------------

def register_agent(hostname: str, agent_version: str) -> tuple[str, str, str]:
    """Yeni bir ajan oturumu acar.

    Returns:
        ``(session_id, token, pairing_code)`` -- token yalnizca burada duz metin
        olarak doner; veritabaninda sadece SHA-256 ozeti saklanir.
    """
    conn = _conn()
    session_id = secrets.token_urlsafe(18)
    token = secrets.token_urlsafe(32)
    now = time.time()

    # Ayni anda gecerli olan kodlarin benzersizligini garanti et.
    code = ""
    for _ in range(50):
        candidate = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        taken = conn.execute(
            "SELECT 1 FROM agents WHERE pairing_code = ? AND code_expires > ?",
            (candidate, now),
        ).fetchone()
        if not taken:
            code = candidate
            break
    if not code:  # pragma: no cover - pratikte ulasilamaz
        raise RuntimeError("Bos eslestirme kodu uretilemedi")

    conn.execute(
        "INSERT INTO agents (session_id, token_hash, pairing_code, code_expires,"
        " username, hostname, agent_version, model_file, created_at, last_seen)"
        " VALUES (?,?,?,?,NULL,?,?,NULL,?,?)",
        (
            session_id,
            _hash(token),
            code,
            now + config.PAIRING_TTL,
            hostname[:120],
            agent_version[:32],
            now,
            now,
        ),
    )
    return session_id, token, code


def authenticate_agent(session_id: str, token: str) -> Optional[sqlite3.Row]:
    """Ajan kimligini dogrular; gecersizse ``None`` doner."""
    row = _conn().execute(
        "SELECT * FROM agents WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    if not secrets.compare_digest(row["token_hash"], _hash(token)):
        return None
    return row


def touch_agent(session_id: str, model_file: Optional[str] = None) -> None:
    """Ajanin canli oldugunu isaretler."""
    conn = _conn()
    if model_file is None:
        conn.execute(
            "UPDATE agents SET last_seen = ? WHERE session_id = ?",
            (time.time(), session_id),
        )
    else:
        conn.execute(
            "UPDATE agents SET last_seen = ?, model_file = ? WHERE session_id = ?",
            (time.time(), model_file[:260], session_id),
        )


def claim_code(code: str, username: str) -> Optional[dict[str, Any]]:
    """Web tarafi eslestirme kodunu bir kullaniciya baglar.

    Bir kullanicinin ayni anda tek ajani olur; onceki oturum dusurulur.
    """
    conn = _conn()
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT * FROM agents WHERE pairing_code = ? AND code_expires > ?"
            " AND username IS NULL",
            (code.strip().upper(), now),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return None

        session_id = row["session_id"]

        # Kullanicinin onceki ajanlarini temizle (tek aktif ajan kurali).
        for old_row in conn.execute(
            "SELECT session_id FROM agents WHERE username = ?", (username,)
        ).fetchall():
            _purge_session(conn, old_row["session_id"])

        conn.execute(
            "UPDATE agents SET username = ?, pairing_code = NULL, code_expires = NULL"
            " WHERE session_id = ?",
            (username, session_id),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    fresh = conn.execute(
        "SELECT * FROM agents WHERE session_id = ?", (session_id,)
    ).fetchone()
    return _row_to_session(fresh) if fresh else None


def get_session_for_user(username: str) -> Optional[dict[str, Any]]:
    """Kullaniciya bagli ajan oturumunu dondurur."""
    row = _conn().execute(
        "SELECT * FROM agents WHERE username = ? ORDER BY last_seen DESC LIMIT 1",
        (username,),
    ).fetchone()
    return _row_to_session(row) if row else None


def get_session(session_id: str) -> Optional[dict[str, Any]]:
    row = _conn().execute(
        "SELECT * FROM agents WHERE session_id = ?", (session_id,)
    ).fetchone()
    return _row_to_session(row) if row else None


def _purge_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("DELETE FROM jobs WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM results WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM leases WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM agents WHERE session_id = ?", (session_id,))


def drop_session(session_id: str) -> None:
    """Oturumu ve tum izlerini siler (kullanici 'baglantiyi kes' dedi)."""
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        _purge_session(conn, session_id)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ---------------------------------------------------------------------------
# Kiralama: ayni ajani iki sekmenin ayni anda kullanmasini engeller
# ---------------------------------------------------------------------------

def acquire_lease(session_id: str, client_id: str) -> bool:
    """Ajan uzerinde ozel kullanim hakki alir ya da yeniler.

    ETABS cagrilari durumludur (once ``SetLoadCombinationsSelectedForDisplay``,
    sonra ``GetTableForDisplayArray``). Iki sekme ayni ajana es zamanli is
    gonderirse yanlis kombinasyonun tablosu okunabilir. Kiralama bunu onler.
    """
    conn = _conn()
    now = time.time()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT client_id, expires_at FROM leases WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is not None and row["expires_at"] > now and row["client_id"] != client_id:
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "INSERT INTO leases (session_id, client_id, expires_at) VALUES (?,?,?)"
            " ON CONFLICT(session_id) DO UPDATE SET client_id = excluded.client_id,"
            " expires_at = excluded.expires_at",
            (session_id, client_id, now + config.LEASE_TTL),
        )
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def release_lease(session_id: str, client_id: str) -> None:
    _conn().execute(
        "DELETE FROM leases WHERE session_id = ? AND client_id = ?",
        (session_id, client_id),
    )


# ---------------------------------------------------------------------------
# Is kuyrugu
# ---------------------------------------------------------------------------

def enqueue_job(session_id: str, client_id: str, op: str, payload: bytes) -> str:
    job_id = secrets.token_urlsafe(16)
    _conn().execute(
        "INSERT INTO jobs (job_id, session_id, client_id, op, payload, state, created_at)"
        " VALUES (?,?,?,?,?,'queued',?)",
        (job_id, session_id, client_id, op, payload, time.time()),
    )
    return job_id


def next_job(session_id: str) -> Optional[dict[str, Any]]:
    """Siradaki isi atomik olarak alir ve 'running' isaretler."""
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT job_id, op, payload FROM jobs"
            " WHERE session_id = ? AND state = 'queued' ORDER BY seq LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute(
            "UPDATE jobs SET state = 'running' WHERE job_id = ?", (row["job_id"],)
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"job_id": row["job_id"], "op": row["op"], "payload": row["payload"]}


def put_result(session_id: str, job_id: str, status: str, blob: bytes) -> bool:
    """Ajanin dondurdugu sonucu saklar. Is bu oturuma ait degilse ``False``."""
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT session_id FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None or row["session_id"] != session_id:
            conn.execute("ROLLBACK")
            return False
        conn.execute(
            "INSERT INTO results (job_id, session_id, status, blob, created_at)"
            " VALUES (?,?,?,?,?)"
            " ON CONFLICT(job_id) DO UPDATE SET status = excluded.status,"
            " blob = excluded.blob, created_at = excluded.created_at",
            (job_id, session_id, status, blob, time.time()),
        )
        conn.execute("UPDATE jobs SET state = 'done' WHERE job_id = ?", (job_id,))
        conn.execute("COMMIT")
        return True
    except Exception:
        conn.execute("ROLLBACK")
        raise


def take_result(job_id: str) -> Optional[dict[str, Any]]:
    """Sonucu okur ve siler.

    Tek seferlik teslim bilincli bir tercih: model verisi sunucuda birikmez.
    """
    conn = _conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT status, blob FROM results WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        conn.execute("DELETE FROM results WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return {"status": row["status"], "blob": row["blob"]}


def cancel_job(job_id: str) -> None:
    """Zaman asimina ugrayan isi kuyruktan dusurur."""
    conn = _conn()
    conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM results WHERE job_id = ?", (job_id,))


# ---------------------------------------------------------------------------
# Bakim
# ---------------------------------------------------------------------------

def cleanup() -> None:
    """Suresi gecmis kayitlari temizler. Arka planda periyodik cagrilir."""
    conn = _conn()
    now = time.time()

    conn.execute("DELETE FROM results WHERE created_at < ?", (now - config.RESULT_TTL,))
    conn.execute("DELETE FROM leases WHERE expires_at < ?", (now,))
    conn.execute("DELETE FROM jobs WHERE created_at < ?", (now - JOB_TTL,))

    # Eslestirilmemis ve kodu suresi dolmus ajan oturumlari
    for row in conn.execute(
        "SELECT session_id FROM agents WHERE username IS NULL AND code_expires < ?",
        (now,),
    ).fetchall():
        _purge_session(conn, row["session_id"])

    # 24 saattir hic goruinmeyen eslesmis ajanlar
    for row in conn.execute(
        "SELECT session_id FROM agents WHERE last_seen < ?", (now - 24 * 3600,)
    ).fetchall():
        _purge_session(conn, row["session_id"])


def stats() -> dict[str, int]:
    """Basit saglik/izleme sayaclari."""
    conn = _conn()
    now = time.time()
    return {
        "agents_total": conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0],
        "agents_online": conn.execute(
            "SELECT COUNT(*) FROM agents WHERE last_seen > ?",
            (now - config.AGENT_IDLE_TIMEOUT,),
        ).fetchone()[0],
        "jobs_queued": conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE state = 'queued'"
        ).fetchone()[0],
        "results_pending": conn.execute("SELECT COUNT(*) FROM results").fetchone()[0],
    }
