"""Tizim administratori paneli (/it-center).

Bu yerga faqat SUPERUSER kira oladi (pastdagi `has_permission`ga qarang) va
bu yerda tizimning BARCHA ma'lumotlari ko'rinadi — jumladan xom jadvallar,
amallar tarixi va Django'ning o'z o'zgarishlar jurnali. Test administratorlari
esa :2050 dagi soddalashtirilgan panel bilan ishlaydi.
"""
from django.apps import apps as django_apps
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils.html import format_html

from .models import (
    Test, Question, Option, QuestionGroup, Employee, Attempt, Result,
    Recording, Setting, ActivityLog, SyncedEmployee, ExpectedEmployee, CheckIn,
    AdminRole, AdminProfile,
)
from .perms import PERMISSIONS

User = get_user_model()


class ReadOnlyMixin:
    """Yozib olingan faktlar (natijalar, seanslar, video yozuvlar, tarix) —
    faqat KO'RISH uchun: qo'shib ham, o'zgartirib ham, o'chirib ham bo'lmaydi.

    Ilgari o'chirish ochiq edi va bu yerda ommaviy tanlab o'chirish amali
    (Django'ning "tanlanganlarni o'chirish") ishlardi — bir bosishda butun
    natijalar yoki video arxivini yo'q qilish mumkin edi. Bu ma'lumotlar
    tizim ishi natijasida paydo bo'ladi va dalil sifatida saqlanadi, shuning
    uchun ularni panel orqali o'chirishning yo'li qoldirilmagan."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        # "Tanlanganlarni o'chirish" ommaviy amali ham olib tashlanadi —
        # `has_delete_permission` uni odatda o'chiradi, lekin ro'yxatda
        # umuman ko'rinmasligi aniqroq.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


# ---------------------------------------------------------------- Testlar ---

class OptionInline(admin.TabularInline):
    model = Option
    extra = 4
    fields = ["order", "text", "is_correct", "match_text", "i18n"]


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ["order", "qtype", "text", "points", "group"]
    show_change_link = True


class QuestionGroupInline(admin.TabularInline):
    model = QuestionGroup
    extra = 0
    fields = ["order", "name"]


@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ["name", "tsex", "mode", "grading_scale", "pass_percent",
                    "time_limit", "proctoring", "is_common_pool", "question_count"]
    list_filter = ["mode", "grading_scale", "is_common_pool", "proctoring", "tsex"]
    search_fields = ["name", "tsex"]
    inlines = [QuestionGroupInline, QuestionInline]

    @admin.display(description="Savollar")
    def question_count(self, obj):
        return obj.questions.count()


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["short_text", "test", "group", "qtype", "points", "translations"]
    list_filter = ["test", "qtype", "group"]
    search_fields = ["text", "correct_text"]
    list_select_related = ["test", "group"]
    inlines = [OptionInline]

    @admin.display(description="Savol")
    def short_text(self, obj):
        return obj.text[:70]

    @admin.display(description="Tarjimalar")
    def translations(self, obj):
        langs = sorted((obj.i18n or {}).keys())
        return ", ".join(langs) if langs else "—"


@admin.register(Option)
class OptionAdmin(admin.ModelAdmin):
    """Variantlar odatda savol ichida tahrirlanadi — bu ro'yxat qidirish va
    ommaviy tekshirish uchun."""
    list_display = ["text", "question", "is_correct", "match_text", "order"]
    list_filter = ["is_correct", "question__test"]
    search_fields = ["text", "match_text"]
    list_select_related = ["question"]


@admin.register(QuestionGroup)
class QuestionGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "test", "order", "question_count"]
    list_filter = ["test"]
    search_fields = ["name"]
    list_select_related = ["test"]

    @admin.display(description="Savollar")
    def question_count(self, obj):
        return obj.questions.count()


# ---------------------------------------------------------------- Xodimlar ---

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["full_name", "department", "tabel_number", "assigned_test",
                    "status", "language", "login_type", "created"]
    list_filter = ["status", "language", "assigned_test", "department"]
    search_fields = ["full_name", "tabel_number", "external_slug"]
    list_select_related = ["assigned_test"]
    date_hierarchy = "created"
    # Parol `Employee.save()` da avtomatik hash qilinadi — bu yerga ochiq matn
    # yozilsa, saqlashda hash'ga aylanadi.

    @admin.display(description="Kirish usuli")
    def login_type(self, obj):
        return "BnpzId (yuz)" if obj.external_slug else "Parol (nomzod)"


@admin.register(SyncedEmployee)
class SyncedEmployeeAdmin(admin.ModelAdmin):
    """employee_service'dan sinxronlangan xodimlar (yuz orqali kirish uchun)."""
    list_display = ["full_name", "tabel_number", "department_name", "position",
                    "has_face", "has_photo", "synced_at"]
    list_filter = ["department_name", "section_name"]
    search_fields = ["full_name", "tabel_number", "slug", "position"]
    readonly_fields = ["synced_at"]
    date_hierarchy = "synced_at"

    @admin.display(description="Yuz belgisi", boolean=True)
    def has_face(self, obj):
        return bool(obj.face_embedding)

    @admin.display(description="Rasm", boolean=True)
    def has_photo(self, obj):
        return bool(obj.local_photo or obj.base_image_url)


@admin.register(ExpectedEmployee)
class ExpectedEmployeeAdmin(admin.ModelAdmin):
    """Bugun kelishi kutilayotgan xodimlar — yuz qidiruvi shu ro'yxat ichida boradi."""
    list_display = ["synced_employee", "department", "created"]
    search_fields = ["synced_employee__full_name", "synced_employee__tabel_number"]
    list_select_related = ["synced_employee"]
    date_hierarchy = "created"

    @admin.display(description="Bo'lim")
    def department(self, obj):
        return obj.synced_employee.department_name


@admin.register(CheckIn)
class CheckInAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Xodim kamera oldiga kelgandan keyingi kutish holati."""
    list_display = ["full_name", "department_name", "status", "test", "match_score", "created"]
    list_filter = ["status", "test", "department_name"]
    search_fields = ["full_name"]
    list_select_related = ["test", "employee", "synced_employee"]
    date_hierarchy = "created"


# ------------------------------------------------- Seanslar va natijalar ---

@admin.register(Attempt)
class AttemptAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Test seansi. Bu yerda savollar tartibi, qulflangan javoblar va
    variantlar joylashuvi ham ko'rinadi — nizoli holatlarni tekshirish uchun."""
    list_display = ["id", "employee", "test", "completed", "language",
                    "question_total", "locked_total", "hints_used", "created"]
    list_filter = ["completed", "test", "language"]
    search_fields = ["employee__full_name", "token"]
    list_select_related = ["employee", "test"]
    date_hierarchy = "created"

    @admin.display(description="Savollar")
    def question_total(self, obj):
        return len(obj.question_ids or [])

    @admin.display(description="Qulflangan")
    def locked_total(self, obj):
        return len(obj.locked_answers or {})


@admin.register(Result)
class ResultAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ["full_name", "tabel_number", "test_name", "correct", "total",
                    "pct", "grade", "passed", "violations", "share_stopped", "created"]
    list_filter = ["passed", "test_name", "share_stopped", "grade"]
    search_fields = ["full_name", "tabel_number", "test_name"]
    date_hierarchy = "created"


@admin.register(Recording)
class RecordingAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Video nazorat yozuvlari. Fayl diskda turadi — bu yerda faqat yo'li."""
    list_display = ["id", "attempt", "kind", "watch", "created"]
    list_filter = ["kind"]
    search_fields = ["attempt__employee__full_name"]
    list_select_related = ["attempt", "attempt__employee"]
    date_hierarchy = "created"

    @admin.display(description="Video")
    def watch(self, obj):
        if not obj.file:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener">Ochish</a>', obj.file.url)


# ------------------------------------------------------------------ Tarix ---

@admin.register(ActivityLog)
class ActivityLogAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Ilova amallari tarixi — kim kirdi, kim test yaratdi, kim topshirdi."""
    list_display = ["created", "actor", "actor_name", "action", "description"]
    list_filter = ["actor", "action"]
    search_fields = ["actor_name", "description", "action"]
    readonly_fields = ["created", "actor", "actor_name", "action", "description", "meta"]
    date_hierarchy = "created"
    ordering = ["-created"]


@admin.register(LogEntry)
class LogEntryAdmin(ReadOnlyMixin, admin.ModelAdmin):
    """Django'ning O'Z o'zgarishlar jurnali: shu panel orqali kim, qaysi
    yozuvni, qachon qo'shgan/tahrirlagan/o'chirgan. `ActivityLog` ilova
    darajasidagi amallarni yozadi, bu esa ma'lumotlar bazasi darajasidagi
    tahrirlarni — ikkalasi bir-birini to'ldiradi."""
    list_display = ["action_time", "user", "content_type", "object_repr", "action_label", "change_message"]
    list_filter = ["action_flag", "content_type", "user"]
    search_fields = ["object_repr", "change_message"]
    list_select_related = ["user", "content_type"]
    date_hierarchy = "action_time"
    ordering = ["-action_time"]

    @admin.display(description="Amal")
    def action_label(self, obj):
        return {1: "Qo'shildi", 2: "O'zgartirildi", 3: "O'chirildi"}.get(obj.action_flag, obj.action_flag)


# ------------------------------------------------------------ Sozlamalar ---

@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    """Yagona qator — ilova nomi va ommaviy oferta matni/videosi."""
    list_display = ["app_title", "has_offer_text", "has_offer_video"]

    def has_add_permission(self, request):
        return not Setting.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Oferta matni", boolean=True)
    def has_offer_text(self, obj):
        return bool(obj.offer_text)

    @admin.display(description="Oferta videosi", boolean=True)
    def has_offer_video(self, obj):
        return bool(obj.offer_video)


# -------------------------------------------------------- Foydalanuvchilar ---

@admin.register(AdminRole)
class AdminRoleAdmin(admin.ModelAdmin):
    """Panel rollari. Odatda :2050 panelning "Rollar" bo'limidan boshqariladi —
    bu yerda ular xom ko'rinishda (JSON kalitlar ro'yxati) turadi."""

    list_display = ["name", "description", "permission_list", "user_count"]
    search_fields = ["name", "description"]

    @admin.display(description="Ruxsatlar")
    def permission_list(self, obj):
        labels = {p["key"]: p["label"] for p in PERMISSIONS}
        if not obj.permissions:
            return format_html('<span style="color:#D9480F">hech qanday bo\'lim</span>')
        return ", ".join(labels.get(k, k) for k in obj.permissions)

    @admin.display(description="Administratorlar")
    def user_count(self, obj):
        return obj.users.count()


class AdminProfileInline(admin.StackedInline):
    """Foydalanuvchi sahifasida rolni shu yerda tanlanadi — alohida jadvalga
    o'tishga hojat qolmasin."""

    model = AdminProfile
    can_delete = False
    verbose_name = "Panel roli"
    verbose_name_plural = "Panel roli"
    fields = ["role"]


class BnpzUserAdmin(UserAdmin):
    """Tizim foydalanuvchilari va ularning darajasi.

    Kundalik ishda bu sahifa endi shart emas: administratorlarni yaratish,
    parolini almashtirish va rol berish :2050 panelning "Foydalanuvchilar"
    bo'limida qilinadi. Bu yer — zaxira yo'l (masalan panelga hech kim kira
    olmay qolganda) va xom ma'lumotni ko'rish uchun.

    Ikki daraja ATAYLAB ajratilgan:

    • "Xodim maqomi (is_staff)" — :2050 paneliga kirish huquqi. Aynan nimani
      ko'rishini esa uning ROLI hal qiladi (pastdagi "Panel roli" bo'limi);
      rolsiz administrator kira oladi-yu, hech qanday bo'lim ko'rmaydi.

    • "Superuser" — rolga umuman bog'liq emas: unga panelning barcha bo'limlari,
      shu jumladan rollar va foydalanuvchilarni boshqarish, hamda shu sahifa
      (/it-center — xom ma'lumotlar bazasi) ochiq.

    Yangi superuserni belgilash: foydalanuvchini oching → "Ruxsatlar" bo'limida
    "Superuser" katakchasini belgilang → saqlang.
    """
    list_display = ["username", "full_name", "level", "panel_role", "is_active", "last_login", "date_joined"]
    list_filter = ["is_superuser", "is_staff", "is_active", "admin_profile__role"]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering = ["-is_superuser", "-is_staff", "username"]
    inlines = [AdminProfileInline]
    list_select_related = ["admin_profile__role"]

    @admin.display(description="Ism-familiya")
    def full_name(self, obj):
        return obj.get_full_name() or "—"

    @admin.display(description="Daraja")
    def level(self, obj):
        if obj.is_superuser:
            return format_html('<b style="color:#3366FF">Superuser</b>')
        if obj.is_staff:
            return "Administrator"
        return format_html('<span style="color:#8A93A6">Kirish huquqi yo\'q</span>')

    @admin.display(description="Panel roli")
    def panel_role(self, obj):
        if obj.is_superuser:
            return format_html('<span style="color:#8A93A6">barcha bo\'limlar</span>')
        if not obj.is_staff:
            return "—"
        role = getattr(getattr(obj, "admin_profile", None), "role", None)
        if role is None:
            # Rolsiz administrator jimgina "bo'sh panel" ko'radi — buni
            # ro'yxatdayoq ko'rinadigan qilamiz, aks holda sababini topish qiyin.
            return format_html('<b style="color:#D9480F">rol berilmagan</b>')
        return f"{role.name} ({len(role.permissions)} ta bo'lim)"


admin.site.unregister(User)
admin.site.register(User, BnpzUserAdmin)

# /it-center (Django admin)ning o'ziga faqat superuser (tizim administratori)
# kira oladi — oddiy "Xodim (is_staff)" belgili test administratorlar faqat
# :2050 panelga kiradi, bu yerga (xom ma'lumotlar bazasiga) emas.
admin.site.has_permission = lambda request: (
    request.user.is_active and request.user.is_superuser
)

# Django'ning o'z bo'limlari (auth, admin) standart holda inglizcha ko'rinadi —
# panelning qolgan qismi o'zbekcha bo'lgani uchun ular ham o'zbekchaga o'giriladi.
# Django'da o'zbek tarjimasi yo'q, shu sabab nomlar shu yerda qo'lda beriladi.
django_apps.get_app_config("auth").verbose_name = "Foydalanuvchilar va ruxsatlar"
django_apps.get_app_config("admin").verbose_name = "Tizim jurnali"

User._meta.verbose_name = "Foydalanuvchi"
User._meta.verbose_name_plural = "Foydalanuvchilar"
Group._meta.verbose_name = "Guruh (ruxsatlar to'plami)"
Group._meta.verbose_name_plural = "Guruhlar (ruxsatlar to'plami)"
LogEntry._meta.verbose_name = "O'zgarish yozuvi"
LogEntry._meta.verbose_name_plural = "O'zgarishlar tarixi"

admin.site.site_header = "BnpzTest — Tizim administratori"
admin.site.site_title = "BnpzTest — tizim boshqaruvi"
admin.site.index_title = "Barcha ma'lumotlar, foydalanuvchilar va amallar tarixi"
