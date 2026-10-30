import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Ishga tushirishdan oldin muhit o'zgaruvchilari orqali beriladi (.env fayl).
#
# DIQQAT: SECRET_KEY administrator seans tokenlarini IMZOLAYDI. Uni kodda
# qoldirish — kod ko'ra oladigan har kim o'ziga admin token yasay olishi degani.
# Ishlab chiqarishda albatta DJANGO_SECRET_KEY berilishi kerak.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

# --- Teskari proksi (nginx) ortida ishlash ---------------------------------
# nginx TLS'ni yakunlab, backend'ga oddiy HTTP orqali murojaat qiladi. Busiz
# Django so'rovni HTTP deb hisoblab, fayllarga havolalarni (build_absolute_uri —
# savol rasmlari, video yozuvlar) http:// bilan yasardi va brauzer ularni HTTPS
# sahifada "mixed content" sifatida bloklardi.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Django admin (/it-center) formalari uchun: CSRF tekshiruvi Origin'ni shu
# ro'yxat bilan solishtiradi. HTTPS manzillar bu yerda ko'rsatilishi shart.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "bnpztest_api.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bnpztest_api.wsgi.application"

# Yagona baza — PostgreSQL. Ilgari bu yerda SQLite'ga "zaxira yo'l" bor edi:
# `DB_ENGINE` berilmasa, Django jim ravishda SQLite fayliga o'tib ketardi va
# BUTUNLAY BOSHQA, bo'sh bazani ko'rsatardi — tashqaridan bu "ma'lumotlar
# yo'qolgan" bo'lib ko'rinardi. Endi bunday holat yo'q: sozlama noto'g'ri
# bo'lsa, ilova jim ishlashda davom etmaydi.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "mytest"),
        "USER": os.environ.get("DB_USER", "mytest"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "mytest"),
        "HOST": os.environ.get("DB_HOST", "db"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        # 0 = ulanish har so'rovdan keyin yopiladi. BU QIYMAT SHUNDAY QOLISHI
        # KERAK — 60 ga qo'yib ko'rildi va ZARAR qildi.
        #
        # O'lchangan. Foydasi umuman yo'q edi (30 ta so'rov):
        #   CONN_MAX_AGE=0  -> 29 ta yangi ulanish, median 51.6 ms
        #   CONN_MAX_AGE=60 -> 29 ta yangi ulanish, median 47.6 ms
        # Chunki `runserver` har so'rovga YANGI OQIM yaratadi, Django esa
        # ulanishni oqimga bog'lab saqlaydi — yangi oqim baribir yangi ulanish
        # ochadi.
        #
        # Zarari esa aniq: ulanish so'rov tugagach yopilmay, oqim o'lguncha
        # ushlanib turadi. Yuk ostida ular to'planib, Postgres chegarasiga
        # (max_connections=100) yetadi. Sinovda 98 ga chiqdi va 773 ta so'rov
        # 500 bilan yiqildi.
        #
        # Diqqat — xato ALDAMCHI ko'rinishda chiqadi. Postgres "ulanishlar
        # tugadi" xabarini o'z tilida (cp1251) qaytaradi, psycopg2 uni UTF-8
        # deb o'qiydi va natijada traceback'da
        #   UnicodeDecodeError: 'utf-8' codec can't decode byte 0xc2 ...
        # ko'rinadi. Bu kodlash muammosi EMAS, ulanishlar tugagani.
        #
        # Oqimlarni qayta ishlatadigan serverga (gunicorn --threads) o'tilsa,
        # bu sozlamani qayta ko'rib chiqish mumkin — lekin faqat o'lchov bilan.
        "CONN_MAX_AGE": 0,
        # Qayta ishlatilayotgan ulanish uzilib qolgan bo'lishi mumkin (baza
        # qayta ishga tushgan, tarmoq uzilgan). Django uni so'rov boshida
        # tekshiradi va kerak bo'lsa jimgina qaytadan ochadi — busiz birinchi
        # so'rov "server ishlamayapti" xatosi bilan qaytardi.
        "CONN_HEALTH_CHECKS": True,
    }
}

# Server xatolari (500) konsolga — ya'ni `docker compose logs backend` ga tushsin.
#
# Django'ning standart sozlamasida xato xabarlari `require_debug_true` filtri
# ortida turadi: DEBUG=0 bo'lishi bilan ular KONSOLGA UMUMAN CHIQMAYDI va
# faqat `mail_admins` orqali yuboriladi — pochta esa sozlanmagan. Amalda bu
# shuni anglatardi: ishlab chiqarishda 500 xatosi yuz bersa, jurnalda faqat
# `"... HTTP/1.1" 500 145` qatori qolardi, sababi esa butunlay yo'qolardi.
#
# Yuk sinovida aynan shunga duch keldik: 32 ta 500 xatosi bor edi, lekin
# nima uchunligini bilishning imkoni yo'q edi.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        # So'rov ichidagi ushlanmagan xatolar — to'liq traceback bilan.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        # Baza bilan bog'liq muammolar (ulanish tugashi, uzilish).
        "django.db.backends": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Frontend (React) dev serveridan so'rovlarga ruxsat. Ishlab chiqarishda aniq manzil qo'ying.
CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    # Standart autentifikatsiya ATAYLAB bo'sh qoldirilgan.
    #
    # Ko'rsatilmasa, DRF o'zining standart ro'yxatini (SessionAuthentication va
    # BasicAuthentication) qo'llaydi. SessionAuthentication esa brauzerda Django
    # sessiyasi bo'lsa CSRF token talab qiladi. Amalda bu shunday ko'rinardi:
    # administrator /it-center (Django admin) ga kirgach, brauzerda `sessionid`
    # cookie paydo bo'ladi; cookie'lar PORTNI AJRATMAYDI, shuning uchun u xodim
    # ilovasiga (boshqa port, o'sha host) ham yuboriladi va xodimning oddiy
    # so'rovi — masalan yuz orqali kirish — 403 Forbidden bilan rad etilardi.
    #
    # Bu yerda sessiyaga asoslangan autentifikatsiya umuman kerak emas:
    # administrator endpointlari `AdminTokenAuthentication` ni o'zi e'lon qiladi,
    # xodim endpointlari esa so'rov ichidagi seans tokeni bilan ishlaydi.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
}

# Tashqi "employee_service" loyihasi bilan integratsiya (yuz orqali kirish uchun
# xodimlar ro'yxati va rasmlarini olib turadi). Kalit faqat o'qish huquqiga ega —
# shu sabab yuzni taqqoslash bizning backend'da mahalliy (lokal) amalga oshiriladi.
EMPLOYEE_SERVICE_BASE_URL = os.environ.get(
    "EMPLOYEE_SERVICE_BASE_URL", "https://192.168.101.6:5000/api/v1"
)
EMPLOYEE_SERVICE_API_KEY = os.environ.get("EMPLOYEE_SERVICE_API_KEY", "dev-employee-service-key")
# Employee_service o'z-o'zidan imzolangan (self-signed) sertifikat ishlatadi.
EMPLOYEE_SERVICE_VERIFY_SSL = os.environ.get("EMPLOYEE_SERVICE_VERIFY_SSL", "false") == "true"
# SFace "match" natijasi (cosine o'xshashlik, 0..1) shu qiymatdan katta bo'lsa — mos deb hisoblanadi.
FACE_MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "0.36"))

# Tashqi dashboard uchun ochiq endpoint (/api/public/protocol/) kaliti.
#
# BO'SH qoldirilsa — endpoint hech narsa so'ramaydi (ataylab shunday: tashqi
# dashboard foydalanuvchisidan BnpzTest logini so'ralmasligi kerak).
# Qiymat berilsa — so'rovda `X-Api-Key` sarlavhasi (yoki `?key=`) talab
# qilinadi. Endpoint tabel raqami bo'yicha xodimning test natijasi, protokoli
# va yuz/ekran videosini beradi, tabel raqami esa maxfiy emas — shuning uchun
# tashqi dashboard SERVER tomonidan so'rov yuborsa, bu kalitni qo'yish tavsiya
# etiladi (brauzerdan to'g'ridan-to'g'ri so'ralsa kalit baribir ko'rinib qoladi).
PUBLIC_API_KEY = os.environ.get("PUBLIC_API_KEY", "")
