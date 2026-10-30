from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve as media_serve

from core.views import media_recordings_view

urlpatterns = [
    path("it-center/", admin.site.urls),
    path("api/", include("core.urls")),
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
    re_path(r"^media/(?P<path>.+)$", media_serve, {"document_root": settings.MEDIA_ROOT}),
]
