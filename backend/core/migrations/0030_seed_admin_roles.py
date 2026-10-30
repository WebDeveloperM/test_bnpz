"""Boshlang'ich rollar va mavjud administratorlarni ularga bog'lash.

Ilgari ruxsatlar kodda edi: "xodim (staff)" belgisiga ega har bir administrator
kundalik 6 ta bo'limni ko'rardi, superuser esa qo'shimcha tizim bo'limlarini.
Endi ruxsatlar rolda saqlanadi, shuning uchun mavjud administratorlarga aynan
o'sha 6 ta bo'limli rol beriladi — migratsiyadan keyin ular uchun hech narsa
o'zgarmaydi. Keyingi o'zgarishlarni superuser panelning "Rollar" bo'limida
o'zi qiladi (bu yerdagi ro'yxatlar shunchaki boshlang'ich holat).
"""
from django.db import migrations

# Migratsiya kod bilan birga o'zgarmasligi uchun kalitlar shu yerda qotirilgan —
# `core/perms.py` keyin o'zgarsa ham bu migratsiya avvalgidek qayta ijro etiladi.
TEST_ADMIN_PERMS = ["expected", "checkins", "active", "results", "tests", "settings"]
UCHEBNIY_PERMS = ["tests", "results"]


def seed(apps, schema_editor):
    AdminRole = apps.get_model("core", "AdminRole")
    AdminProfile = apps.get_model("core", "AdminProfile")
    User = apps.get_model("auth", "User")

    test_admin, _ = AdminRole.objects.get_or_create(
        name="Test administratori",
        defaults={
            "description": "Kundalik test o'tkazish ishi.",
            "permissions": TEST_ADMIN_PERMS,
        },
    )
    AdminRole.objects.get_or_create(
        name="Uchebniy administrator",
        defaults={
            "description": "O'quv qismi: testlar, savollar va natijalar.",
            "permissions": UCHEBNIY_PERMS,
        },
    )

    # Superuserga rol kerak emas — unga har doim barcha bo'limlar ochiq.
    for user in User.objects.filter(is_staff=True, is_superuser=False):
        AdminProfile.objects.get_or_create(user=user, defaults={"role": test_admin})


def unseed(apps, schema_editor):
    # Rollarni o'chirish yetarli: `AdminProfile.role` SET_NULL, jadvallarning
    # o'zi esa 0029 ni orqaga qaytarganda yo'qoladi.
    AdminRole = apps.get_model("core", "AdminRole")
    AdminRole.objects.filter(name__in=["Test administratori", "Uchebniy administrator"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_adminrole_adminprofile"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
