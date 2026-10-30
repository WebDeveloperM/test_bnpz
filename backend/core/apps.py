from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    # Tizim administratori panelidagi bo'lim sarlavhasi ("CORE" o'rniga).
    verbose_name = "Testlar, xodimlar va natijalar"

    # Bu yerda ilgari har 24 soatda `sync_employees` ni chaqiradigan fon oqimi
    # bor edi. U OLIB TASHLANDI, chunki qilgan ishi amalda kerak emas edi:
    #
    # Yuz orqali kirish (EmployeeIdentifyView) faqat "Kutilayotgan xodimlar"
    # ro'yxati ichida qidiradi, o'sha ro'yxatga qo'shishda esa yuz belgisi
    # allaqachon o'sha zahoti hisoblanadi. Ya'ni tungi sinxron 3000+ xodimning
    # rasmini yuklab, hech qachon ishlatilmaydigan belgilarni hisoblardi.
    #
    # Endi BnpzId'ga faqat ma'lumot HAQIQATAN kerak bo'lganda murojaat
    # qilinadi: administrator qidirganda va xodimni ro'yxatga qo'shganda.
    #
    # Oqimning o'zi ham mo'rt edi: u faqat `RUN_MAIN == "true"` bo'lganda
    # ishga tushardi (ya'ni boshqa server bilan jimgina o'chib qolardi),
    # xatosi `except Exception: pass` bilan yutilardi, va birinchi yurishidan
    # oldin 24 soat uxlardi.
    #
    # Ommaviy yangilash kerak bo'lsa: `python manage.py sync_employees`.
