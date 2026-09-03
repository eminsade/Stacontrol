"""Kopru API'si.

Iki tarafi bulusturur:

* **Ajan** (kullanicinin bilgisayari) -- uzun yoklama ile is alir, ETABS'ten
  okudugu tabloyu geri gonderir. Sadece **giden** baglanti kurar; kullanicinin
  guvenlik duvarinda hicbir port acilmaz.
* **Web** (Streamlit arka ucu) -- ic anahtar ile is birakir ve sonucu bekler.

Tasarim notlari
---------------
* Ucnoktalar ``async``; SQLite erisimi ``asyncio.to_thread`` icinde yapilir, bu
  sayede uzun yoklama olay dongusunu bloke etmez.
* Ayni surec icinde ``asyncio.Event`` ile aninda uyandirma yapilir; birden fazla
  isci (worker) ile calisilirsa yoklamaya duser -- dogruluk her iki durumda da
  korunur (bkz. ``_WAKE`` aciklamasi).
* Model verisi sunucuda kalici olarak tutulmaz: sonuc bir kez okunur ve silinir.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict, deque
from typing import Any, Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .. import protocol
from ..protocol import STATUS_ERROR, STATUS_HEADER, STATUS_OK
from . import config, store

API_VERSION = "1.0.0"


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    """Acilista semayi kurar, kapanista temizlik gorevini durdurur."""
    await asyncio.to_thread(store.init)
    cleaner = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        cleaner.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleaner


app = FastAPI(
    title="ETABS Bridge",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url=None,       # Genel API dokumantasyonu yayinlamiyoruz
    redoc_url=None,
    openapi_url=None,
)

# ---------------------------------------------------------------------------
# Surec ici uyandirma
# ---------------------------------------------------------------------------
# Tek isci ile calisildiginda (onerilen kurulum) bu olaylar gecikmeyi
# milisaniyeye dusurur. Birden fazla isci varsa olay diger surece ulasmaz; bu
# durumda asagidaki bekleme donguleri kisa araliklarla veritabanini yoklamaya
# devam ettigi icin sistem yine dogru calisir, sadece biraz daha yavas olur.

_WAKE_JOB: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
_WAKE_RESULT: dict[str, asyncio.Event] = defaultdict(asyncio.Event)

_POLL_INTERVAL = 0.25


def _wake_job(session_id: str) -> None:
    _WAKE_JOB[session_id].set()


def _wake_result(job_id: str) -> None:
    _WAKE_RESULT[job_id].set()


async def _wait_event(event: asyncio.Event, timeout: float) -> None:
    """Olayi bekler; zaman asiminda sessizce doner."""
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(event.wait(), timeout=timeout)
    event.clear()


# ---------------------------------------------------------------------------
# Basit hiz sinirlama (kayit ucnoktasi icin)
# ---------------------------------------------------------------------------

_REGISTER_HITS: dict[str, deque] = defaultdict(deque)
_REGISTER_LIMIT = 20          # ayni IP'den
_REGISTER_WINDOW = 300        # 5 dakikada


def _rate_limited(ip: str) -> bool:
    now = time.time()
    hits = _REGISTER_HITS[ip]
    while hits and hits[0] < now - _REGISTER_WINDOW:
        hits.popleft()
    if len(hits) >= _REGISTER_LIMIT:
        return True
    hits.append(now)
    return False


# ---------------------------------------------------------------------------
# Kimlik dogrulama
# ---------------------------------------------------------------------------

async def agent_auth(
    x_session_id: str = Header(default=""),
    x_agent_token: str = Header(default=""),
) -> dict[str, Any]:
    """Ajan kimligini dogrular ve oturum bilgisini dondurur."""
    if not x_session_id or not x_agent_token:
        raise HTTPException(status_code=401, detail="Kimlik basliklari eksik")
    row = await asyncio.to_thread(store.authenticate_agent, x_session_id, x_agent_token)
    if row is None:
        raise HTTPException(status_code=401, detail="Gecersiz ajan oturumu")
    return {"session_id": x_session_id, "username": row["username"]}


async def web_auth(x_internal_key: str = Header(default="")) -> None:
    """Streamlit arka ucunu dogrular. Bu anahtar tarayiciya asla gonderilmez."""
    import secrets as _secrets

    if not _secrets.compare_digest(x_internal_key, config.INTERNAL_API_KEY):
        raise HTTPException(status_code=401, detail="Gecersiz ic anahtar")


# ---------------------------------------------------------------------------
# Yasam dongusu
# ---------------------------------------------------------------------------

async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.sleep(60)
            await asyncio.to_thread(store.cleanup)
            # Uyandirma sozluklerinin sinirsiz buyumesini engelle
            if len(_WAKE_RESULT) > 5000:
                _WAKE_RESULT.clear()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover
            print(f"[bridge] temizlik hatasi: {exc}")


@app.get("/healthz")
async def healthz() -> JSONResponse:
    data = await asyncio.to_thread(store.stats)
    return JSONResponse({"ok": True, "version": API_VERSION, **data})


# ===========================================================================
# AJAN UCNOKTALARI
# ===========================================================================

@app.post("/api/agent/register")
async def agent_register(request: Request, body: dict = Body(default={})) -> JSONResponse:
    """Ajan acilista buraya kayit olur ve ekranda gosterecegi kodu alir."""
    ip = (request.client.host if request.client else "?") or "?"
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Cok fazla deneme, biraz bekleyin")

    hostname = str(body.get("hostname", "bilinmiyor"))
    version = str(body.get("agent_version", "0"))
    session_id, token, code = await asyncio.to_thread(
        store.register_agent, hostname, version
    )
    return JSONResponse(
        {
            "session_id": session_id,
            "token": token,
            "pairing_code": code,
            "expires_in": config.PAIRING_TTL,
            "poll_seconds": protocol.AGENT_POLL_SECONDS,
            "min_agent_version": config.MIN_AGENT_VERSION,
        }
    )


@app.get("/api/agent/poll")
async def agent_poll(auth: dict = Depends(agent_auth)) -> Response:
    """Uzun yoklama: is varsa dondurur, yoksa 204 ile bos doner.

    Ayni istek kalp atisi gorevi de gorur; ajan surekli yoklama yaptigi surece
    ``last_seen`` guncel kalir ve web tarafi onu 'cevrimici' gorur.
    """
    session_id = auth["session_id"]
    await asyncio.to_thread(store.touch_agent, session_id)

    deadline = time.monotonic() + protocol.AGENT_POLL_SECONDS
    while True:
        job = await asyncio.to_thread(store.next_job, session_id)
        if job is not None:
            return Response(
                content=job["payload"],
                media_type="application/octet-stream",
                headers={
                    "X-Job-Id": job["job_id"],
                    "X-Job-Op": job["op"],
                    "X-Paired": "1" if auth["username"] else "0",
                },
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        await _wait_event(_WAKE_JOB[session_id], min(_POLL_INTERVAL, remaining))

    return Response(
        status_code=204,
        headers={"X-Paired": "1" if auth["username"] else "0"},
    )


@app.post("/api/agent/result/{job_id}")
async def agent_result(
    job_id: str,
    request: Request,
    auth: dict = Depends(agent_auth),
    x_result_status: str = Header(default=STATUS_OK),
) -> JSONResponse:
    """Ajan isin sonucunu (gzip'li JSON govdesi) buraya birakir."""
    blob = await request.body()
    if len(blob) > protocol.MAX_RESULT_BYTES:
        raise HTTPException(status_code=413, detail="Sonuc cok buyuk")

    status = STATUS_OK if x_result_status == STATUS_OK else STATUS_ERROR
    stored = await asyncio.to_thread(
        store.put_result, auth["session_id"], job_id, status, blob
    )
    if not stored:
        raise HTTPException(status_code=404, detail="Is bulunamadi")
    _wake_result(job_id)
    return JSONResponse({"ok": True})


@app.post("/api/agent/state")
async def agent_state(
    auth: dict = Depends(agent_auth), body: dict = Body(default={})
) -> JSONResponse:
    """Ajan acik model dosyasini bildirir (web tarafinda gosterilir)."""
    model_file = body.get("model_file")
    await asyncio.to_thread(
        store.touch_agent, auth["session_id"], model_file if model_file else None
    )
    session = await asyncio.to_thread(store.get_session, auth["session_id"])
    return JSONResponse({"ok": True, "paired": bool(session and session["paired"])})


# ===========================================================================
# WEB UCNOKTALARI (Streamlit arka ucu -> kopru)
# ===========================================================================

@app.post("/api/web/pair", dependencies=[Depends(web_auth)])
async def web_pair(body: dict = Body(...)) -> JSONResponse:
    """Kullanicinin girdigi eslestirme kodunu hesabina baglar."""
    code = str(body.get("code", "")).strip().upper()
    username = str(body.get("username", "")).strip()
    if not code or not username:
        raise HTTPException(status_code=400, detail="Kod ve kullanici zorunlu")

    session = await asyncio.to_thread(store.claim_code, code, username)
    if session is None:
        raise HTTPException(
            status_code=404, detail="Kod gecersiz, suresi dolmus veya kullanilmis"
        )
    _wake_job(session["session_id"])  # ajan hemen 'eslesti' bilgisini gorsun
    return JSONResponse(_public_session(session))


@app.get("/api/web/status", dependencies=[Depends(web_auth)])
async def web_status(username: str) -> JSONResponse:
    session = await asyncio.to_thread(store.get_session_for_user, username)
    if session is None:
        return JSONResponse({"connected": False})
    return JSONResponse({"connected": True, **_public_session(session)})


@app.post("/api/web/disconnect", dependencies=[Depends(web_auth)])
async def web_disconnect(body: dict = Body(...)) -> JSONResponse:
    username = str(body.get("username", "")).strip()
    session = await asyncio.to_thread(store.get_session_for_user, username)
    if session:
        await asyncio.to_thread(store.drop_session, session["session_id"])
    return JSONResponse({"ok": True})


@app.post("/api/web/release", dependencies=[Depends(web_auth)])
async def web_release(body: dict = Body(...)) -> JSONResponse:
    username = str(body.get("username", "")).strip()
    client_id = str(body.get("client_id", "")).strip()
    session = await asyncio.to_thread(store.get_session_for_user, username)
    if session:
        await asyncio.to_thread(store.release_lease, session["session_id"], client_id)
    return JSONResponse({"ok": True})


@app.post("/api/web/call", dependencies=[Depends(web_auth)])
async def web_call(body: dict = Body(...)) -> Response:
    """Bir ETABS islemini ajana gonderir ve sonucu bekler.

    Donus govdesi ajanin urettigi gzip'li JSON'dur; ``X-Result-Status`` basligi
    ``ok`` degilse govde ``{"message": ..., "kind": ...}`` seklindedir.
    """
    username = str(body.get("username", "")).strip()
    client_id = str(body.get("client_id", "")).strip()
    op = str(body.get("op", "")).strip()
    args = body.get("args") or {}
    timeout = float(body.get("timeout") or protocol.DEFAULT_CALL_TIMEOUT)
    timeout = max(5.0, min(timeout, 600.0))

    if op not in protocol.ALLOWED_OPS:
        raise HTTPException(status_code=400, detail=f"Desteklenmeyen islem: {op}")
    if not username or not client_id:
        raise HTTPException(status_code=400, detail="username ve client_id zorunlu")

    session = await asyncio.to_thread(store.get_session_for_user, username)
    if session is None:
        raise HTTPException(status_code=409, detail="agent_offline")
    if not session["online"]:
        raise HTTPException(status_code=409, detail="agent_offline")

    session_id = session["session_id"]

    got_lease = await asyncio.to_thread(store.acquire_lease, session_id, client_id)
    if not got_lease:
        raise HTTPException(status_code=423, detail="agent_busy")

    payload = protocol.encode({"op": op, "args": args})
    job_id = await asyncio.to_thread(
        store.enqueue_job, session_id, client_id, op, payload
    )
    _wake_job(session_id)

    deadline = time.monotonic() + timeout
    try:
        while True:
            result = await asyncio.to_thread(store.take_result, job_id)
            if result is not None:
                return Response(
                    content=result["blob"] or b"",
                    media_type="application/octet-stream",
                    headers={STATUS_HEADER: result["status"]},
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await _wait_event(_WAKE_RESULT[job_id], min(_POLL_INTERVAL, remaining))
    finally:
        _WAKE_RESULT.pop(job_id, None)

    await asyncio.to_thread(store.cancel_job, job_id)
    raise HTTPException(status_code=504, detail="agent_timeout")


def _public_session(session: dict[str, Any]) -> dict[str, Any]:
    """Web tarafina donen, sir icermeyen oturum ozeti."""
    return {
        "hostname": session["hostname"],
        "agent_version": session["agent_version"],
        "model_file": session["model_file"],
        "online": session["online"],
        "paired": session["paired"],
        "last_seen": session["last_seen"],
    }
