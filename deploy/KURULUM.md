# Kurulum Rehberi

## Önce şunu bilin: paylaşımlı hosting bu uygulamayı çalıştıramaz

`axial.com.tr` şu anda **GüzelHosting paylaşımlı hosting**'inde duruyor
(`Server: LiteSpeed`, cPanel tipi ortam). Bu uygulama orada çalışamaz — bu bir
yapılandırma eksikliği değil, ortamın yapısal sınırı:

| Gereksinim | Paylaşımlı hosting |
|---|---|
| Sürekli çalışan Python süreci (Streamlit) | ❌ Yok. Süreçler istek bitince sonlanır. |
| WebSocket (Streamlit'in çalışma şekli) | ❌ Desteklenmez. |
| İkinci bir servis (köprü, 8500) | ❌ Kendi portunuzu açamazsınız. |
| 25 saniye açık kalan istek (uzun yoklama) | ❌ LiteSpeed zaman aşımıyla keser. |
| systemd / root erişimi | ❌ Yok. |

cPanel'deki "Setup Python App" özelliği de kurtarmaz: o Passenger/WSGI içindir;
Streamlit WSGI değildir ve boştaki süreçler kapatılır.

## Ama alan adınızı koruyabilirsiniz

Çözüm basit: küçük bir sunucu kiralayın ve **alt alan adını** ona yönlendirin.
Ana siteniz (`axial.com.tr`) paylaşımlı hostingde kalmaya devam eder.

```
axial.com.tr              →  mevcut paylaşımlı hosting (dokunulmaz)
stacontrol.axial.com.tr   →  yeni sunucu (Stacontrol burada çalışır)
```

Kullanıcı açısından hepsi sizin alan adınızdır; marka bütünlüğü bozulmaz.

### Sunucu seçenekleri

Uygulama hafiftir; 2 GB RAM fazlasıyla yeter.

| Sağlayıcı | Ürün | Yaklaşık aylık |
|---|---|---|
| GüzelHosting | Sanal Sunucu (VPS) | mevcut sağlayıcınızda kalırsınız, tek fatura |
| Hetzner | CX22 (2 vCPU / 4 GB) | ~4 EUR |
| DigitalOcean | Basic Droplet (1 GB) | ~6 USD |
| Contabo | VPS S | ~5 EUR |

Ubuntu 22.04 veya 24.04 seçin.

---

## Adım adım

### 1. DNS kaydını ekleyin

GüzelHosting panelinde `axial.com.tr` için bir **A kaydı** ekleyin:

| Tip | Ad | Değer |
|---|---|---|
| A | `stacontrol` | sunucunuzun IP adresi |

Yayılması genellikle birkaç dakika, bazen birkaç saat sürer. Kontrol:

```bash
nslookup stacontrol.axial.com.tr
```

### 2. Sunucuya bağlanın ve kodu çekin

```bash
ssh root@SUNUCU_IP
apt update && apt install -y git
git clone https://github.com/eminsade/Stacontrol.git
cd Stacontrol
```

### 3. Kurulum betiğini çalıştırın

```bash
sudo bash deploy/kurulum.sh stacontrol.axial.com.tr
```

Betik sırasıyla: paketleri kurar, `stacontrol` kullanıcısını oluşturur, sanal
ortamı hazırlar, **sırları üretir**, ajan paketini doğru adresle derler,
systemd servislerini başlatır, nginx'i yapılandırır ve Let's Encrypt
sertifikasını alır. Tekrar çalıştırmak güvenlidir; mevcut sırlar korunur.

### 4. Doğrulayın

```bash
curl -s https://stacontrol.axial.com.tr/bridge/healthz
# {"ok":true,"version":"1.0.0","agents_total":0,...}

systemctl status stacontrol-bridge stacontrol-web
```

Tarayıcıdan `https://stacontrol.axial.com.tr` adresini açın, kayıt olun, ana
sayfadaki **⬇️ ETABS Ajanını İndir** butonuyla ajanı indirip deneyin.

---

## Güncelleme

```bash
cd ~/Stacontrol && git pull
sudo bash deploy/kurulum.sh stacontrol.axial.com.tr
```

Sırlar ve veritabanı korunur (`/etc/stacontrol/stacontrol.env`,
`/var/lib/stacontrol/`).

## Sorun giderme

**Servis açılmıyor**
```bash
journalctl -u stacontrol-bridge -n 50 --no-pager
journalctl -u stacontrol-web -n 50 --no-pager
```

**Sertifika alınamadı** — DNS henüz yayılmamıştır. Yayıldıktan sonra:
```bash
sudo certbot --nginx -d stacontrol.axial.com.tr
```

**Ajan bağlanıyor ama tablo okurken zaman aşımı** — nginx'te
`proxy_read_timeout 300s` satırının durduğundan emin olun. Büyük modellerde
tablo okuma dakikalar sürebilir.

**Ajan hiç bağlanmıyor** — kullanıcının ağı `https://stacontrol.axial.com.tr`
adresine çıkabiliyor mu? Ajan paketindeki `agent_config.json` içinde doğru
adres yazıyor mu? (Betik bunu otomatik yazar.)

---

## Streamlit Community Cloud'daki mevcut uygulama ne olacak?

Kurulum tamamlandıktan sonra ona ihtiyacınız kalmaz. İsterseniz Streamlit
Cloud'daki uygulamayı silin ya da bırakın — ama **köprü orada çalışamayacağı
için ETABS bağlantısı o adreste hiçbir zaman işlemez**; kullanıcıları yeni
adrese yönlendirin.

> Not: Streamlit Cloud'un dosya sistemi kalıcı olmadığı için oradaki kullanıcı
> hesapları ve kayıtlı hesaplamalar zaten her yeniden dağıtımda sıfırlanıyordu.
> Yeni sunucuda veritabanı `/var/lib/stacontrol/` altında kalıcıdır.
