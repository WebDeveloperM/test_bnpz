from django.core.management.base import BaseCommand
from core.models import Test, Question, Option, Employee


DEMO = {
    "Buxgalter": [
        ("Buxgalteriya balansi qaysi ikki qismdan iborat?", "single",
         [("Aktiv va passiv", True), ("Debet va foyda", False),
          ("Kirim va soliq", False), ("Kassa va bank", False)]),
        ("Quyidagilardan qaysilari asosiy vositalarga kiradi?", "multiple",
         [("Bino", True), ("Uskuna", True), ("Xomashyo", False), ("Ish haqi", False)]),
    ],
    "Dispetcher": [
        ("Dispetcherning asosiy vazifasi nima?", "single",
         [("Harakatni muvofiqlashtirish", True), ("Hisobot yozish", False),
          ("Ta'mirlash", False), ("Sotuv qilish", False)]),
        ("Favqulodda vaziyatda dispetcher birinchi navbatda nima qiladi?", "single",
         [("Tegishli xizmatlarga xabar beradi", True), ("Kutadi", False),
          ("Smenani tark etadi", False), ("Hujjat to'ldiradi", False)]),
    ],
}


class Command(BaseCommand):
    help = "Namuna testlar va xodimlar yaratadi"

    def handle(self, *args, **opts):
        for test_name, questions in DEMO.items():
            test, _ = Test.objects.get_or_create(
                name=test_name,
                defaults={"pass_percent": 60, "time_limit": 10, "grading_scale": "foiz"},
            )
            if test.questions.exists():
                continue
            for order, (text, qtype, options) in enumerate(questions):
                q = Question.objects.create(test=test, qtype=qtype, text=text, order=order)
                for oi, (otext, correct) in enumerate(options):
                    Option.objects.create(question=q, text=otext, is_correct=correct, order=oi)
            self.stdout.write(self.style.SUCCESS(f"Test yaratildi: {test_name}"))

        buxgalter = Test.objects.filter(name="Buxgalter").first()
        dispetcher = Test.objects.filter(name="Dispetcher").first()

        demo_emps = [
            ("Karimov Aziz", "1234", buxgalter, "uz"),
            ("Soliyeva Nigora", "1234", dispetcher, "uz-cyrl"),
        ]
        for name, pwd, test, lang in demo_emps:
            if not Employee.objects.filter(full_name=name).exists():
                Employee.objects.create(full_name=name, password=pwd,
                                        assigned_test=test, language=lang)
                self.stdout.write(self.style.SUCCESS(f"Xodim yaratildi: {name} (parol: {pwd})"))

        self.stdout.write(self.style.SUCCESS("Namuna ma'lumotlar tayyor."))
