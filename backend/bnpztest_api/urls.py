from django.contrib import admin
from django.contrib.staticfiles.views import serve as static_serve
from django.urls import path, include, re_path

from core.views import media_recordings_view, public_media_view

urlpatterns = [
    path("it-center/", admin.site.urls),
    path("api/", include("core.urls")),
    # Django admin (/it-center) ning CSS/JS fayllari. Ilgari ularni
    # `runserver --insecure` o'zi uzatardi; `serve.py` (waitress) bunday
    # qilmaydi. Fayllar o'rnatilgan paketlar ichidan olinadi (collectstatic
    # shart emas). nginx /static/ ni faqat admin portida (2050) uzatadi.
    re_path(r"^static/(?P<path>.*)$", static_serve, {"insecure": True}),
    # Video nazorat yozuvlari — FAQAT administratorlar (token yoki /it-center
    # sessiyasi bilan). Bu qator umumiy media qatoridan OLDIN turishi shart.
    re_path(r"^media/recordings/(?P<path>.+)$", media_recordings_view),
    # Qolgan media — savol/variant rasmlari, oferta videosi — ochiq: ularni
    # test topshirayotgan xodim ham ko'radi.
    #
    # DIQQAT: ilgari bu yerda `static()` yordamchisi ishlatilgan. U esa faqat
    # DEBUG=True da ishlaydi — DEBUG o'chirilishi bilan BARCHA rasm va videolar
    # jimgina 404 bo'lib qolardi. Media har doim nginx orqali shu backend'dan
    # so'raladi, shuning uchun serve doim yoqiq turadi.
    # `public_media_view` — `serve` ning o'zi, faqat yozuvlar papkasiga tushadigan
    # yo'llarni ruxsat tekshiruviga qaytaradi (sababi o'sha funksiya izohida).
    re_path(r"^media/(?P<path>.+)$", public_media_view),
]
