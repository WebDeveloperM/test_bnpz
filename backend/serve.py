"""Backend konteynerining HTTP serveri (qarang: Dockerfile, CMD).

Nega `manage.py runserver` emas
-------------------------------
`runserver` — Django'ning ishlab chiqish (dev) serveri. U HAR BIR so'rov uchun
yangi oqim ochadi va so'rov tugashi bilan uni tashlaydi. Django esa bazaga
ulanishni oqimga bog'lab saqlaydi — ya'ni har so'rov bazaga YANGI ulanish
ochardi. Serverdagi Postgres Windows'da ishlaydi va u har ulanish uchun yangi
jarayon yaratadi: o'lchangan ~50 ms, va bu ulanishlar Postgres ichida NAVBAT
bilan ochiladi. 10 xodim (video bo'laklar, polling) va admin paneli (har
so'rovda token bazadan tekshiriladi) birga sekundiga bir necha ulanish
degani — hamma so'rov shu navbatda kutib qolardi.

Bu yerda `waitress` ishlatiladi: oqimlar SONI CHEKLANGAN va ular QAYTA
ishlatiladi. Shuning uchun ulanish ham qayta ishlatiladi (`DB_CONN_MAX_AGE`),
ulanishlar soni esa oqimlar sonidan oshmaydi — `CONN_MAX_AGE` runserver bilan
sinalganda yuz bergan "100 ta ulanish to'lib qoldi" holati bu yerda bo'lmaydi.

Nega bitta jarayon (gunicorn kabi bir nechta worker emas)
--------------------------------------------------------
Jonli ekran signaling'i (`views._live_sessions`), sinxronizatsiya bayrog'i va
Django keshi (LocMemCache) jarayon XOTIRASIDA turadi. Bir nechta jarayonda har
biri o'z nusxasini ko'rardi va jonli ekran tasodifiy ishlamay qolardi. Bitta
jarayon + oqimlar havzasi bu holatni o'zgartirmaydi.

Zaxira yo'l
-----------
`.env` ga `WSGI_SERVER=runserver` yozilib, `docker compose up -d backend`
qilinsa — eski serverga (aynan avvalgi buyruq bilan) qaytiladi. Kodni
qaytarish ham, image'ni qayta yig'ish ham shart emas.
"""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bnpztest_api.settings")

# Bir vaqtda ishlov beriladigan so'rovlar soni = bazaga ulanishlar chegarasi.
# 24: 10-20 xodim + bir necha admin uchun yetarli zaxira (bir paytning o'zida
# odatda 5-10 so'rov bo'ladi), Postgres'ning standart 100 ulanish chegarasidan
# esa ancha past.
THREADS = int(os.environ.get("WSGI_THREADS") or "24")


def main():
    server = (os.environ.get("WSGI_SERVER") or "waitress").strip().lower()
    if server == "runserver":
        os.execvp(sys.executable, [
            sys.executable, "manage.py", "runserver", "0.0.0.0:8000", "--insecure",
        ])

    # Settings import qilinishidan OLDIN o'rnatilishi shart (settings.py o'qiydi).
    # 60 soniya: ulanish shuncha ishlatilmay tursa, keyingi so'rovda yopilib
    # yangisi ochiladi — uzoq vaqt bo'sh turgan (masalan Docker Desktop tarmog'i
    # uzib qo'ygan) ulanishga tayanilmaydi.
    os.environ.setdefault("DB_CONN_MAX_AGE", "60")

    from waitress import serve
    from bnpztest_api.wsgi import application

    serve(
        application,
        listen="0.0.0.0:8000",
        threads=THREADS,
        # nginx `X-Forwarded-Proto: https` yuboradi — Django fayl havolalarini
        # (build_absolute_uri) https:// bilan yasashi uchun bu sarlavha
        # yetib borishi kerak. Backend porti tashqariga chiqarilmagan, unga
        # faqat nginx murojaat qiladi, shuning uchun "*" xavfsiz.
        trusted_proxy="*",
        trusted_proxy_headers={"x-forwarded-proto", "x-forwarded-for"},
        clear_untrusted_proxy_headers=False,
        # nginx'ning proxy_read_timeout/proxy_send_timeout bilan bir xil.
        channel_timeout=300,
        connection_limit=500,
        asyncore_use_poll=True,
        ident="bnpztest",
    )


if __name__ == "__main__":
    main()
