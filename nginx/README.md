# HTTPS (nginx) — sozlash va sertifikat

## Nega kerak

Brauzer kamera va ekran ulashishga (`getUserMedia` / `getDisplayMedia`) faqat
**xavfsiz kontekstda** ruxsat beradi — bu esa amalda HTTPS yoki `localhost`
degani. Shu sababli hozirgacha har bir test kompyuterida `chrome://flags`
sozlamasini qo'lda o'zgartirishga to'g'ri kelardi. HTTPS bu ehtiyojni butunlay
yo'q qiladi: yuz orqali kirish ham, video nazorat ham hech qanday sozlamasiz
ishlaydi.

## Tuzilma

```
https://<server>:2000/            xodim ilovasi
https://<server>:2000/api/...     Django API
https://<server>:2000/media/...   yuklangan fayllar (rasm, video)
https://<server>:2050/            admin paneli
https://<server>:2050/it-center/  Django admin (dasturchi uchun)

http://<server>:2000  →  https://<server>:2000   (avtomatik)
http://<server>:2050  →  https://<server>:2050   (avtomatik)
http://<server>       →  https://<server>:2000   (avtomatik)
```

Portlar avvalgidek qoldi — xodimlarning yorliqlari o'zgarmaydi, faqat protokol
`http` dan `https` ga o'tdi. Eski `http://` havolalar avtomatik yo'naltiriladi.

**Backend (8000) tashqariga chiqarilmagan** — unga faqat nginx konteyner tarmog'i
ichidan murojaat qilinadi, ya'ni API'ga http orqali to'g'ridan-to'g'ri kirib
bo'lmaydi.

Hamma narsa **bitta manzil** ostida bo'lgani uchun ilova kodida host ham, port
ham yozilmagan (nisbiy `/api`). Bu HTTPS uchun shart: aks holda sahifa https'da,
API esa http'da bo'lib, brauzer so'rovlarni "mixed content" deb bloklaydi.

## Ishga tushirish

```bash
sh nginx/make-selfsigned-cert.sh 192.168.2.74
docker compose up -d --build web
```

Birinchi buyruqdagi manzil — serverning LAN IP'si yoki domen nomi. Sertifikat
`nginx/certs/` ichida yaratiladi (repozitoriyga tushmaydi).

## Sertifikat: uchta yo'l

nginx sozlamasi uchala holatda ham **bir xil** — faqat `nginx/certs/server.crt`
va `server.key` fayllari almashadi, so'ng `docker compose restart web`.

### 1. Self-signed (hozirgi holat)

Darhol ishlaydi, hech narsa talab qilmaydi. Kamchiligi: brauzer sertifikatni
imzolagan markazni tanimaydi (`ERR_CERT_AUTHORITY_INVALID`) va "Bu sayt xavfsiz
emas" ogohlantirishini ko'rsatadi.

Ikki yo'l bor:

**a) Ogohlantirishni har safar o'tkazib yuborish.** "Qo'shimcha → Davom etish".
Test ishlaydi, kamera ham ochiladi — lekin xodimlar chalkashadi va ba'zi
korporativ siyosatlar bunga yo'l qo'ymaydi.

**b) Sertifikatni ishonchli qilib qo'yish** — ogohlantirish butunlay yo'qoladi.

Kompyuterlar **domenda** bo'lsa, buni bir marta markazdan qilish mumkin —
sertifikat markazi (CA) qurish SHART EMAS, mavjud `server.crt` ning o'zi
tarqatiladi:

```
Group Policy Management → domen siyosati → Edit
Computer Configuration → Policies → Windows Settings → Security Settings
  → Public Key Policies → Trusted Root Certification Authorities
  → Import → server.crt
```

Shundan keyin domendagi barcha kompyuterlarda ogohlantirish chiqmaydi va
xodim tomonida hech narsa sozlanmaydi.

Domen bo'lmasa (yoki kompyuter kam bo'lsa) — har biriga qo'lda, administrator
huquqi bilan:

```powershell
Import-Certificate -FilePath server.crt -CertStoreLocation Cert:\LocalMachine\Root
```

Faqat `server.crt` ko'chiriladi. **`server.key` (maxfiy kalit) hech qachon
serverdan chiqmasligi kerak.**

> **Diqqat:** sertifikat server IP manziliga bog'langan. IP o'zgarsa (DHCP)
> sertifikat yaroqsiz bo'ladi — serverga **statik IP** berilishi tavsiya etiladi.

### 2. Korxonaning ichki CA'si (domen va CA infratuzilmasi bo'lsa)

IT bo'limi korxona sertifikat markazidan server uchun sertifikat beradi va CA
ildiz sertifikatini Group Policy orqali tarqatadi. 1(b) usulidan farqi: sertifikat
muddati tugaganda yangisini olish osonroq va bu boshqa ichki xizmatlar uchun
ham ishlaydi. Sertifikatda `subjectAltName` da server IP'si yoki nomi albatta
ko'rsatilishi kerak — brauzerlar faqat CN'ga qaramaydi.

### 3. Haqiqiy sertifikat (Let's Encrypt, DNS-01)

Korxona domeni bo'lsa (masalan `test.bnpz.uz`) — bepul va avtomatik
yangilanadigan sertifikat. Server internetga chiqarilmaydi: tasdiqlash DNS
yozuvi orqali o'tadi. Ichki DNS shu nomni server IP'siga yo'naltiradi.

## Muhit o'zgaruvchilari (.env) — yagona IP manbai

Loyihaning BARCHA server-manzillari `docker-compose.yml` yonidagi `.env` faylida.
Serverga ko'chirganda faqat shu faylni tahrirlang (namuna: `.env.example`).
Odatda ikki qatorni to'g'rilash yetarli — qolgani shulardan yig'iladi:

```
# 1) Shu serverning IP'si (jonli ekran/TURN shu orqali ishlaydi)
SERVER_IP=192.168.2.74
# 2) BnpzId (employee_service) manzili — host:port
BNPZID_HOST=192.168.2.74:5000

EMPLOYEE_SERVICE_API_KEY=<BnpzId API kaliti>
DJANGO_SECRET_KEY=<uzun tasodifiy satr>
DJANGO_DEBUG=0
```

`SERVER_IP` bir vaqtning o'zida TURN (`TURN_EXTERNAL_IP`) va Django CSRF ishonchli
manzillarini (`https://SERVER_IP:2000`, `:2050`) ham belgilaydi — ular avtomatik
yig'iladi. Korxona domeni bo'lsa (`test.bnpz.uz`), CSRF ni qo'lda ustiga yozing:
`DJANGO_CSRF_TRUSTED_ORIGINS=https://test.bnpz.uz`.

`DJANGO_SECRET_KEY` — eng muhimi: administrator seans tokenlari shu kalit bilan
imzolanadi. Kalitni yaratish:

```bash
docker compose exec backend python -c "import secrets; print(secrets.token_urlsafe(64))"
```

## Ishlab chiqish rejimi

Vite dev-serveri ishlab chiqarishda ishga tushmaydi (u `dev` profilida).
Ishlab chiqish uchun kerak bo'lsa:

```bash
docker compose --profile dev up -d frontend admin
# xodim: http://localhost:5173    admin: http://localhost:5174
```

Ular 5173/5174 portlarida — 2000/2050 ni band qilmaydi, shu sabab nginx bilan
bir vaqtda ishlay oladi.

## Eslatma: TURN (jonli ekran)

`coturn` o'z holicha qoladi — WebRTC ulanishlari "mixed content" qoidasiga
tushmaydi, shuning uchun HTTPS sahifadan oddiy TURN serveriga ulanish ishlaydi.
