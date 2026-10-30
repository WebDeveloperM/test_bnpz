"""Mavjud video yozuvlarga tabel raqami va sexni nusxa qilib yozadi.

0037 shu maydonlarni qo'shdi, lekin eski qatorlar bo'sh qoldi — arxiv filtri
esa aynan shu ustunlar bo'yicha ishlaydi, ya'ni to'ldirilmasa eski yozuvlar
tabel/sex bo'yicha qidirilganda topilmay qolardi.

Qiymat uch manbadan izlanadi (qaysi biri qolgan bo'lsa):
  • natijadagi tabel nusxasi (`Result.tabel_number` — topshirish paytida olingan);
  • seansdagi xodim (`Attempt.employee.tabel_number`);
  • seans yoki natija testi (`Test.tsex`).

Ikkalasi ham topilmasa qator bo'sh qoladi — bu xato emas: bog'lanishi
allaqachon uzilgan eski yozuvda bu ma'lumotni oladigan joy yo'q (qarang:
0032, xuddi shu holat ism/test nomi uchun).
"""
from django.db import migrations


def fill(apps, schema_editor):
    Recording = apps.get_model("core", "Recording")
    updated = 0
    qs = Recording.objects.select_related(
        "attempt__employee", "attempt__test", "result__employee", "result__test",
    )
    for r in qs:
        if r.tabel_number and r.tsex:
            continue
        attempt, result = r.attempt, r.result

        if not r.tabel_number:
            if result is not None and result.tabel_number:
                r.tabel_number = result.tabel_number
            elif attempt is not None and attempt.employee_id:
                r.tabel_number = attempt.employee.tabel_number or ""
            elif result is not None and result.employee_id:
                r.tabel_number = result.employee.tabel_number or ""

        if not r.tsex:
            if attempt is not None and attempt.test_id:
                r.tsex = attempt.test.tsex or ""
            elif result is not None and result.test_id:
                r.tsex = result.test.tsex or ""

        if r.tabel_number or r.tsex:
            r.save(update_fields=["tabel_number", "tsex"])
            updated += 1
    print(f"  {updated} ta video yozuviga tabel/sex yozildi")


def unfill(apps, schema_editor):
    # Maydonlar 0037 ni orqaga qaytarganda yo'qoladi — bu yerda qiladigan ish yo'q.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_recording_tabel_number_recording_tsex"),
    ]

    operations = [
        migrations.RunPython(fill, unfill),
    ]
