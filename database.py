"""Veritabani katmani (SQLite).

Uretim notlari
--------------
* Sifreler **bcrypt** ile saklanir. Eski surumde duz SHA-256 kullaniliyordu;
  o kayitlar ilk basarili giriste sessizce bcrypt'e yukseltilir
  (bkz. ``verify_user``).
* WAL modu ve ``busy_timeout`` acik; boylece ayni anda birden fazla kullanici
  yazarken "database is locked" hatasi alinmaz.
* Veritabani yolu ``STACONTROL_DB`` ortam degiskeniyle degistirilebilir --
  uretimde kalici bir dizine (orn. /var/lib/stacontrol) alin.
"""

import hashlib
import hmac
import os
import re
import sqlite3
import time
from datetime import datetime

import bcrypt
import pandas as pd

DB_NAME = os.environ.get("STACONTROL_DB", "hesaplama_sonuc.db")

#: bcrypt maliyet katsayisi. 12 ~ 250 ms; giris hizini kabul edilebilir
#: tutarken kaba kuvvet saldirisini pahali kilar.
_BCRYPT_ROUNDS = int(os.environ.get("STACONTROL_BCRYPT_ROUNDS", "12"))

#: Eski (yukseltilmemis) SHA-256 ozeti bicimi.
_LEGACY_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Basit giris denemesi sinirlama durumu {kullanici: (deneme, ilk_deneme_zamani)}
_LOGIN_ATTEMPTS: dict[str, list] = {}
_MAX_ATTEMPTS = 8
_ATTEMPT_WINDOW = 300  # saniye


def get_connection():
    """Veritabanı bağlantısı oluşturur."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ---------------------------------------------------------------------------
# Hesaplamalar tablosu
# ---------------------------------------------------------------------------

def create_hesaplamalar_table():
    """Hesaplamalar tablosunu oluşturur."""
    conn = get_connection()
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS hesaplamalar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        hesap_tipi TEXT NOT NULL,
        sonuc TEXT NOT NULL,
        hesap_tarihi TEXT NOT NULL,
        kaynak_sayfa TEXT NOT NULL
    );
    """
    conn.execute(create_table_sql)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_hesaplamalar_user"
        " ON hesaplamalar(username, hesap_tarihi DESC)"
    )
    conn.commit()
    conn.close()


def add_kaynak_sayfa_column():
    """Hesaplamalar tablosuna kaynak_sayfa sütununu ekler (eski şema için)."""
    conn = get_connection()
    try:
        conn.execute(
            "ALTER TABLE hesaplamalar ADD COLUMN kaynak_sayfa TEXT NOT NULL"
            " DEFAULT 'bilinmiyor'"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # sütun zaten var
    finally:
        conn.close()


def save_hesaplama(hesap_tipi: str, sonuc: str, username: str, kaynak_sayfa: str):
    """Hesaplama sonucunu veritabanına kaydeder."""
    conn = get_connection()
    hesap_tarihi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    insert_sql = """
    INSERT INTO hesaplamalar (username, hesap_tipi, sonuc, hesap_tarihi, kaynak_sayfa)
    VALUES (?, ?, ?, ?, ?)
    """
    try:
        conn.execute(insert_sql, (username, hesap_tipi, sonuc, hesap_tarihi, kaynak_sayfa))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Hesaplama kaydedilirken hata oluştu: {e}")
        raise
    finally:
        conn.close()


def get_hesaplamalar(username: str = None):
    """Kullanıcıya ait hesaplamaları döndürür."""
    conn = get_connection()
    try:
        if username:
            query = (
                "SELECT * FROM hesaplamalar WHERE username = ?"
                " ORDER BY hesap_tarihi DESC"
            )
            df = pd.read_sql_query(query, conn, params=(username,))
        else:
            query = "SELECT * FROM hesaplamalar ORDER BY hesap_tarihi DESC"
            df = pd.read_sql_query(query, conn)
        return df
    except sqlite3.Error as e:
        print(f"Hesaplamalar alınırken hata oluştu: {e}")
        return pd.DataFrame()
    finally:
        conn.close()


def get_hesaplama_by_id(saved_id: int, username: str):
    """Belirli bir hesaplama kaydını ID ve kullanıcı adına göre döndürür."""
    conn = get_connection()
    try:
        query = """
        SELECT id, username, hesap_tipi, sonuc, hesap_tarihi, kaynak_sayfa
        FROM hesaplamalar
        WHERE id = ? AND username = ?
        """
        df = pd.read_sql_query(query, conn, params=(saved_id, username))
        if not df.empty:
            return df.iloc[0]
        return None
    except sqlite3.Error as e:
        print(f"Hesaplama alınırken hata oluştu: {e}")
        return None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Kullanıcılar
# ---------------------------------------------------------------------------

def create_users_table():
    """Kullanıcılar tablosunu oluşturur."""
    conn = get_connection()
    create_users_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    );
    """
    conn.execute(create_users_sql)
    conn.commit()
    conn.close()


def normalize_username(username: str) -> str:
    """Kullanıcı adını tekilleştirir (baş/son boşluk yok, küçük harf)."""
    return (username or "").strip().lower()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def _rate_limited(username: str) -> bool:
    """Aynı kullanıcı adına art arda deneme yapılmasını yavaşlatır."""
    now = time.time()
    attempts, first = _LOGIN_ATTEMPTS.get(username, [0, now])
    if now - first > _ATTEMPT_WINDOW:
        attempts, first = 0, now
    if attempts >= _MAX_ATTEMPTS:
        return True
    _LOGIN_ATTEMPTS[username] = [attempts + 1, first]
    return False


def _clear_attempts(username: str) -> None:
    _LOGIN_ATTEMPTS.pop(username, None)


def register_user(username: str, password: str):
    """Yeni bir kullanıcı kaydeder.

    Args:
        username: Kullanıcı adı.
        password: **Düz metin** şifre. Karma (hash) işlemi burada yapılır --
            çağıran taraf şifreyi asla kendisi hash'lememelidir.
    """
    username = normalize_username(username)
    if len(username) < 3:
        return False, "Kullanıcı adı en az 3 karakter olmalı."
    if len(password or "") < 8:
        return False, "Şifre en az 8 karakter olmalı."

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, _hash_password(password)),
        )
        conn.commit()
        return True, "Kayıt başarılı! Artık giriş yapabilirsiniz."
    except sqlite3.IntegrityError:
        return False, "Bu kullanıcı adı zaten mevcut."
    except sqlite3.Error as e:
        return False, f"Kayıt sırasında hata oluştu: {e}"
    finally:
        conn.close()


def verify_user(username: str, password: str) -> bool:
    """Kullanıcı kimlik bilgilerini doğrular.

    Eski SHA-256 kayıtları da kabul eder ve ilk başarılı girişte bcrypt'e
    yükseltir; böylece mevcut kullanıcılar şifre sıfırlamak zorunda kalmaz.
    """
    username = normalize_username(username)
    if not username or not password:
        return False
    if _rate_limited(username):
        return False

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            # Kullanıcı yoksa da benzer sürede yanıt ver (zamanlama sızıntısını azaltır)
            bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
            return False

        stored = row[0] or ""

        if _LEGACY_SHA256.match(stored):
            legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(legacy, stored):
                return False
            # Sessiz yükseltme
            conn.execute(
                "UPDATE users SET password = ? WHERE username = ?",
                (_hash_password(password), username),
            )
            conn.commit()
            _clear_attempts(username)
            return True

        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except ValueError:
            return False
        if ok:
            _clear_attempts(username)
        return ok
    except sqlite3.Error as e:
        print(f"Kullanıcı doğrulanırken hata oluştu: {e}")
        return False
    finally:
        conn.close()


def change_password(username: str, old_password: str, new_password: str):
    """Şifre değiştirir."""
    if not verify_user(username, old_password):
        return False, "Mevcut şifre hatalı."
    if len(new_password or "") < 8:
        return False, "Yeni şifre en az 8 karakter olmalı."
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (_hash_password(new_password), normalize_username(username)),
        )
        conn.commit()
        return True, "Şifreniz güncellendi."
    finally:
        conn.close()


# Tabloları oluştur ve şemayı güncelle
create_hesaplamalar_table()
create_users_table()
add_kaynak_sayfa_column()
