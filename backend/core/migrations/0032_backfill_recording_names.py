"""Mavjud video yozuvlarga xodim va test nomini nusxa qilib yozadi.

0031 shu maydonlarni qo'shdi, lekin eski qatorlar bo'sh qoldi. Ularni hozir,
seans bog'lanishi hali uzilmagan paytda to'ldiramiz — keyinroq test yoki xodim
o'chirilsa, nomni oladigan joy qolmaydi.
"""
from django.db import migrations


def fill(apps, schema_editor):
    Recording = apps.get_model("core", "Recording")
    updated = 0
    for r in Recording.objects.select_related("attempt__employee", "attempt__test"):
        if r.employee_name and r.test_name:
            continue
        attempt = r.attempt
        if attempt is None:
            continue
        if not r.employee_name and attempt.employee_id:
            r.employee_name = attempt.employee.full_name
        if not r.test_name and attempt.test_id:
            r.test_name = attempt.test.name
        r.save(update_fields=["employee_name", "test_name"])
        updated += 1
    print(f"  {updated} ta video yozuviga nom yozildi")


def unfill(apps, schema_editor):
    # Maydonlar 0031 ni orqaga qaytarganda yo'qoladi — bu yerda qiladigan ish yo'q.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_recording_employee_name_recording_test_name_and_more"),
    ]

    operations = [
        migrations.RunPython(fill, unfill),
    ]
