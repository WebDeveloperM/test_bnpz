# BnpzTest — veb-versiya (2-bosqich)

Xodimlarni lavozimlar bo'yicha bilim testidan o'tkazish uchun veb-dastur.
Backend: **Django + Django REST Framework**. Frontend: **React (Vite)**.

Ishlaydigan imkoniyatlar: lavozim testlari, savol turlari (bir tanlovli, ko'p
tanlovli, to'g'ri/noto'g'ri, matn/raqam kiritish, bo'sh joyni to'ldirish,
tartiblash, moslashtirish/juftlash), savollarni bo'limlarga ajratish, savolga
rasm biriktirish, **oddiy TXT (yoki CSV) fayldan bir nechta savolni birdaniga
import qilish** (texnik bilim shart emas — savol yozib, to'g'ri javob oldiga
"+", noto'g'risiga "-" qo'yish kifoya), test rejimlari (Oddiy/Erkin/Jarima — ball ayirish/Maksimal — qat'iy nazorat) va
parametrlari (aralashtirish, vaqt chegarasi — butun test yoki har bir savol
uchun, savollarni tasodifiy tanlash, baho chegaralari, kirish so'zi, darhol
javob nazorati), savol og'irligiga (ball) qarab vaznli baholash, xodimlarni
parol bilan boshqarish, tayinlash va qidirish, xodim login (ism + parol),
testni topshirish (o'tkazib yuborish / bilmayman tugmalari, taymer, savol
takrorlanmasligi), server tomonda ball hisoblash, natijani saqlash, xodim
uchun to'liq tahlil, admin uchun har bir natijaning batafsil tahlili va
diagrammasi, natijalarni CSV formatda yuklab olish, namuna ma'lumot
yuklash/tozalash. Interfeys tili: o'zbek (lotin/kirill), rus.

**Administrator paneli — endi alohida sahifada** (`/admin`), Django admin panelga
kirish shart emas: shu yerdan testlar, savollar, xodimlar, natijalar va umumiy
sozlamalar (dastur nomi, admin paroli) to'liq boshqariladi.

---

## 1. Backend (Django)

Talab: Python 3.10+

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt

python manage.py migrate
python manage.py seed_demo            # namuna testlar va xodimlar (ixtiyoriy)
python manage.py runserver            # http://localhost:8000
```

Standart holatda mahalliy ishga tushirishda **SQLite** ishlatiladi. Docker
orqali ishga tushirilganda esa **PostgreSQL** avtomatik ulanadi (pastga
qarang) — katta hajmdagi ma'lumotlarda tezroq ishlaydi.

Admin panelning boshlang'ich paroli: **`admin123`** (muhit o'zgaruvchisi
`ADMIN_PASSWORD` orqali o'zgartiriladi, keyinchalik panelning o'zidan —
Sozlamalar bo'limidan — ham almashtirish mumkin).

**Namuna xodimlar (seed_demo dan keyin):**
- `Karimov Aziz` — parol `1234` (Buxgalter testi)
- `Soliyeva Nigora` — parol `1234` (Dispetcher testi)

---

## 2. Frontend (React)

Talab: Node.js 18+

```bash
cd frontend
npm install
npm run dev                           # http://localhost:5173
```

- `http://localhost:5173` — xodim uchun login sahifasi.
- `http://localhost:5173/admin` — administrator paneli (parol bilan kiriladi).

> Eslatma: frontend backendga `http://localhost:8000/api` manzili orqali ulanadi
> (`frontend/src/api.js` ichida). Backend boshqa manzilda bo'lsa, shuni o'zgartiring.

---

## 2.1. Docker orqali ishga tushirish

Talab: Docker va Docker Compose.

```bash
docker compose up --build
```

- Frontend (xodimlar uchun): `http://localhost:2000` (admin panel shu yerda ham
  ochiladi: `http://localhost:2000/admin`)
- **Admin panel — alohida port**: `http://localhost:2050` (to'g'ridan-to'g'ri
  administrator kirish sahifasi, `/admin` yozish shart emas — tarmoq darajasida
  xodimlar portidan ajratib qo'yish uchun)
- Backend (API): `http://localhost:8000`
- Ma'lumotlar bazasi: **PostgreSQL** (`db` xizmati), ma'lumotlar `pgdata`
  nomli Docker volume'da saqlanadi — konteynerlarni qayta ishga tushirish
  (`docker compose down` / `up`) ma'lumotlarni o'chirmaydi. Faqat
  `docker compose down -v` volume'ni ham o'chiradi (ehtiyot bo'ling).

---

## 2a. Administratorlar, rollar va ruxsatlar

Barcha administratorlar **bitta** kirish sahifasidan (`:2050`) o'z login-paroli
bilan kiradi. Alohida panel yoki alohida manzil yo'q — kim nimani ko'rishini
uning **roli** hal qiladi va panel menyusi shunga qarab yig'iladi.

- **Superuser** — rolga bog'liq emas, unga barcha bo'limlar har doim ochiq.
  Faqat u "Foydalanuvchilar" va "Rollar va ruxsatlar" bo'limlarini ko'radi.
- **Qolgan administratorlar** — har biriga bitta rol beriladi (masalan
  "Test administratori", "Uchebniy administrator"). Rolga qaysi bo'limlar
  ochiqligini superuser panel ichida, "Rollar va ruxsatlar" bo'limida
  belgilaydi — bu kodda yozilmagan, istalgan paytda o'zgartiriladi.
- **Rolsiz administrator** panelga kira olmaydi (kirishda tushunarli xabar
  chiqadi) — "hech narsa berilmagan" holat "hammasi ochiq"dan xavfsizroq.

Mavjud bo'limlar ro'yxati bitta joyda — `backend/core/perms.py`. Har bir
endpoint o'zining `required_permission` kaliti bilan **serverda** tekshiriladi
(`IsAdmin`), ya'ni menyudan bo'limni yashirish himoya emas: ruxsati yo'q
administrator API'ga to'g'ridan-to'g'ri murojaat qilsa ham 403 oladi.

Yangi bo'lim qo'shilganda: kalitni `perms.py` ga qo'shing, view'ga
`required_permission` yozing va `AdminDashboard.jsx` dagi `ALL_TABS` ga
qator qo'shing — uchalasi bir xil kalitga tayanadi.

---

## 3. Ishlash tartibi

1. Administrator `/admin` orqali parol bilan kiradi, test (lavozim) yaratadi va
   savollar qo'shadi — birma-bir yoki tayyor CSV fayldan birdaniga import
   qilib ("Namuna CSV" tugmasi orqali shablonni yuklab olish mumkin).
2. Administrator xodimni qo'shadi: ism-familiya, parol, biriktirilgan test, til.
3. Xodim boshqa kompyuterda frontend orqali ism + parol bilan kiradi.
4. Tizim unga biriktirilgan testni ochadi; kirish so'zi bo'lsa avval ko'rsatadi,
   so'ng xodim javob beradi.
5. Yakunda ball server tomonda (savol og'irligini hisobga olib) hisoblanadi,
   natija saqlanadi va tahlil ko'rsatiladi.
6. Xodim testni topshirgach, holati "topshirilgan"ga o'tadi — qayta kira olmaydi
   (administrator "Qayta biriktirish" tugmasi bilan qayta ochmaguncha).
7. Administrator Natijalar bo'limida barcha natijalarni ko'radi, har birining
   batafsil tahlili va diagrammasini ochadi, filtrlaydi va CSV formatda
   yuklab oladi.

---

## 4. Keyingi bosqichlar (TZ bo'yicha)

- Qo'shimcha savol turlari: rasmda joy belgilash.
- Bir necha formulировка (savolning bir necha ko'rinishi).
- Savol matnini formatlash (shrift, rang, ro'yxat, jadval) va formula muharriri.
- Testni bosma (qog'oz) ko'rinishida chiqarish.
- Natijalar jadvalini ustun bo'yicha saralash (hozir faqat lavozim bo'yicha filtr bor).
- Mobil qurilmalar uchun moslashuvchan (responsive) dizayn.
- Production uchun xavfsizlik sozlamalari (`DEBUG=False`, maxfiy `SECRET_KEY`,
  aniq `ALLOWED_HOSTS`) — hozir dev-rejimda ishlaydi.
- Video nazorat (proktoring): ekran va veb-kamera yozuvi, xavfsiz saqlash —
  alohida infratuzilma talab qiladi.
