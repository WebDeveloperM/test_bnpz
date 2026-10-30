"""BnpzId (employee_service) dagi xodimlar ro'yxatini mahalliy `SyncedEmployee`
jadvaliga ko'chiradi.

STANDART HOLDA FAQAT METAMA'LUMOT olinadi — ism, tabel, sex, lavozim, rasm
manzili. Rasm YUKLANMAYDI va yuz belgisi hisoblanmaydi.

Sabab: yuz orqali kirish (`EmployeeIdentifyView`) faqat "Kutilayotgan xodimlar"
ro'yxati ichida qidiradi, o'sha ro'yxatga qo'shishda esa belgi allaqachon
o'sha zahoti hisoblanadi (`AdminExpectedEmployeeListView`). Ya'ni 3000+
xodimning belgisini oldindan hisoblash — hech qachon ishlatilmaydigan ish.
Metama'lumotning o'zi esa arzon: butun ro'yxat bir necha soniyada keladi.

`--with-photos` bilan eski xatti-harakat qaytadi: rasmi o'zgargan (yoki hali
belgisi yo'q) xodimlar uchun rasm yuklanib, yuz belgisi hisoblanadi. Bu og'ir
amal — minglab rasm yuklanadi — shuning uchun u ataylab ochiq so'raladi.

Ilgari bu komanda har 24 soatda fon oqimida avtomatik ishga tushardi; u olib
tashlandi (qarang: core/apps.py)."""

from django.core.management.base import BaseCommand, CommandError

from core import bnpzid, face
from core.models import SyncedEmployee


class Command(BaseCommand):
    help = ("BnpzId'dan xodimlar metama'lumotini sinxronlaydi. "
            "--with-photos bilan rasmlarni ham yuklab, yuz belgisini hisoblaydi (og'ir).")

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-photos", action="store_true",
            help="Rasmlarni ham yuklab, yuz belgisini hisoblash (minglab so'rov).",
        )

    def handle(self, *args, **options):
        with_photos = options.get("with_photos", False)

        existing = {
            se.slug: se
            for se in SyncedEmployee.objects.only("slug", "base_image_url", "face_embedding")
        }

        total = synced = skipped = image_missing = no_face = 0

        # Butun ro'yxat AVVAL yig'ib olinadi, keyin yoziladi. Ilgari sahifalar
        # o'qilgani sayin yozilar, o'rtada bitta sahifa kelmasa esa komanda
        # yarim yangilangan holatni qoldirib to'xtardi. Ro'yxat 3000+ yozuv —
        # xotirada bemalol sig'adi.
        try:
            employees = list(bnpzid.iter_employees())
        except bnpzid.BnpzIdError as exc:
            raise CommandError(f"Sinxronizatsiya bajarilmadi — {exc}. Hech nima o'zgartirilmadi.")

        for item in employees:
            total += 1
            slug = item.get("slug")
            image_url = bnpzid.image_url_of(item)
            department = item.get("department") or {}
            section = item.get("section") or {}

            prev = existing.get(slug)
            unchanged = prev and prev.face_embedding and prev.base_image_url == (image_url or "")

            if not with_photos:
                # Metama'lumot rejimi — rasmga umuman tegilmaydi. Mavjud
                # belgi ham o'zgarmaydi (quyida faqat `embedding is not None`
                # bo'lganda yoziladi).
                embedding = None
                skipped += 1
            elif unchanged:
                embedding = prev.face_embedding
                skipped += 1
            else:
                embedding = None
                if image_url:
                    content = bnpzid.fetch_image(image_url)
                    if content is None:
                        # Rasm kelmadi — 404, DEBUG o'chirilgan, yoki tarmoq
                        # uzilgan. Sabab loglarda; bu yerda ularni ajratish
                        # foyda bermaydi, natija bir xil: belgi yangilanmaydi.
                        image_missing += 1
                    else:
                        embedding = face.extract_embedding(content)
                        if embedding is None:
                            no_face += 1

            defaults = {
                "tabel_number": item.get("tabel_number") or "",
                "full_name": item.get("full_name") or "",
                "department_name": department.get("name") or "",
                "section_name": section.get("name") or "",
                "position": item.get("position") or "",
                "base_image_url": image_url or "",
            }
            # Yuz belgisi FAQAT haqiqatan hisoblangan bo'lsa yoziladi.
            #
            # Ilgari u shartsiz yozilardi va `embedding` None bo'lsa ishlab
            # turgan belgi NULL bilan ustiga yozilardi. Bu uch holatda sodir
            # bo'lardi: tarmoq uzilganda, BnpzId rasmni bermaganda, va —
            # eng ko'p uchraydigani — RASM KELIB, unda yuz aniqlanmaganda.
            # Oxirgisi xatolik ham emas: rasmlarning bir qismi shunchaki
            # sifatsiz yoki yuz ko'rinmaydigan holatda.
            #
            # Oqibati og'ir edi: xodim kamera oldida turardi, tizim uni
            # tanimasdi, va buning sababi hech qayerda ko'rinmasdi. Admin
            # kamera bilan QO'LDA yuklagan rasmdan hisoblangan belgi ham
            # shu yo'l bilan yo'qolardi — ya'ni qo'lda qilingan ish keyingi
            # sinxronizatsiyada bekor bo'lardi.
            #
            # Endi eskisi joyida qoladi: eski belgi bilan ishlash, umuman
            # belgisiz qolishdan har doim yaxshiroq.
            if embedding is not None:
                defaults["face_embedding"] = embedding

            SyncedEmployee.objects.update_or_create(slug=slug, defaults=defaults)
            if embedding is not None:
                synced += 1

        if with_photos:
            self.stdout.write(self.style.SUCCESS(
                f"Jami: {total}, yuz belgisi yangilandi: {synced} "
                f"(o'zgarmagani uchun o'tkazib yuborildi: {skipped}), "
                f"rasm olinmadi: {image_missing}, yuz aniqlanmadi: {no_face}"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Metama'lumot yangilandi: {total} xodim. "
                f"Rasmlarga tegilmadi (yuz belgisi kerak bo'lsa: --with-photos)."
            ))
