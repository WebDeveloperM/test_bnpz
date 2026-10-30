"""Panel bo'limlari (ruxsat kalitlari) — yagona manba.

Muhim: qaysi rol nimani ko'rishi BU YERDA yozilmagan. Bu ro'yxat faqat
"umuman qanday ruxsatlar bor" degan savolga javob beradi. Har bir rolga
qaysi bo'limlar ochiqligini superuser panelning "Rollar" bo'limida o'zi
belgilaydi (`AdminRole.permissions` — shu kalitlardan iborat ro'yxat).

Bir xil kalitlarga ikkala tomon tayanadi:
  • server  — `IsAdmin` har bir view'ning `required_permission`ini tekshiradi;
  • panel   — menyu shu kalitlar bo'yicha yig'iladi.
Shuning uchun yangi bo'lim qo'shilganda kalit shu yerga ham qo'shilishi shart,
aks holda u hech bir rolga berib bo'lmaydigan bo'lib qoladi.

Rollar va foydalanuvchilarni boshqarish ataylab bu ro'yxatda YO'Q — u har doim
faqat superuserda qoladi. Aks holda rol o'ziga o'zi barcha ruxsatni berib,
cheklovni aylanib o'tishi mumkin edi.
"""

PERMISSIONS = [
    {
        "key": "expected",
        "label": "Kutilayotgan xodimlar",
        "group": "Kundalik ish",
        "hint": "Test topshirishi kutilayotgan xodimlar ro'yxatini tuzish va tahrirlash.",
    },
    {
        "key": "checkins",
        "label": "Kutish ro'yxati",
        "group": "Kundalik ish",
        "hint": "Kamera orqali o'zini tanitgan xodimga test tayinlab, testni boshlab berish.",
    },
    {
        "key": "active",
        "label": "Faol seanslar",
        "group": "Kundalik ish",
        "hint": "Hozir test topshirayotganlar ro'yxati va ularning ekranini jonli ko'rish.",
    },
    {
        "key": "results",
        "label": "Test natijalari",
        "group": "Kundalik ish",
        "hint": "Natijalar ro'yxati, batafsil ko'rish, protokol va CSV eksport.",
    },
    {
        "key": "tests",
        "label": "Testlar va savollar",
        "group": "O'quv qismi",
        "hint": "Test yaratish/tahrirlash, savollar muharriri, savollarni fayldan import qilish. "
                "Testlar ro'yxatini KO'RISH bu ruxsatsiz ham mumkin — usiz xodimga test tayinlab bo'lmaydi.",
    },
    {
        "key": "settings",
        "label": "Sozlamalar",
        "group": "O'quv qismi",
        "hint": "Ommaviy oferta matni va videosi, xodimlarni sinxronlash.",
    },
    {
        "key": "sysstatus",
        "label": "Tizim holati",
        "group": "Tizim",
        "hint": "Server, baza va disk holati bo'yicha ko'rsatkichlar.",
    },
    {
        "key": "activity",
        "label": "Amallar tarixi",
        "group": "Tizim",
        "hint": "Kim, qachon, nima qilgani — tizimdagi barcha amallar jurnali.",
    },
    {
        "key": "recordings",
        "label": "Video yozuvlar",
        "group": "Tizim",
        "hint": "Video nazorat yozuvlari arxivi va eskilarini tozalash.",
    },
]

PERMISSION_KEYS = frozenset(p["key"] for p in PERMISSIONS)


def clean_permissions(values):
    """Ro'yxatdan tanilmagan kalitlarni olib tashlaydi va tartibga soladi.

    Rol saqlanayotganda ham, tokendan ruxsat o'qilayotganda ham ishlatiladi —
    kod o'zgarib, eski bo'lim olib tashlangan bo'lsa, bazadagi eskirgan kalit
    hech qanday ta'sir qilmasligi kerak."""
    if not isinstance(values, (list, tuple, set)):
        return []
    chosen = {v for v in values if v in PERMISSION_KEYS}
    # Tartib har doim PERMISSIONS bo'yicha — shunda saqlangan qiymat barqaror.
    return [p["key"] for p in PERMISSIONS if p["key"] in chosen]
