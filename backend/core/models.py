import uuid
from django.conf import settings as django_settings
from django.db import models
from django.contrib.auth.hashers import make_password, check_password, identify_hasher

from .perms import clean_permissions


class AdminRole(models.Model):
    """Panel roli — nomi va unga ochiq bo'limlar ro'yxati.

    Ruxsatlar kodda qattiq biriktirilmagan: superuser panelning "Rollar"
    bo'limida istalgan paytda belgilab/o'zgartirib turadi. `permissions` —
    `core/perms.py` dagi kalitlardan iborat oddiy ro'yxat.

    Superuser rolga umuman bog'liq emas — unga har doim barcha bo'limlar
    ochiq, shuning uchun unga rol berish shart emas."""

    name = models.CharField("Rol nomi", max_length=100, unique=True)
    description = models.CharField("Izoh", max_length=300, blank=True)
    permissions = models.JSONField("Ruxsatlar", default=list, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Rollar"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Tanilmagan kalit bazaga tushmasin — u hech qachon ishlamaydi, lekin
        # ro'yxatda "ruxsat bordek" ko'rinib chalkashtiradi.
        self.permissions = clean_permissions(self.permissions)
        super().save(*args, **kwargs)


class AdminProfile(models.Model):
    """Django foydalanuvchisini panel roli bilan bog'laydi.

    Alohida jadval qilinganining sababi: `auth.User` Django'niki, unga maydon
    qo'shib bo'lmaydi. Roli yo'q (yoki roli o'chirilgan) administrator panelga
    kira oladi, lekin hech qanday bo'lim ko'rmaydi — bu ataylab shunday:
    "ruxsat berilmagan" holat "hamma narsa ochiq"dan xavfsizroq."""

    user = models.OneToOneField(
        django_settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="admin_profile", verbose_name="Foydalanuvchi",
    )
    role = models.ForeignKey(
        AdminRole, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="users", verbose_name="Rol",
    )

    class Meta:
        verbose_name = "Administrator roli"
        verbose_name_plural = "Administratorlar rollari"

    def __str__(self):
        return f"{self.user.username} — {self.role.name if self.role else 'rolsiz'}"


class Test(models.Model):
    """Lavozim testi."""
    MODE_CHOICES = [
        ("oddiy", "Oddiy"),
        ("erkin", "Erkin"),
        ("jarima", "Jarima"),
        ("maksimal", "Maksimal"),
    ]
    SCALE_CHOICES = [
        ("foiz", "Foiz"),
        ("5", "5 ballik"),
        ("100", "100 ballik"),
    ]
    TIME_SCOPE_CHOICES = [
        ("test", "Butun test uchun"),
        ("question", "Har bir savol uchun"),
    ]

    name = models.CharField("Lavozim / test nomi", max_length=200)
    tsex = models.CharField(
        "Sex/tsex", max_length=200, blank=True,
        help_text="Lavozimlarni sex/tsex bo'yicha guruhlash uchun — xodimga test biriktirishda "
                   "avval sex tanlanadi, keyin shu sexga tegishli lavozimlar ko'rsatiladi.",
    )
    mode = models.CharField("Rejim", max_length=20, choices=MODE_CHOICES, default="oddiy")
    introduction = models.TextField("Kirish yo'riqnomasi", blank=True)
    grading_scale = models.CharField("Baholash shkalasi", max_length=10, choices=SCALE_CHOICES, default="foiz")
    pass_percent = models.PositiveIntegerField("O'tish foizi", default=60)
    time_limit = models.PositiveIntegerField("Vaqt chegarasi (daqiqa, 0 = cheksiz)", default=0)
    time_limit_scope = models.CharField("Vaqt chegarasi turi", max_length=10,
                                        choices=TIME_SCOPE_CHOICES, default="test")
    shuffle_questions = models.BooleanField("Savollarni aralashtirish", default=True)
    shuffle_options = models.BooleanField("Variantlarni aralashtirish", default=True)
    sample_count = models.PositiveIntegerField("Beriladigan savollar soni (0 = barchasi)", default=0)
    common_question_count = models.PositiveIntegerField(
        "Umumiy savollar soni", default=0,
        help_text="Beriladigan savollar soniga \"umumiy savollar\" testidan shuncha savol qo'shiladi. "
                   "Masalan: 20 savol, shundan 5 tasi umumiy bo'lsa, qolgan 15 tasi shu lavozimga xos "
                   "savollardan tanlanadi.",
    )
    is_common_pool = models.BooleanField(
        "Umumiy savollar to'plami", default=False,
        help_text="Belgilansa, bu testga qo'shilgan barcha savollar boshqa testlarning "
                   "\"umumiy savollar\" manbai sifatida ishlatiladi.",
    )
    instant_feedback = models.BooleanField("Noto'g'ri javobni darhol bildirish", default=False)
    proctoring = models.BooleanField("Video nazorat", default=True)
    grade_thresholds = models.JSONField(
        "Baho chegaralari", default=list, blank=True,
        help_text="Masalan: [{\"min\": 90, \"grade\": \"5\"}, {\"min\": 75, \"grade\": \"4\"}]",
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Test (lavozim)"
        verbose_name_plural = "Testlar (lavozimlar)"

    def __str__(self):
        return self.name


class QuestionGroup(models.Model):
    """Test ichidagi savollar bo'limi (TZ 4.2, 5.1 — groups)."""
    test = models.ForeignKey(Test, related_name="groups", on_delete=models.CASCADE)
    name = models.CharField("Bo'lim nomi", max_length=200)
    order = models.PositiveIntegerField("Tartib", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Savollar bo'limi"
        verbose_name_plural = "Savollar bo'limlari"

    def __str__(self):
        return f"[{self.test.name}] {self.name}"


class Question(models.Model):
    TYPE_CHOICES = [
        ("single", "Bir tanlovli"),
        ("multiple", "Ko'p tanlovli"),
        ("truefalse", "To'g'ri/Noto'g'ri"),
        ("text", "Matn/raqam kiritish"),
        ("fillblank", "Bo'sh joyni to'ldirish"),
        ("ordering", "Tartiblash"),
        ("matching", "Moslashtirish"),
    ]
    test = models.ForeignKey(Test, related_name="questions", on_delete=models.CASCADE)
    group = models.ForeignKey(QuestionGroup, related_name="questions", null=True, blank=True,
                              on_delete=models.SET_NULL, verbose_name="Bo'lim")
    qtype = models.CharField("Savol turi", max_length=20, choices=TYPE_CHOICES, default="single")
    text = models.TextField("Savol matni")
    points = models.PositiveIntegerField("Ball (og'irlik)", default=1)
    explanation = models.TextField("To'g'ri javob izohi", blank=True)
    correct_text = models.CharField("To'g'ri javob (matn/raqam turi uchun)", max_length=300, blank=True)
    image = models.ImageField("Rasm", upload_to="questions/", null=True, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    # Boshqa tillardagi matnlar. Yuqoridagi `text`/`explanation`/`correct_text`
    # — asosiy til (o'zbekcha lotin). Bu yerda faqat tarjimalar saqlanadi:
    #   {"ru": {"text": "...", "explanation": "...", "correct_text": "..."},
    #    "uz-cyrl": {...}}
    # Savol bitta qator bo'lib qolgani uchun til almashtirilganda savol id'si
    # ham, variant id'lari ham o'zgarmaydi — xodimning javoblari joyida qoladi
    # va baholash mantiqi bitta joyda (tarjimadan mustaqil) qoladi.
    i18n = models.JSONField("Tarjimalar", default=dict, blank=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Savol"
        verbose_name_plural = "Savollar"

    def __str__(self):
        return f"[{self.test.name}] {self.text[:50]}"


class Option(models.Model):
    question = models.ForeignKey(Question, related_name="options", on_delete=models.CASCADE)
    text = models.CharField("Variant matni", max_length=500, blank=True)
    is_correct = models.BooleanField("To'g'ri javob", default=False)
    match_text = models.CharField("Mos javob (moslashtirish turi uchun)", max_length=500, blank=True)
    # Variantning o'z rasmi — savol rasmidan alohida. Masalan "qaysi belgi
    # to'g'ri?" turidagi savolda har bir variant rasm bo'lishi mumkin.
    # Rasm bo'lsa matn bo'sh qolishi mumkin, shuning uchun `text` blank=True.
    image = models.ImageField("Rasm", upload_to="options/", null=True, blank=True)
    order = models.PositiveIntegerField("Tartib", default=0)
    # {"ru": {"text": "...", "match_text": "..."}, "uz-cyrl": {...}} — qarang: Question.i18n
    i18n = models.JSONField("Tarjimalar", default=dict, blank=True)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "Variant"
        verbose_name_plural = "Variantlar"

    def __str__(self):
        return self.text or ("[rasm]" if self.image else f"#{self.pk}")


class Employee(models.Model):
    STATUS_CHOICES = [
        ("assigned", "Tayinlangan"),
        ("completed", "Topshirilgan"),
    ]
    LANG_CHOICES = [
        ("uz", "O'zbek (lotin)"),
        ("uz-cyrl", "O'zbek (kirill)"),
        ("ru", "Rus"),
    ]
    full_name = models.CharField("Ism-familiya", max_length=200)
    password = models.CharField("Parol", max_length=256, blank=True)
    department = models.CharField("Bo'lim / sex", max_length=200, blank=True)
    tabel_number = models.CharField("Tabel raqami", max_length=50, blank=True)
    assigned_test = models.ForeignKey(Test, null=True, blank=True, on_delete=models.SET_NULL,
                                      verbose_name="Biriktirilgan test")
    status = models.CharField("Holat", max_length=20, choices=STATUS_CHOICES, default="assigned")
    language = models.CharField("Til", max_length=10, choices=LANG_CHOICES, default="uz")
    external_slug = models.CharField(
        "employee_service slug", max_length=200, blank=True, null=True, unique=True,
        help_text="Yuz orqali kirish uchun employee_service loyihasidagi xodimga bog'lanish.",
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Xodim"
        verbose_name_plural = "Xodimlar"

    def save(self, *args, **kwargs):
        # Parolni hash qilish (agar hali hash qilinmagan bo'lsa).
        if self.password:
            try:
                identify_hasher(self.password)
            except Exception:
                self.password = make_password(self.password)
        super().save(*args, **kwargs)

    def check_password(self, raw):
        return check_password(raw, self.password)

    def __str__(self):
        return self.full_name


class Attempt(models.Model):
    """Xodimning bitta test seansi.

    Seans ham yozib olingan fakt: xodim yoki test o'chirilsa, u bilan birga
    yo'qolmaydi (`SET_NULL`). Ilgari ikkalasi ham CASCADE edi va test
    o'chirilishi seansni, seans esa video yozuvini o'chirib yuborardi."""
    employee = models.ForeignKey(Employee, related_name="attempts", null=True, blank=True,
                                 on_delete=models.SET_NULL)
    test = models.ForeignKey(Test, null=True, blank=True, on_delete=models.SET_NULL)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    question_ids = models.JSONField(default=list)  # shu seansda beriladigan savollar tartibi
    completed = models.BooleanField(default=False)
    hints_used = models.PositiveIntegerField(default=0)  # "Tekshirish" (instant_feedback) necha marta bosilgan
    # Testni yakunlagan paytdagi til — test davomida o'zgartirilishi mumkin,
    # shuning uchun xodim profilidagi `Employee.language` emas, aynan shu seansniki.
    language = models.CharField("Til", max_length=10, choices=Employee.LANG_CHOICES, default="uz")
    # Serverda qulflangan javoblar: {"<savol id>": <javob>}.
    # Javob bu yerga tushgach, yakunlashda mijoz yuborgan javob emas, AYNAN shu
    # javob hisobga olinadi. Ikki holatda qulflanadi: (1) "Tekshirish" bosilib
    # to'g'ri javob ko'rsatilganda — aks holda javobni ko'rib, keyin o'zgartirib
    # yuborish mumkin edi; (2) "Maksimal" rejimda savoldan keyingisiga o'tilganda —
    # bu rejimda orqaga qaytish taqiqlangani faqat brauzerda emas, serverda ham
    # kuchga kirishi uchun.
    locked_answers = models.JSONField("Qulflangan javoblar", default=dict, blank=True)
    # Aralashtirilgan variantlar tartibi: {"<savol id>": {"options": [...], "match": [...]}}.
    # Bir marta hisoblanadi va shu seans davomida o'zgarmaydi — aks holda sahifa
    # yangilanganda (F5) savol variantlari qayta aralashib, xodim uchun butunlay
    # boshqa ko'rinishga kelardi.
    layout = models.JSONField("Variantlar tartibi", default=dict, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Test seansi"
        verbose_name_plural = "Test seanslari"

    def __str__(self):
        # `employee`/`test` SET_NULL — o'chirilgan bo'lishi mumkin. To'g'ridan
        # to'g'ri `self.employee.full_name` yozilsa, /it-center dagi seanslar
        # yoki video yozuvlar ro'yxati shunday qatorda 500 bilan yiqilardi.
        who = self.employee.full_name if self.employee_id else "(o'chirilgan xodim)"
        what = self.test.name if self.test_id else "(o'chirilgan test)"
        return f"{who} — {what}"


class Result(models.Model):
    employee = models.ForeignKey(Employee, null=True, on_delete=models.SET_NULL)
    test = models.ForeignKey(Test, null=True, on_delete=models.SET_NULL)
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    test_name = models.CharField(max_length=200)
    full_name = models.CharField(max_length=200)
    tabel_number = models.CharField(max_length=50, blank=True)
    correct = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)
    pct = models.PositiveIntegerField(default=0)
    points_earned = models.IntegerField(default=0)
    points_total = models.PositiveIntegerField(default=0)
    violations = models.PositiveIntegerField("Chiqib ketishga urinishlar", default=0)
    share_stopped = models.BooleanField("Ekran ulashish to'xtatilgani sababli yakunlandi", default=False)
    # Sahifa yangilangani (F5) yoki seans tashlab ketilgani sababli majburan
    # yakunlangan test. Test davomida sahifani yangilash TAQIQLANGAN: yangilagan
    # xodim testga qaytib kirmaydi, test o'sha ondagi javoblar bilan yopiladi.
    interrupted = models.BooleanField("Sahifa yangilangani sababli to'xtatildi", default=False)
    grade = models.CharField(max_length=10, blank=True)
    passed = models.BooleanField(default=False)
    answers = models.JSONField(default=list)  # har bir savol bo'yicha tafsilot
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Natija"
        verbose_name_plural = "Natijalar"

    def __str__(self):
        return f"{self.full_name} — {self.test_name} — {self.pct}%"


class ActivityLog(models.Model):
    """Tizimdagi barcha muhim harakatlar tarixi — adminning ham, test
    ishlayotgan xodimning ham amallari (login, test yaratish/o'chirish,
    test topshirish va h.k.) shu yerda kuzatiladi."""
    ACTOR_ADMIN = "admin"
    ACTOR_EMPLOYEE = "employee"
    ACTOR_CHOICES = [(ACTOR_ADMIN, "Administrator"), (ACTOR_EMPLOYEE, "Xodim")]

    created = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=10, choices=ACTOR_CHOICES)
    actor_name = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=50)
    description = models.CharField(max_length=500)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created"]
        verbose_name = "Amallar tarixi"
        verbose_name_plural = "Amallar tarixi"

    def __str__(self):
        return f"[{self.actor}] {self.actor_name} — {self.description}"


class Recording(models.Model):
    """Video nazorat yozuvi (TZ 4.9). Fayl diskda (MEDIA_ROOT) saqlanadi,
    bazada faqat yo'l/manzil turadi — shu sabab baza video hajmi bilan og'irlashmaydi.

    Yozuv YOZIB OLINGAN FAKT: u test ham, xodim ham, seans ham o'chirilgandan
    keyin arxivda qolishi shart. Shuning uchun:
      • `attempt` va `result` — SET_NULL (bog'lanish uziladi, yozuv qolaveradi);
      • xodim va test NOMI shu yerning o'zida saqlanadi, ya'ni bog'lanish
        uzilgandan keyin ham arxivda "kimning, qaysi test videosi" ko'rinadi.

    Ilgari `attempt` CASCADE edi: test yoki xodim o'chirilsa seans, seans bilan
    birga video yozuvi ham o'chib ketardi (fayl diskda qolib, arxivdan
    yo'qolardi). Shu sabab bu yerda CASCADE ishlatilmaydi."""
    KIND_CHOICES = [("screen", "Ekran"), ("face", "Yuz (kamera)")]

    attempt = models.ForeignKey(Attempt, related_name="recordings", null=True, blank=True,
                                on_delete=models.SET_NULL)
    result = models.ForeignKey(Result, null=True, blank=True, related_name="recordings",
                               on_delete=models.SET_NULL)
    # Bog'lanish uzilganda ham arxiv o'qilishi uchun nusxa olinadigan maydonlar.
    employee_name = models.CharField("Xodim", max_length=200, blank=True)
    test_name = models.CharField("Test", max_length=200, blank=True)
    # Tabel raqami va sex ham SHU YERDA nusxa qilinadi — yuqoridagilar bilan
    # bir xil sababga ko'ra, va yana bittasi uchun: arxivni tabel yoki sex
    # bo'yicha filtrlash aks holda `attempt`/`result` orqali JOIN talab
    # qilardi, nullable FK ustidagi bunday filtr esa bog'lanishi uzilgan
    # yozuvni HECH QACHON topa olmaydi — ya'ni eski yozuv filtrda jimgina
    # yo'qolardi. `db_index`: arxiv o'sib boradi, filtr esa aynan shu ikki
    # ustun bo'yicha ishlaydi.
    tabel_number = models.CharField("Tabel raqami", max_length=50, blank=True, db_index=True)
    tsex = models.CharField("Sex/tsex", max_length=200, blank=True, db_index=True)
    kind = models.CharField("Turi", max_length=10, choices=KIND_CHOICES)
    file = models.FileField("Fayl", upload_to="recordings/%Y/%m/%d/")
    created = models.DateTimeField(auto_now_add=True)
    # Fayl bo'lak-bo'lak yozilgani uchun (qarang: RecordingUploadView) sarlavhada
    # umumiy davomiylik yo'q — pleyer buni "jonli oqim" deb hisoblaydi. Katta
    # faylda (100+ MB) bu og'ir oqibat beradi: sarlavhada davomiylik yo'qligi
    # sabab brauzer buni bilish uchun faylning katta qismini yuklashga majbur
    # bo'ladi (qarang: fixVideoDuration.js). Xodim brauzeri yozuv necha soniya
    # davom etganini aniq biladi (qarang: RecordingDurationView) — shu qiymat
    # shu yerda saqlanadi va birinchi ko'rilganda sarlavhaga yoziladi (qarang:
    # `_ensure_recording_duration_fixed`).
    duration_ms = models.PositiveIntegerField("Davomiylik (ms)", null=True, blank=True)
    # Sarlavhaga yozish bir martalik amal (fayl qayta o'qilib, qisman qayta
    # yoziladi) — bu bayroq takroriy urinishning oldini oladi. `duration_ms`
    # hali kelmagan (eski yozuv yoki hali yakunlanmagan) holatda ham, urinish
    # muvaffaqiyatsiz bo'lganda ham O'RNATILADI: aks holda bunday yozuv har
    # safar ko'rilganda qayta-qayta tekshirilaverardi.
    duration_fixed = models.BooleanField("Davomiylik tuzatilgan", default=False)

    class Meta:
        verbose_name = "Video yozuv"
        verbose_name_plural = "Video yozuvlar"

    def __str__(self):
        who = self.employee_name or (str(self.attempt) if self.attempt_id else "—")
        return f"{who} — {self.get_kind_display()}"


class SyncedEmployee(models.Model):
    """employee_service loyihasidagi xodimning mahalliy nusxasi — yuz orqali
    identifikatsiya qilish uchun oldindan hisoblangan "embedding" bilan birga
    saqlanadi (TZ: kamera orqali kirish). Manba tizim faqat o'qish huquqi
    beradi, shu sabab bu ma'lumot davriy ravishda sinxronlanadi (sync_employees
    boshqaruv komandasi)."""

    slug = models.CharField(max_length=200, unique=True)
    tabel_number = models.CharField(max_length=50, blank=True)
    full_name = models.CharField(max_length=200)
    department_name = models.CharField(max_length=200, blank=True)
    section_name = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=200, blank=True)
    base_image_url = models.URLField(max_length=500, blank=True)
    face_embedding = models.JSONField(null=True, blank=True)
    local_photo = models.ImageField(
        "Qo'lda yuklangan rasm", upload_to="synced_employee_photos/", null=True, blank=True,
        help_text="employee_service'da rasmi bo'lmagan xodim uchun admin panelda qo'lda yuklangan rasm.",
    )
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sinxronlangan xodim (employee_service)"
        verbose_name_plural = "Sinxronlangan xodimlar (employee_service)"

    def __str__(self):
        return f"{self.full_name} ({self.tabel_number})"


class ExpectedEmployee(models.Model):
    """Admin tomonidan oldindan belgilangan "bugun kelishi kutilayotgan
    xodimlar" ro'yxati. Yuz orqali kirish (EmployeeIdentifyView) shu ro'yxat
    bo'sh bo'lmasa, FAQAT shu xodimlar orasida qidiradi — 3000+ xodimning
    barchasini har safar solishtirish o'rniga, serverga tushadigan yukni
    kamaytiradi."""

    synced_employee = models.ForeignKey(
        SyncedEmployee, on_delete=models.CASCADE, related_name="expected_entries",
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Kutilayotgan xodim"
        verbose_name_plural = "Kutilayotgan xodimlar"
        unique_together = [("synced_employee",)]
        ordering = ["-created"]

    def __str__(self):
        return self.synced_employee.full_name


class CheckIn(models.Model):
    """Xodim kamera oldiga kelib o'zini tanitgandan so'ng, administrator test
    tayinlab boshlab bergunga qadar bo'lgan kutish holati (TZ: yuz orqali
    kirish oqimi)."""

    STATUS_CHOICES = [
        ("waiting", "Kutilmoqda"),
        ("started", "Boshlandi"),
        ("cancelled", "Bekor qilindi"),
    ]

    synced_employee = models.ForeignKey(SyncedEmployee, null=True, blank=True, on_delete=models.SET_NULL)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL)
    full_name = models.CharField(max_length=200)
    department_name = models.CharField(max_length=200, blank=True)
    match_score = models.FloatField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="waiting")
    test = models.ForeignKey(Test, null=True, blank=True, on_delete=models.SET_NULL)
    attempt = models.ForeignKey(Attempt, null=True, blank=True, on_delete=models.SET_NULL)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Xodim kelishi"
        verbose_name_plural = "Xodim kelishlari"
        ordering = ["-created"]

    def __str__(self):
        return f"{self.full_name} — {self.get_status_display()}"


class Setting(models.Model):
    """Yagona qator — umumiy sozlamalar (TZ 4.8, 5.5). Admin login/parol endi
    bu yerda emas — Django'ning o'z foydalanuvchi tizimi (auth.User, "Xodim"
    belgisi) orqali boshqariladi, /it-center → Foydalanuvchilar."""
    app_title = models.CharField(max_length=200, default="BnpzTest")
    offer_text = models.TextField("Ommaviy oferta matni", blank=True)
    offer_video = models.FileField("Ommaviy oferta video instruksiyasi", upload_to="offer/", null=True, blank=True)

    class Meta:
        verbose_name = "Sozlama"
        verbose_name_plural = "Sozlamalar"

    def __str__(self):
        return self.app_title

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
