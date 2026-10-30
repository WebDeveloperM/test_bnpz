from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import SAFE_METHODS, BasePermission

from .perms import PERMISSION_KEYS, clean_permissions

ADMIN_TOKEN_SALT = "bnpztest-admin-token"
ADMIN_TOKEN_MAX_AGE = 60 * 60 * 12  # 12 soat


class AdminPrincipal:
    is_authenticated = True

    def __init__(self, username="", is_superuser=False, permissions=(), role_name=""):
        self.username = username
        # Superuser — barcha ruxsatlar, rolga bog'liq emas.
        self.is_superuser = is_superuser
        self.permissions = frozenset(permissions)
        self.role_name = role_name

    def has_perm_key(self, key):
        return self.is_superuser or key in self.permissions


def permissions_for(user):
    """Foydalanuvchining amaldagi ruxsatlari (rolidan olinadi).

    Superuserga har doim hammasi ochiq. Roli yo'q administrator hech qanday
    bo'lim ko'rmaydi — bo'sh ro'yxat qaytadi."""
    if user.is_superuser:
        return set(PERMISSION_KEYS)
    profile = getattr(user, "admin_profile", None)
    role = getattr(profile, "role", None)
    if role is None:
        return set()
    return set(clean_permissions(role.permissions))


def role_name_for(user):
    if user.is_superuser:
        return "Superuser"
    profile = getattr(user, "admin_profile", None)
    role = getattr(profile, "role", None)
    return role.name if role else ""


def make_admin_token(username=""):
    return signing.dumps({"admin": True, "username": username}, salt=ADMIN_TOKEN_SALT)


class AdminTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if header.startswith("Token "):
            token = header[len("Token "):].strip()
        else:
            token = request.query_params.get("token", "")
        if not token:
            return None
        try:
            payload = signing.loads(token, salt=ADMIN_TOKEN_SALT, max_age=ADMIN_TOKEN_MAX_AGE)
        except signing.BadSignature:
            raise AuthenticationFailed("Sessiya muddati tugagan. Qayta kiring.")

        username = payload.get("username", "")
        # Daraja va ruxsatlar tokendan EMAS, bazadan o'qiladi. Tokenga yozilganda,
        # rol o'zgartirilgan (yoki hisob o'chirilgan) bo'lsa ham eski token yana
        # 12 soat davomida eski ruxsatlar bilan ishlayverardi.
        user = (
            get_user_model().objects
            .filter(username=username)
            .select_related("admin_profile__role")
            .first()
        )
        if not user or not user.is_active or not user.is_staff:
            raise AuthenticationFailed("Hisob o'chirilgan yoki huquqi olib qo'yilgan. Qayta kiring.")

        principal = AdminPrincipal(
            username,
            is_superuser=user.is_superuser,
            permissions=permissions_for(user),
            role_name=role_name_for(user),
        )
        return (principal, token)

    def authenticate_header(self, request):
        # DRF buni aniqlamasa, autentifikatsiya xatosini 401 o'rniga 403 qilib
        # qaytaradi — frontend esa faqat 401'da avtomatik qayta login qiladi.
        return "Token"


class IsAdmin(BasePermission):
    """Panelga kirgan administrator + view talab qilgan bo'lim ruxsati.

    View o'zining `required_permission` (barcha so'rovlar uchun) yoki
    `required_write_permission` (faqat yozish uchun) atributida qaysi bo'limga
    tegishli ekanini aytadi. Menyuda bo'limni yashirish himoya emas — asosiy
    tekshiruv SHU YERDA, serverda turadi, shuning uchun ruxsati yo'q admin
    endpointga to'g'ridan-to'g'ri murojaat qilsa ham ma'lumot ola olmaydi."""

    message = "Bu bo'limga ruxsatingiz yo'q."

    def has_permission(self, request, view):
        if not request.auth:
            return False
        needed = getattr(view, "required_permission", None)
        if needed is None and request.method not in SAFE_METHODS:
            needed = getattr(view, "required_write_permission", None)
        if needed is None:
            return True
        return bool(getattr(request.user, "has_perm_key", lambda _k: False)(needed))


class IsSuperUser(BasePermission):
    """Faqat superuser. Rollar va foydalanuvchilarni boshqarish shu darajada
    qoladi — aks holda rol o'ziga o'zi ruxsat qo'shib, cheklovni aylanib
    o'tishi mumkin edi."""

    message = "Bu amal faqat superuser uchun."

    def has_permission(self, request, view):
        return bool(request.auth) and getattr(request.user, "is_superuser", False)


# Eski nom — kod bazasida qolgan joylar uchun.
IsSystemAdmin = IsSuperUser
