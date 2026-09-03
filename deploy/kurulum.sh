#!/usr/bin/env bash
#
# Stacontrol - Ubuntu/Debian sunucusuna tek komutla kurulum
#
# Kullanim (sunucuda, root olarak):
#   sudo bash deploy/kurulum.sh stacontrol.axial.com.tr
#
# Ne yapar:
#   1. Gerekli paketleri kurar (python3-venv, nginx, certbot)
#   2. stacontrol kullanicisini ve dizinleri olusturur
#   3. Kodu /opt/stacontrol icine kopyalar, sanal ortam kurar
#   4. Sirlari URETIR ve /etc/stacontrol/stacontrol.env icine yazar
#      (dosya varsa mevcut sirlar KORUNUR)
#   5. systemd birimlerini ve nginx yapilandirmasini kurar
#   6. Let's Encrypt sertifikasi alir
#   7. Ajan paketini dogru adresle uretir ve indirilebilir hale getirir
#
# Betik idempotenttir: tekrar calistirmak guvenlidir.

set -euo pipefail

DOMAIN="${1:-}"
APP_USER="stacontrol"
APP_DIR="/opt/stacontrol"
STATE_DIR="/var/lib/stacontrol"
ENV_DIR="/etc/stacontrol"
ENV_FILE="${ENV_DIR}/stacontrol.env"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bilgi() { printf '\033[1;34m[kurulum]\033[0m %s\n' "$*"; }
uyari() { printf '\033[1;33m[uyari]\033[0m %s\n' "$*"; }
hata()  { printf '\033[1;31m[hata]\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# On kontroller
# ---------------------------------------------------------------------------
[[ $EUID -eq 0 ]] || hata "Bu betik root olarak calistirilmali: sudo bash $0 <alan-adi>"
[[ -n "$DOMAIN" ]] || hata "Alan adi verilmedi. Ornek: sudo bash $0 stacontrol.axial.com.tr"
command -v apt-get >/dev/null || hata "Bu betik Ubuntu/Debian icindir."

bilgi "Alan adi : ${DOMAIN}"
bilgi "Kaynak   : ${SRC_DIR}"

# DNS kontrolu -- sertifika alinabilmesi icin alan adi bu sunucuyu gostermeli
SUNUCU_IP="$(curl -fsS --max-time 10 https://api.ipify.org || echo '')"
ALAN_IP="$(getent hosts "$DOMAIN" | awk '{print $1}' | head -1 || echo '')"
if [[ -n "$SUNUCU_IP" && -n "$ALAN_IP" && "$SUNUCU_IP" != "$ALAN_IP" ]]; then
    uyari "DNS uyusmuyor: ${DOMAIN} -> ${ALAN_IP}, bu sunucu -> ${SUNUCU_IP}"
    uyari "Alan adi saglayicinizda (GuzelHosting panelinde) A kaydini bu sunucuya"
    uyari "yonlendirin, yayilmasini bekleyin, sonra betigi tekrar calistirin."
    uyari "Sertifika adimi atlanacak; digerleri kurulmaya devam edecek."
    SERTIFIKA_AL=0
elif [[ -z "$ALAN_IP" ]]; then
    uyari "${DOMAIN} icin DNS kaydi bulunamadi. Sertifika adimi atlanacak."
    SERTIFIKA_AL=0
else
    SERTIFIKA_AL=1
fi

# ---------------------------------------------------------------------------
# 1. Paketler
# ---------------------------------------------------------------------------
bilgi "Paketler kuruluyor..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx curl certbot python3-certbot-nginx

# ---------------------------------------------------------------------------
# 2. Kullanici ve dizinler
# ---------------------------------------------------------------------------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    bilgi "Kullanici olusturuluyor: ${APP_USER}"
    useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
mkdir -p "$APP_DIR" "$STATE_DIR" "$ENV_DIR"

# ---------------------------------------------------------------------------
# 3. Kod ve sanal ortam
# ---------------------------------------------------------------------------
bilgi "Kod kopyalaniyor -> ${APP_DIR}"
# Sanal ortami ve durum dosyalarini ezmemek icin secici kopyalama
tar -C "$SRC_DIR" \
    --exclude='.git' --exclude='.venv' --exclude='dist' --exclude='__pycache__' \
    --exclude='*.db' --exclude='.env' \
    -cf - . | tar -C "$APP_DIR" -xf -

if [[ ! -d "${APP_DIR}/.venv" ]]; then
    bilgi "Sanal ortam olusturuluyor..."
    python3 -m venv "${APP_DIR}/.venv"
fi
bilgi "Bagimliliklar kuruluyor (birkac dakika surebilir)..."
"${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/requirements.txt"

# ---------------------------------------------------------------------------
# 4. Sirlar
# ---------------------------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
    bilgi "Mevcut ${ENV_FILE} korunuyor (sirlar yeniden uretilmedi)."
    # BRIDGE_URL/PUBLIC_BRIDGE_URL alan adi degistiyse guncellensin
    sed -i "s|^PUBLIC_BRIDGE_URL=.*|PUBLIC_BRIDGE_URL=https://${DOMAIN}/bridge|" "$ENV_FILE"
    sed -i "s|^AGENT_DOWNLOAD_URL=.*|AGENT_DOWNLOAD_URL=https://${DOMAIN}/indir/StacontrolAgent.zip|" "$ENV_FILE"
else
    bilgi "Sirlar uretiliyor -> ${ENV_FILE}"
    INTERNAL_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
    COOKIE_KEY="$(python3 -c 'import secrets;print(secrets.token_urlsafe(32))')"
    cat > "$ENV_FILE" <<EOF
# Stacontrol - uretim ortam degiskenleri
# Bu dosya kurulum betigi tarafindan uretildi. Sirlari kimseyle paylasmayin.

BRIDGE_INTERNAL_KEY=${INTERNAL_KEY}
COOKIES_PASSWORD=${COOKIE_KEY}

BRIDGE_URL=http://127.0.0.1:8500
PUBLIC_BRIDGE_URL=https://${DOMAIN}/bridge
AGENT_DOWNLOAD_URL=https://${DOMAIN}/indir/StacontrolAgent.zip

STACONTROL_DB=${STATE_DIR}/hesaplama_sonuc.db
BRIDGE_DB=${STATE_DIR}/bridge_state.db
EOF
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

# ---------------------------------------------------------------------------
# 5. Ajan paketi
# ---------------------------------------------------------------------------
bilgi "Ajan paketi uretiliyor (bridge-url: https://${DOMAIN}/bridge)..."
(
    cd "$APP_DIR"
    "${APP_DIR}/.venv/bin/python" -m etabs_bridge.tools.build_agent \
        --bridge-url "https://${DOMAIN}/bridge" >/dev/null
)
mkdir -p "${APP_DIR}/static"
cp "${APP_DIR}"/dist/StacontrolAgent-*.zip "${APP_DIR}/static/StacontrolAgent.zip"
bilgi "Ajan paketi hazir: ${APP_DIR}/static/StacontrolAgent.zip"

chown -R "$APP_USER":"$APP_USER" "$APP_DIR" "$STATE_DIR"

# ---------------------------------------------------------------------------
# 6. systemd
# ---------------------------------------------------------------------------
bilgi "systemd birimleri kuruluyor..."
cp "${APP_DIR}/deploy/stacontrol-bridge.service" /etc/systemd/system/
cp "${APP_DIR}/deploy/stacontrol-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now stacontrol-bridge stacontrol-web
systemctl restart stacontrol-bridge stacontrol-web

# ---------------------------------------------------------------------------
# 7. nginx
# ---------------------------------------------------------------------------
bilgi "nginx yapilandiriliyor..."
sed "s|__DOMAIN__|${DOMAIN}|g" \
    "${APP_DIR}/deploy/nginx-stacontrol.conf" > /etc/nginx/sites-available/stacontrol

# Sertifika henuz yokken nginx acilmasin diye TLS bloklarini gecici olarak
# devre disi birak; certbot basariyla calisinca geri acilir.
if [[ ! -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]]; then
    sed -i -e "s|^\( *ssl_certificate\)|#\1|" /etc/nginx/sites-available/stacontrol
    sed -i -e "s|listen 443 ssl;|listen 443;|" -e "s|listen \[::\]:443 ssl;|listen [::]:443;|" \
        -e "s|^ *http2 on;|    # http2 on;|" /etc/nginx/sites-available/stacontrol
fi

ln -sf /etc/nginx/sites-available/stacontrol /etc/nginx/sites-enabled/stacontrol
rm -f /etc/nginx/sites-enabled/default
mkdir -p /var/www/certbot
nginx -t && systemctl reload nginx

# ---------------------------------------------------------------------------
# 8. Sertifika
# ---------------------------------------------------------------------------
if [[ "$SERTIFIKA_AL" -eq 1 ]]; then
    bilgi "Let's Encrypt sertifikasi aliniyor..."
    if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos \
        --register-unsafely-without-email --redirect; then
        bilgi "Sertifika alindi."
    else
        uyari "Sertifika alinamadi. DNS yayildiktan sonra su komutu calistirin:"
        uyari "  sudo certbot --nginx -d ${DOMAIN}"
    fi
fi

# ---------------------------------------------------------------------------
# Ozet
# ---------------------------------------------------------------------------
echo
bilgi "================= KURULUM TAMAMLANDI ================="
echo
bilgi "Site      : https://${DOMAIN}"
bilgi "Kopru     : https://${DOMAIN}/bridge/healthz"
bilgi "Ajan indir: https://${DOMAIN}/indir/StacontrolAgent.zip"
echo
bilgi "Durum kontrolu:"
echo "  systemctl status stacontrol-bridge stacontrol-web"
echo "  curl -s https://${DOMAIN}/bridge/healthz"
echo
bilgi "Kayitlari izlemek icin:"
echo "  journalctl -u stacontrol-bridge -f"
echo "  journalctl -u stacontrol-web -f"
echo
uyari "Sirlar ${ENV_FILE} icinde. Yedekleyin; COOKIES_PASSWORD degisirse"
uyari "tum kullanicilar bir kez cikis yapmis olur."
