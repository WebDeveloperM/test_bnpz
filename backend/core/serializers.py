from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import (
    Test, Question, Option, Employee, Result, QuestionGroup, Recording, ActivityLog,
    AdminRole, AdminProfile,
)
from .perms import PERMISSION_KEYS, clean_permissions

User = get_user_model()


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ["id", "created", "actor", "actor_name", "action", "description", "meta"]


def _abs_image_url(obj, context):
    """Rasmning to'liq manzili. `request` kontekstda bo'lmasa nisbiy yo'l
    qaytadi — bu ham ishlaydi, chunki frontend va /media bitta manzildan
    (nginx) beriladi."""
    if not obj.image:
        return None
    request = (context or {}).get("request")
    return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class OptionPublicSerializer(serializers.ModelSerializer):
    """Xodimga yuboriladi — to'g'ri javob ko'rsatilmaydi."""
    text_i18n = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Option
        fields = ["id", "text", "text_i18n", "image_url"]

    def get_text_i18n(self, obj):
        """{"ru": "...", "uz-cyrl": "..."} — til almashtirilganda ishlatiladi."""
        return {lang: (values or {}).get("text") for lang, values in (obj.i18n or {}).items()
                if (values or {}).get("text")}

    def get_image_url(self, obj):
        return _abs_image_url(obj, self.context)


class QuestionPublicSerializer(serializers.ModelSerializer):
    options = OptionPublicSerializer(many=True, read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)

    class Meta:
        model = Question
        fields = ["id", "qtype", "text", "points", "group_name", "options"]


class TestInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Test
        fields = ["id", "name", "mode", "introduction", "grading_scale",
                  "pass_percent", "time_limit", "time_limit_scope", "instant_feedback", "proctoring"]


class ResultSerializer(serializers.ModelSerializer):
    tsex = serializers.CharField(source="test.tsex", read_only=True, default="")

    class Meta:
        model = Result
        fields = ["id", "full_name", "tabel_number", "test_name", "tsex", "correct", "total",
                  "pct", "grade", "passed", "violations", "share_stopped", "interrupted", "created"]


def recording_media_url(recording, request):
    """Video yozuv faylining manzili — administrator tokeni bilan.

    Video yozuvlar (xodimning ekrani va yuzi!) endi ochiq /media orqali
    berilmaydi: server ularni faqat haqiqiy administrator tokeni bilan beradi
    (qarang: `MediaRecordingView`). Token so'rov parametrida yuboriladi, chunki
    <video src=...> teg Authorization sarlavha qo'sha olmaydi."""
    if not recording.file:
        return None
    url = request.build_absolute_uri(recording.file.url) if request else recording.file.url
    token = getattr(request, "auth", None) if request else None
    if token:
        url += ("&" if "?" in url else "?") + "token=" + token
    return url


class RecordingSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Recording
        fields = ["id", "kind", "url", "created"]

    def get_url(self, obj):
        return recording_media_url(obj, self.context.get("request"))


class ResultDetailSerializer(ResultSerializer):
    recordings = serializers.SerializerMethodField()

    class Meta(ResultSerializer.Meta):
        fields = ResultSerializer.Meta.fields + ["answers", "recordings"]

    def get_recordings(self, obj):
        # Video ba'zan submit'dan keyin yuklanadi, shu sabab attempt orqali qidiramiz —
        # bu vaqt tartibidan qat'i nazar to'g'ri natijani beradi.
        qs = obj.attempt.recordings.all() if obj.attempt_id else obj.recordings.all()
        return RecordingSerializer(qs, many=True, context=self.context).data


class OptionAdminSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    text = serializers.CharField(required=False, allow_blank=True)
    match_text = serializers.CharField(required=False, allow_blank=True)
    i18n = serializers.JSONField(required=False)
    # Rasm alohida (multipart) endpoint orqali yuklanadi — bu yerda faqat
    # ko'rsatish uchun, shuning uchun `read_only`.
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Option
        fields = ["id", "text", "is_correct", "match_text", "image_url", "order", "i18n"]

    def get_image_url(self, obj):
        return _abs_image_url(obj, self.context)


class QuestionGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionGroup
        fields = ["id", "test", "name", "order"]


class QuestionAdminSerializer(serializers.ModelSerializer):
    options = OptionAdminSerializer(many=True, required=False)
    image_url = serializers.SerializerMethodField()
    i18n = serializers.JSONField(required=False)

    class Meta:
        model = Question
        fields = ["id", "test", "group", "qtype", "text", "points", "explanation",
                  "correct_text", "image_url", "order", "options", "i18n"]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    def validate(self, attrs):
        qtype = attrs.get("qtype") or getattr(self.instance, "qtype", None)
        if qtype in ("text", "fillblank"):
            correct_text = attrs.get("correct_text") or getattr(self.instance, "correct_text", "")
            if not correct_text.strip():
                raise serializers.ValidationError({"correct_text": "To'g'ri javobni kiriting."})
            return attrs

        options = attrs.get("options")
        if options is None and self.instance is not None:
            options = [
                {"is_correct": o.is_correct, "match_text": o.match_text} for o in self.instance.options.all()
            ]
        options = options or []
        if len(options) < 2:
            raise serializers.ValidationError({"options": "Kamida 2 ta variant kerak."})
        if qtype == "matching":
            match_texts = [(o.get("match_text") or "").strip() for o in options]
            if any(not m for m in match_texts):
                raise serializers.ValidationError(
                    {"options": "Har bir chap element uchun mos javobni (o'ng ustun) kiriting."})
            # Mos javoblar takrorlanmasligi kerak — aks holda bir javobni bir
            # necha juftga qo'yib to'g'ri hisoblatib olish mumkin bo'lardi
            # (har juft mustaqil tekshiriladi, 1:1 moslik shart emas edi).
            if len(set(match_texts)) != len(match_texts):
                raise serializers.ValidationError(
                    {"options": "Mos javoblar (o'ng ustun) takrorlanmasligi kerak."})
        elif qtype != "ordering" and not any(o.get("is_correct") for o in options):
            raise serializers.ValidationError({"options": "Kamida bitta to'g'ri variant belgilang."})
        return attrs

    def create(self, validated_data):
        options_data = validated_data.pop("options", [])
        question = Question.objects.create(**validated_data)
        self._save_options(question, options_data)
        return question

    def update(self, instance, validated_data):
        options_data = validated_data.pop("options", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        if options_data is not None:
            self._save_options(instance, options_data)
        return instance

    @staticmethod
    def _save_options(question, options_data):
        """Variantlarni id bo'yicha YANGILAYDI, o'chirib qaytadan yaratmaydi.

        Ilgari bu yerda `options.all().delete()` + qaytadan yaratish bor edi.
        Bu ikki muammo tug'dirardi:
          • variantning RASMI yo'qolardi — savol matnini bir harfga o'zgartirib
            saqlash ham barcha variant rasmlarini o'chirib yuborardi;
          • har saqlashda variant id'lari o'zgarardi, ya'ni o'sha paytda test
            topshirayotgan xodimning saqlangan javoblari va variantlar tartibi
            (`Attempt.layout`, `locked_answers`) mavjud bo'lmagan id'larga
            ishora qilib qolardi.
        Shuning uchun: id kelgan variant yangilanadi, id'siz variant yaratiladi,
        ro'yxatda umuman qolmagani esa o'chiriladi."""
        kept_ids = []
        for idx, opt in enumerate(options_data):
            fields = {
                "text": opt.get("text", ""),
                "is_correct": opt.get("is_correct", False),
                "match_text": opt.get("match_text", ""),
                "order": opt.get("order", idx),
                "i18n": opt.get("i18n") or {},
            }
            # `image` bu yerda umuman yo'q — u alohida endpoint orqali
            # yuklanadi, ya'ni savolni saqlash unga hech qachon tegmaydi.
            opt_id = opt.get("id")
            existing = question.options.filter(pk=opt_id).first() if opt_id else None
            if existing:
                for field, value in fields.items():
                    setattr(existing, field, value)
                existing.save()
                kept_ids.append(existing.pk)
            else:
                created = Option.objects.create(question=question, **fields)
                kept_ids.append(created.pk)

        # Administrator formadan olib tashlagan variantlar — ular bilan birga
        # rasm fayli ham diskdan ketadi, aks holda "yetim" fayl qolib ketardi.
        removed = question.options.exclude(pk__in=kept_ids)
        for old in removed:
            if old.image:
                old.image.delete(save=False)
        removed.delete()


class TestAdminSerializer(serializers.ModelSerializer):
    question_count = serializers.SerializerMethodField()

    def get_question_count(self, obj):
        # Ro'yxatda son `annotate` bilan bitta so'rovda keladi (TestAdminViewSet).
        # Yangi yaratilgan test javobida annotatsiya bo'lmaydi — o'shanda sanaymiz.
        annotated = getattr(obj, "question_count_annotated", None)
        return annotated if annotated is not None else obj.questions.count()

    class Meta:
        model = Test
        fields = ["id", "name", "tsex", "mode", "introduction", "grading_scale", "pass_percent",
                  "time_limit", "time_limit_scope", "shuffle_questions", "shuffle_options", "sample_count",
                  "common_question_count", "is_common_pool", "instant_feedback", "proctoring", "grade_thresholds",
                  "question_count", "created"]
        # Video nazorat har doim yoqilgan — administrator uni o'chira olmaydi,
        # shuning uchun maydon faqat o'qish uchun (admin panelida ham
        # ko'rsatilmaydi). Xodim ilovasi uni `TestInfoSerializer` orqali oladi.
        read_only_fields = ["created", "proctoring"]

    def validate(self, attrs):
        sample_count = attrs.get("sample_count", getattr(self.instance, "sample_count", 0))
        common_question_count = attrs.get(
            "common_question_count", getattr(self.instance, "common_question_count", 0)
        )
        if sample_count and common_question_count > sample_count:
            raise serializers.ValidationError({
                "common_question_count": "Umumiy savollar soni beriladigan savollar sonidan oshmasligi kerak.",
            })
        return attrs

    def create(self, validated_data):
        validated_data["proctoring"] = True
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data["proctoring"] = True
        return super().update(instance, validated_data)


# Ism-familiya va parol bilan kiradigan xodimlar — BnpzId (employee_service)
# ro'yxatida yo'q, ya'ni zavod xodimi emas, ishga kirmoqchi bo'lgan nomzod.
# Ularning bo'limi doim shu qiymat bo'ladi: bo'lim/sex faqat haqiqiy xodimlarda
# bo'ladi va u BnpzId'dan avtomatik keladi.
CANDIDATE_DEPARTMENT = "Nomzod"


class EmployeeAdminSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    assigned_test_name = serializers.CharField(source="assigned_test.name", read_only=True, default=None)
    is_manual = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ["id", "full_name", "password", "department", "assigned_test", "assigned_test_name",
                  "status", "language", "is_manual", "created"]
        read_only_fields = ["created"]

    def get_is_manual(self, obj):
        return not obj.external_slug

    def create(self, validated_data):
        password = validated_data.pop("password", None) or "1234"
        employee = Employee(**validated_data)
        employee.password = password
        # Bu yo'l bilan yaratilgan xodim har doim qo'lda kiritilgan (BnpzId'da yo'q)
        # bo'ladi, shuning uchun bo'lim so'ralmaydi ham, saqlanmaydi ham.
        employee.department = CANDIDATE_DEPARTMENT
        employee.save()
        return employee

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if password:
            instance.password = password
        # BnpzId'dan kelgan xodimda bo'lim sinxronizatsiyadan keladi — unga tegmaymiz.
        if not instance.external_slug:
            instance.department = CANDIDATE_DEPARTMENT
        instance.save()
        return instance


# ------------------------------------------- Rollar va panel foydalanuvchilari ---

class AdminRoleSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = AdminRole
        fields = ["id", "name", "description", "permissions", "user_count", "created"]
        read_only_fields = ["created"]

    def get_user_count(self, obj):
        return obj.users.count()

    def validate_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Rol nomini kiriting.")
        return value

    def validate_permissions(self, value):
        # Noma'lum kalitni jimgina tashlab yubormaymiz: superuser ruxsat
        # bergandek his qilib, keyin u ishlamaganini tushunmay qolmasligi kerak.
        if not isinstance(value, list):
            raise serializers.ValidationError("Ruxsatlar ro'yxat ko'rinishida bo'lishi kerak.")
        unknown = [v for v in value if v not in PERMISSION_KEYS]
        if unknown:
            raise serializers.ValidationError("Noma'lum ruxsat: " + ", ".join(map(str, unknown)))
        return clean_permissions(value)


class AdminUserSerializer(serializers.ModelSerializer):
    """Panel administratori: login, parol va rol.

    Parol faqat YOZISH uchun — javobda hech qachon qaytmaydi. Tahrirlashda
    bo'sh qoldirilsa eski parol o'zgarishsiz qoladi, ya'ni rolni almashtirish
    uchun parolni qayta kiritish shart emas."""

    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    role = serializers.PrimaryKeyRelatedField(
        queryset=AdminRole.objects.all(), required=False, allow_null=True,
    )
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "password",
                  "role", "role_name", "is_superuser", "is_active", "last_login"]
        # `is_superuser` — faqat o'qish uchun: superuser darajasi panel orqali
        # emas, /it-center orqali beriladi (panelning o'zi ham shunday deydi).
        # Aks holda API orqali oxirgi superuserni "oddiy"ga tushirib, rollar va
        # foydalanuvchilar boshqaruvisiz qolish mumkin edi.
        read_only_fields = ["last_login", "is_superuser"]

    def _role_of(self, obj):
        profile = getattr(obj, "admin_profile", None)
        return getattr(profile, "role", None)

    def get_role_name(self, obj):
        # Superuser rolga bog'liq emas — unga har doim hammasi ochiq.
        if obj.is_superuser:
            return "Superuser"
        role = self._role_of(obj)
        return role.name if role else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        role = self._role_of(instance)
        data["role"] = role.id if role else None
        return data

    def validate_username(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Loginni kiriting.")
        qs = User.objects.filter(username__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu login band.")
        return value

    def validate(self, attrs):
        # Parolsiz yaratilgan hisobga hech kim kira olmaydi — bu jimgina
        # ishlamaydigan hisob demak, shuning uchun majburiy qilamiz.
        if self.instance is None and not (attrs.get("password") or "").strip():
            raise serializers.ValidationError({"password": "Parolni kiriting."})

        # Faolsizlantirish himoyasi. O'chirish allaqachon taqiqlangan edi
        # (o'zini va oxirgi superuserni), lekin "Faol" belgisini olib tashlash
        # xuddi shu natijaga olib borardi: o'z hisobini o'chirib qo'ygan
        # superuser paneldan chiqib ketadi, u OXIRGI superuser bo'lsa —
        # rollar/foydalanuvchilar boshqaruviga hech kim kira olmay qoladi.
        if self.instance is not None and attrs.get("is_active") is False:
            request = (self.context or {}).get("request")
            me = getattr(getattr(request, "user", None), "username", None)
            if me and self.instance.username == me:
                raise serializers.ValidationError(
                    {"is_active": "O'z hisobingizni faolsizlantira olmaysiz."})
            if (self.instance.is_superuser and self.instance.is_active
                    and User.objects.filter(is_superuser=True, is_active=True)
                    .exclude(pk=self.instance.pk).count() == 0):
                raise serializers.ValidationError(
                    {"is_active": "Oxirgi superuserni faolsizlantirib bo'lmaydi."})
        return attrs

    def _set_role(self, user, role):
        profile, _created = AdminProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.save(update_fields=["role"])
        # `user.admin_profile` so'rov boshida o'qib qo'yilgan bo'lishi mumkin —
        # u ESKI rolni ushlab turadi va javob bazadagi haqiqiy holatdan farq
        # qiladi (panelda rol o'zgarmagandek ko'rinadi). Keshni yangilaymiz.
        user.admin_profile = profile

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        role = validated_data.pop("role", None)
        # Panelga kirish sharti — "Xodim (staff)" belgisi. Bu yerdan yaratilgan
        # har bir hisob aynan panel administratori, shuning uchun majburan
        # qo'yiladi; aks holda yaratilgan hisob kira olmay qolardi.
        user = User(is_staff=True, **validated_data)
        user.set_password(password)
        user.save()
        self._set_role(user, role)
        return user

    def update(self, instance, validated_data):
        password = (validated_data.pop("password", "") or "").strip()
        # "role" umuman yuborilmagan bo'lsa — tegmaymiz; `None` yuborilgan
        # bo'lsa — bu ataylab "rolni olib tashlash" degani. Ikkisi har xil.
        has_role = "role" in validated_data
        role = validated_data.pop("role", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.is_staff = True
        if password:
            instance.set_password(password)
        instance.save()
        if has_role:
            self._set_role(instance, role)
        return instance
