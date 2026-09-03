# Stacontrol

ETABS modellerinde TBDY 2018 / TS500 kontrollerini otomatikleştiren Streamlit
tabanlı web uygulaması: göreli kat ötelemesi, kolon kapasitesi, perde kapasitesi,
perde kesme, kiriş kesme ve metraj.

---

## Neden bir "ajan" var?

ETABS API'si **COM** üzerinden çalışır ve yalnızca ETABS'in kurulu olduğu
Windows makinesinde erişilebilir. Bir web sunucusu, ziyaretçinin bilgisayarındaki
ETABS'e doğrudan bağlanamaz — tarayıcılar da web sayfalarının yerel programlara
erişmesine izin vermez.

Çözüm: kullanıcı, bilgisayarında küçük bir **ajan** çalıştırır. Ajan yalnızca
**dışarı** doğru bağlantı kurar (kullanıcıda hiçbir port açılmaz), sunucudan
gelen okuma isteklerini yerine getirir ve tabloları geri gönderir. Hesaplama
sunucuda yapılır.

```
 Kullanıcının bilgisayarı                      Sunucu
┌───────────────────────┐                 ┌──────────────────────────┐
│  ETABS  ◄─COM─► ajan  │ ──HTTPS(giden)─►│  Köprü API'si  (:8500)   │
└───────────────────────┘   uzun yoklama  │        ▲                 │
                                          │        │ iç anahtar      │
      Tarayıcı ───────HTTPS──────────────►│  Streamlit     (:8501)   │
                                          └──────────────────────────┘
```

**Tasarımın kilit noktası:** `etabs_bridge/client.py` içindeki `RemoteSapModel`,
gerçek COM `SapModel` nesnesinin kullanılan alt kümesini **birebir taklit eder** —
aynı metot adları, aynı argümanlar, aynı dönüş demeti düzeni (`ret[2]` sütunlar,
`ret[4]` veri). Bu sayede sayfalardaki ~4000 satırlık hesap kodu hiç değişmedi;
yalnızca bağlantı satırı değişti:

```python
# önce (yalnızca aynı makinede çalışır)
etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
SapModel = etabs_object.SapModel

# şimdi
SapModel = connect_etabs(units=6)
```

---

## Proje yapısı

```
anasayfa.py                    Ana sayfa (ajan indirme butonu burada)
pages/                         Hesap sayfaları
  0_ETABS_Baglantisi.py        Ajan indirme + eşleştirme + durum
  1..6, metraj_hesaplama.py    Kontroller (ETABS erişimi köprü üzerinden)
database.py                    SQLite: kullanıcılar (bcrypt) + kayıtlı hesaplar
utils.py                       Oturum çerezleri, üst bar
sidebar.py                     Navigasyon + ajan durum rozeti

etabs_bridge/
  protocol.py                  Ortak tel formatı + izin verilen işlem listesi
  client.py                    RemoteSapModel (COM şekilli proxy) + HTTP taşıma
  streamlit_ui.py              connect_etabs(), eşleştirme paneli, durum çubuğu
  server/
    app.py                     FastAPI: ajan ve web uç noktaları
    store.py                   SQLite iş kuyruğu, oturum ve kiralama
    config.py                  Ortam değişkeni yapılandırması
  agent/
    agent.py                   Kullanıcının bilgisayarında çalışan istemci
    BASLAT.bat                 Başlatıcı (kurulum gerektirmez)
    OKUBENI.txt                Kullanıcı talimatları
  tools/build_agent.py         Dağıtılabilir zip üretir

deploy/                        systemd birimleri + nginx yapılandırması
tests/test_bridge_e2e.py       ETABS olmadan uçtan uca köprü testi
```

---

## Nerede barındırılır? (önemli)

Uygulama **iki servisten** oluşur ve ikisinin de dışarıdan erişilebilir olması
gerekir:

| Servis | Port | Kime açık olmalı |
|---|---|---|
| Streamlit web arayüzü | 8501 | Tarayıcıya |
| Köprü API'si | 8500 | **Ajana** (kullanıcının bilgisayarına) |

### ⚠️ Streamlit Community Cloud tek başına yetmez

Streamlit Community Cloud yalnızca tek bir süreç (`streamlit run`) çalıştırır ve
yalnızca Streamlit'in kendi HTTP/WebSocket ucunu yayınlar. **İkinci bir portu
dışarı açmanın yolu yoktur**, dolayısıyla ajanın bağlanacağı `/api/agent/poll`
adresi orada barındırılamaz. Ayrıca dosya sistemi kalıcı değildir: uygulama
uykuya daldığında veya yeniden dağıtıldığında `hesaplama_sonuc.db` sıfırlanır —
kullanıcı hesapları ve kayıtlı hesaplar silinir.

İki seçeneğiniz var:

**A) Karma kurulum — mevcut Streamlit Cloud adresinizi korursunuz**

Arayüz Streamlit Cloud'da kalır, köprüyü küçük bir yere koyarsınız
(Fly.io / Render / Railway / 5 USD'lik VPS — tek bir uvicorn süreci, çok hafif):

1. Köprüyü orada çalıştırın, kendisine bir HTTPS adresi verin
   (örn. `https://kopru.stacontrol.com`).
2. Streamlit Cloud'da **Manage app → Settings → Secrets** bölümüne
   `.streamlit/secrets.toml.example` içeriğini uyarlayarak yapıştırın;
   `BRIDGE_URL` köprünün genel adresi olmalı.
3. Ajan paketini o adresle üretin:
   `--bridge-url https://kopru.stacontrol.com`
4. Zip'i **GitHub Releases**'e yükleyip `AGENT_DOWNLOAD_URL` olarak verin
   (Streamlit Cloud'un statik klasörü depo ile birlikte dağıtıldığı için
   11 MB'lık zip'i repoya koymak istemezsiniz).

Kullanıcı veritabanı hâlâ geçici olur; kalıcılık için harici bir Postgres
(örn. Neon/Supabase ücretsiz katman) bağlayıp `database.py`'yi ona
yönlendirmeniz gerekir.

**B) Tek sunucu — önerilen**  
_Adım adım rehber: [deploy/KURULUM.md](deploy/KURULUM.md) — tek komutluk kurulum betiği dahil._

Her ikisini de kendi sunucunuzda çalıştırırsınız; `deploy/` klasöründeki
systemd birimleri ve nginx yapılandırması tam olarak bunun içindir. Veritabanı
kalıcı olur, ajan `https://siteniz.com/bridge` adresine bağlanır, tek alan adı,
tek sertifika. "Kendi web sitem üzerinde yayınlayacağım" hedefinize uyan yol
budur.

---

## Yerel geliştirme

```bash
pip install -r requirements-dev.txt
```

Windows'ta iki süreç birden:

```bash
calistir_gelistirme.cmd
```

Ajanı yerel köprüye bağlayarak denemek için (ETABS açıkken):

```bash
calistir_ajan_gelistirme.cmd
```

Testler (ETABS gerekmez — sahte bir `SapModel` kullanılır):

```bash
python -m pytest tests/ -v
```

---

## Üretime alma

### 1. Sırları üret

```bash
python -c "import secrets;print(secrets.token_urlsafe(32))"
```

İki farklı değer üretin: biri `BRIDGE_INTERNAL_KEY`, biri `COOKIES_PASSWORD`.
`/etc/stacontrol/stacontrol.env` dosyasına yazın (`.env.example` şablondur) ve
izinleri kısın:

```bash
sudo chmod 600 /etc/stacontrol/stacontrol.env
sudo chown stacontrol:stacontrol /etc/stacontrol/stacontrol.env
```

> `COOKIES_PASSWORD` değiştiğinde tüm kullanıcılar bir kez çıkış yapmış olur.
> Bu bilinçlidir: eski sürümde sabit bir varsayılan parola kullanılıyordu.

### 2. Kurulum

```bash
sudo useradd --system --home /opt/stacontrol stacontrol
sudo mkdir -p /opt/stacontrol /var/lib/stacontrol
sudo chown -R stacontrol:stacontrol /opt/stacontrol /var/lib/stacontrol

# kodu /opt/stacontrol içine kopyalayın, sonra:
cd /opt/stacontrol
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 3. Ajan paketini üret ve yayınla

```bash
python -m etabs_bridge.tools.build_agent --bridge-url https://stacontrol.com/bridge
cp dist/StacontrolAgent-1.0.0.zip static/StacontrolAgent.zip
```

`--bridge-url` değeri ajan paketine gömülür; **sitenizin gerçek adresi** olmalıdır.

### 4. Servisler ve nginx

```bash
sudo cp deploy/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now stacontrol-bridge stacontrol-web

sudo cp deploy/nginx-stacontrol.conf /etc/nginx/sites-available/stacontrol
sudo ln -s /etc/nginx/sites-available/stacontrol /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

`nginx-stacontrol.conf` içindeki `proxy_read_timeout 300s` **kritiktir**: ajan
25 saniyelik uzun yoklama yapar ve büyük modellerde tablo okuma dakikalar
sürebilir. Kısa bir zaman aşımı istekleri 504 ile keser.

### 5. Doğrulama

```bash
curl -s https://stacontrol.com/bridge/healthz
# {"ok":true,"version":"1.0.0","agents_total":0,...}
```

---

## Ölçekleme notları

* Köprüyü **tek işçi (worker)** ile çalıştırın. Süreç içi uyandırma olayları
  süreçler arası paylaşılmaz; birden fazla işçiyle sistem yine doğru çalışır ama
  her istekte 0,25 sn'ye kadar ek gecikme oluşur. İstekler G/Ç ağırlıklı olduğu
  için tek işçi binlerce ajanı taşır.
* Durum SQLite'ta tutulur (WAL). Tek sunucu için yeterlidir. Birden fazla
  sunucuya yayılmak gerekirse yalnızca `etabs_bridge/server/store.py` değişir;
  arayüz aynı kalır.
* Kullanıcı verisi (`hesaplama_sonuc.db`) da SQLite'tır. Eşzamanlı kullanıcı
  sayısı arttıkça PostgreSQL'e taşımak gerekir; `database.py` bunun tek noktasıdır.

---

## Güvenlik

| Alan | Uygulama |
|---|---|
| Ajan yetkileri | `protocol.ALLOWED_OPS` beyaz listesi. Sunucu ele geçirilse bile ajana kod çalıştırtılamaz; dosya okuma/yazma veya model değiştirme yeteneği yoktur. |
| Ağ yönü | Ajan yalnızca giden bağlantı kurar. Kullanıcıda port açılmaz. |
| Ajan kimliği | Kayıtta üretilen jeton; sunucuda yalnızca SHA-256 özeti saklanır. |
| Eşleştirme | 6 haneli, 10 dakika geçerli, tek kullanımlık kod. Kayıt uç noktası IP başına hız sınırlı. |
| Web ↔ köprü | `BRIDGE_INTERNAL_KEY` ile sunucudan sunucuya; tarayıcıya asla gönderilmez. |
| Model verisi | Sonuç bir kez okunur ve silinir; sunucuda kalıcı olarak tutulmaz. |
| Parolalar | bcrypt (maliyet 12). Eski SHA-256 kayıtları ilk girişte sessizce yükseltilir. |
| Oturum | Şifreli çerez; anahtar ortam değişkeninden, varsayılan parola yok. |
| Eşzamanlılık | Ajan üzerinde kiralama; iki sekme aynı anda farklı kombinasyon seçip yanlış tablo okuyamaz. |

### İmzalama hakkında

Paket **PyInstaller .exe değil**, python.org'un embeddable dağıtımı + düz metin
`.bat` başlatıcıdır. Çalışan ikili (`python.exe`) Python Software Foundation
tarafından imzalıdır ve kullanıcı `agent.py` ile `BASLAT.bat` içeriğini okuyabilir.
Yine de zip internetten indiği için Windows bir kez uyarı gösterebilir. Bunu
tamamen kaldırmak isterseniz OV kod imzalama sertifikası (yıllık ~200-400 USD)
alıp `BASLAT.bat` yerine imzalı bir başlatıcı dağıtmanız gerekir.

---

## Bilinen sınırlar

* Ajan yalnızca Windows'ta çalışır (ETABS COM gereksinimi).
* Kullanıcı başına aynı anda **tek** ajan oturumu desteklenir; yeni eşleştirme
  öncekini düşürür.
* Okunan tablolar varsayılan 300 saniye önbelleklenir. ETABS'te analizi yeniden
  çalıştırdıysanız sayfa üstündeki **↻ Verileri yenile** düğmesine basın.
* `GetAvailableTables` köprüde uygulanmıştır ancak hiçbir sayfa kullanmaz; gerçek
  ETABS ile doğrulanmamıştır.
