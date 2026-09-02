"""
STACONT - Ortak Mühendislik ve Malzeme Sabitleri
Tüm sayfalar tarafından paylaşılan beton, çelik, perde ve yük katsayıları tanımları.
"""

# Beton Sınıfları ve Karakteristik Basınç Dayanımları (fck kPa cinsinden)
CONCRETE_OPTIONS = {
    "C16": 16000,
    "C18": 18000,
    "C20": 20000,
    "C25": 25000,
    "C30": 30000,
    "C35": 35000,
    "C40": 40000,
    "C45": 45000,
    "C50": 50000,
    "C55": 55000,
    "C60": 60000
}

# Çelik Sınıfları ve Akma Dayanımları (fyk kPa cinsinden)
STEEL_OPTIONS = {
    "S420": 420000,
    "B420C": 420000,
    "B500C": 500000
}

# Perde Boşluklu / Boşluksuz Katsayıları (TBDY 2018 Denk. 7.18)
BOSLUK_OPTIONS = {
    "Boşluksuz Perde: 0.85": 0.85,
    "Boşluklu Perde: 0.65": 0.65
}

# Perde Dinamik Büyütme Katsayısı (Bv) (TBDY 2018 Denk. 7.16)
BV_OPTIONS = {
    "Deprem Yükünün Tamamı Perdelerde: 1": 1.0,
    "Deprem Yükü Paylaşılıyor: 1.5": 1.5
}

# Varsayılan Köprü (Bridge) Ayarları
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765
BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"
