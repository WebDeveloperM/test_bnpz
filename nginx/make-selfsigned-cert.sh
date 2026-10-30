#!/bin/sh
# Vaqtinchalik (self-signed) sertifikat yaratadi — HTTPS'ni DARHOL ishga tushirib,
# tekshirib ko'rish uchun. Xodimlar brauzerida "sayt xavfsiz emas" ogohlantirishi
# chiqadi; uni yo'qotish uchun ichki CA yoki haqiqiy sertifikatga o'tiladi
# (qarang: nginx/README.md). O'shanda nginx sozlamasi o'zgarmaydi — faqat shu
# papkadagi server.crt / server.key fayllari almashtiriladi.
#
# Ishlatish:   sh nginx/make-selfsigned-cert.sh 192.168.2.74
set -e

HOST="${1:-192.168.2.74}"
DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR"

# subjectAltName SHART: zamonaviy brauzerlar faqat CN'ga qaramaydi — manzil
# (IP yoki domen) aynan shu ro'yxatda bo'lishi kerak, aks holda sertifikat
# "noto'g'ri" deb hisoblanadi.
if echo "$HOST" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
  ALT="IP.1 = $HOST"
else
  ALT="DNS.1 = $HOST"
fi

CONF="$DIR/.openssl.cnf"
cat > "$CONF" <<EOF
[req]
distinguished_name = dn
x509_extensions    = v3
prompt             = no

[dn]
CN = $HOST
O  = BNPZ
OU = BnpzTest

[v3]
subjectAltName   = @alt
basicConstraints = CA:FALSE
keyUsage         = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt]
$ALT
DNS.9 = localhost
IP.9  = 127.0.0.1
EOF

# `-config` ishlatiladi (`-addext` emas) — eski openssl versiyalarida, jumladan
# Windows'dagi Git Bash bilan kelganida, `-addext` mavjud emas.
openssl req -x509 -nodes -newkey rsa:2048 -days 825 \
  -keyout "$DIR/server.key" -out "$DIR/server.crt" -config "$CONF"

rm -f "$CONF"
echo "Tayyor: $DIR/server.crt va server.key  (manzil: $HOST)"
echo "Endi:   docker compose up -d --build web"
