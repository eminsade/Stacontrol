import sqlite3
import pandas as pd
from datetime import datetime

DB_NAME = "hesaplama_sonuc.db"

def get_connection():
    """Veritabanı bağlantısı oluşturur."""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    return conn

# Hesaplamalar tablosu
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
    conn.commit()
    conn.close()

def add_kaynak_sayfa_column():
    """Hesaplamalar tablosuna kaynak_sayfa sütununu ekler."""
    conn = get_connection()
    try:
        # Mevcut tabloya kaynak_sayfa sütununu ekle
        conn.execute("ALTER TABLE hesaplamalar ADD COLUMN kaynak_sayfa TEXT NOT NULL DEFAULT 'bilinmiyor'")
        conn.commit()
        print("kaynak_sayfa sütunu başarıyla eklendi.")
    except sqlite3.OperationalError as e:
        # Eğer sütun zaten varsa hata vermesini engelle
        print(f"Sütun eklenirken hata oluştu (muhtemelen sütun zaten var): {e}")
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
            query = "SELECT * FROM hesaplamalar WHERE username = ? ORDER BY hesap_tarihi DESC"
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

# Kullanıcılar tablosu
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

def register_user(username: str, password: str):
    """Yeni bir kullanıcı kaydeder."""
    conn = get_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        conn.commit()
        return True, "Kayıt başarılı! Artık giriş yapabilirsiniz."
    except sqlite3.IntegrityError:
        return False, "Bu kullanıcı adı zaten mevcut."
    except sqlite3.Error as e:
        return False, f"Kayıt sırasında hata oluştu: {e}"
    finally:
        conn.close()

def verify_user(username: str, password: str):
    """Kullanıcı kimlik bilgilerini doğrular."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row and row[0] == password:
            return True
        return False
    except sqlite3.Error as e:
        print(f"Kullanıcı doğrulanırken hata oluştu: {e}")
        return False
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
            return df.iloc[0]  # İlk satırı pandas Series olarak döndür
        return None
    except sqlite3.Error as e:
        print(f"Hesaplama alınırken hata oluştu: {e}")
        return None
    finally:
        conn.close()

# Tabloları oluştur ve şemayı güncelle
create_hesaplamalar_table()
create_users_table()
add_kaynak_sayfa_column()  # Yeni sütunu ekle