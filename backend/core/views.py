import csv
import io
import logging
import mimetypes
import os
import posixpath
import random
import re
import struct
import threading as _threading
import time
import uuid
import zipfile
from collections import OrderedDict
from datetime import date, timedelta
from django.db import connection, transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.static import serve as media_serve
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status, viewsets

from . import bnpzid, face
from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import SuspiciousFileOperation
from django.utils._os import safe_join
from rest_framework.exceptions import ValidationError
from .auth import (
    ADMIN_TOKEN_MAX_AGE, ADMIN_TOKEN_SALT,
    AdminTokenAuthentication, IsAdmin, IsSuperUser, make_admin_token,
    permissions_for, role_name_for,
)
from .perms import PERMISSIONS

User = get_user_model()
from .models import (
    Test, Question, Option, Employee, Attempt, Result, Setting, QuestionGroup, Recording,
    SyncedEmployee, CheckIn, ExpectedEmployee, ActivityLog, AdminRole,
)
from .serializers import (
    QuestionPublicSerializer, TestInfoSerializer, ResultSerializer, ResultDetailSerializer, OptionPublicSerializer,
    TestAdminSerializer, QuestionAdminSerializer, EmployeeAdminSerializer, QuestionGroupSerializer,
    ActivityLogSerializer, AdminRoleSerializer, AdminUserSerializer, recording_media_url,
)

logger = logging.getLogger(__name__)


def log_activity(actor, actor_name, action, description, meta=None):
    """Amallar tarixiga bitta yozuv qo'shadi — bu funksiya hech qachon asosiy
    so'rovni buzmasligi kerak, shu sabab xatolik yuz bersa jim yutib yuboriladi."""
    try:
        ActivityLog.objects.create(
            actor=actor, actor_name=actor_name or "", action=action,
            description=description, meta=meta or {},
        )
    except Exception:
        pass



# O'zbek matnida apostrof turli belgilar bilan yoziladi (klaviatura, Word'ning
# avtomatik almashtirishi, nusxa ko'chirish manbasiga qarab). Ular ko'zga bir xil
# ko'rinadi, shuning uchun "to'g'ri" va "to'g'ri" ni turlicha deb hisoblash —
# xodimni haqsiz ravishda xato baholash bo'lardi.
_APOSTROPHES = "’‘ʻʼʹ′`´"
_APOSTROPHE_MAP = {ord(ch): "'" for ch in _APOSTROPHES}


def _normalize_text(value):
    value = (value or "").strip().lower().translate(_APOSTROPHE_MAP)
    # Ichki ortiqcha bo'shliqlar ham farq qilmasin ("5  bar" == "5 bar").
    value = " ".join(value.split())
    try:
        # Vergul kasr ajratgichi bo'lishi mumkin ("5,5") — nuqtaga keltiramiz,
        # aks holda "5,5" son deb tanilmay, "5.5" bilan teng bo'lmay qolardi.
        return str(float(value.replace(",", ".")))
    except ValueError:
        return value


DEFAULT_GRADE_THRESHOLDS = {
    "5": [{"min": 90, "grade": "5"}, {"min": 75, "grade": "4"}, {"min": 60, "grade": "3"}, {"min": 0, "grade": "2"}],
    "100": [{"min": 86, "grade": "5"}, {"min": 71, "grade": "4"}, {"min": 55, "grade": "3"}, {"min": 0, "grade": "2"}],
}


def _scale_grade(test, pct):
    if test.grading_scale == "foiz":
        return None
    thresholds = test.grade_thresholds or DEFAULT_GRADE_THRESHOLDS.get(test.grading_scale, [])
    if not thresholds:
        return None
    thresholds = sorted(thresholds, key=lambda t: -float(t.get("min", 0)))
    for th in thresholds:
        if pct >= float(th.get("min", 0)):
            return str(th.get("grade", ""))
    return str(thresholds[-1].get("grade", "")) if thresholds else None


IMPORT_QTYPES = {"single", "multiple", "truefalse", "text", "fillblank"}

# Asosiy til — savolning `text`/`options[].text` maydonlarida shu tilda saqlanadi.
# Qolgan tillar `i18n` ichida tarjima sifatida yotadi.
BASE_LANG = "uz"

# Import faylida til belgisi turlicha yozilishi mumkin — hammasini qabul qilamiz,
# chunki faylni oddiy foydalanuvchi (dasturchi emas) qo'lda yozadi.
LANG_ALIASES = {
    "uz": BASE_LANG, "uzb": BASE_LANG, "lotin": BASE_LANG, "latin": BASE_LANG, "ozbek": BASE_LANG,
    "ru": "ru", "rus": "ru", "russ": "ru", "russian": "ru", "русский": "ru", "рус": "ru",
    "krill": "uz-cyrl", "kril": "uz-cyrl", "kiril": "uz-cyrl", "kirill": "uz-cyrl",
    "cyrl": "uz-cyrl", "cyrillic": "uz-cyrl", "uz-cyrl": "uz-cyrl",
    "кирилл": "uz-cyrl", "кирил": "uz-cyrl", "крилл": "uz-cyrl", "крил": "uz-cyrl",
}
LANG_LABELS = {BASE_LANG: "o'zbekcha", "ru": "ruscha", "uz-cyrl": "krillcha"}


def _tr(obj, lang, field):
    """Question/Option obyektining tanlangan tildagi matni.
    Tarjima bo'lmasa asosiy tildagi matn qaytariladi — test hech qachon
    bo'sh matn bilan to'xtab qolmasligi kerak."""
    if lang and lang != BASE_LANG:
        value = ((obj.i18n or {}).get(lang) or {}).get(field)
        if value:
            return value
    return getattr(obj, field)


def _clean_lang(value, fallback=BASE_LANG):
    """Mijozdan kelgan til kodini tekshiradi — notanish qiymat asosiy tilga tushadi."""
    return value if value in dict(Employee.LANG_CHOICES) else fallback


def _tr_all(obj, field):
    """Barcha tillardagi matn: {"ru": "...", "uz-cyrl": "..."} (asosiy tilsiz).
    Xodim tilni test davomida almashtirganda server bilan qayta bog'lanmasligi
    uchun barcha tillar savol bilan birga bir marta yuboriladi."""
    out = {}
    for lang, values in (obj.i18n or {}).items():
        value = (values or {}).get(field)
        if value:
            out[lang] = value
    return out


def _lang_marker(line):
    """"#ru", "@rus", "[krill]" kabi til belgisini aniqlaydi. Til belgisi bo'lmasa None.

    Faqat butun qatordan iborat belgi qabul qilinadi — shu sabab "-15 bar" kabi
    variant qatorlari yoki "#1 Savol?" kabi raqamlash bilan chalkashmaydi."""
    m = re.match(r"^[#@\[]\s*([A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ\-]+)\s*\]?$", line.strip())
    return LANG_ALIASES.get(m.group(1).strip().lower()) if m else None


def _parse_txt_section(lines):
    """Bitta tildagi bo'limni ajratadi -> (savol matni, variantlar, ochiq javob)."""
    question_text = re.sub(r"^\d+[.)]\s*", "", lines[0]).strip()
    text_answer = None
    options = []
    for line in lines[1:]:
        if line.startswith("="):
            text_answer = line[1:].strip()
        elif line.startswith("+"):
            options.append({"text": line[1:].strip(), "is_correct": True})
        elif line.startswith("-"):
            options.append({"text": line[1:].strip(), "is_correct": False})
        else:
            question_text += " " + line
    return question_text, options, text_answer


def _attach_translation(payload, lang, text, options, text_answer):
    """Tarjimani savol payload'iga biriktiradi. Xato bo'lsa xabar matnini qaytaradi.

    To'g'ri javob faqat asosiy tilda belgilanadi — tarjimadan faqat MATN olinadi.
    Shuning uchun variantlar tartibi tillar bo'ylab bir xil bo'lishi shart: ruscha
    2-variant o'zbekcha 2-variantning tarjimasi deb qabul qilinadi. Amalda bu doim
    shunday, lekin faylda bitta qator tushib qolsa javoblar surilib ketib, ruschada
    boshqa variant to'g'ri hisoblanib qolardi — quyidagi tekshiruvlar shundan saqlaydi.
    """
    label = LANG_LABELS.get(lang, lang)
    if not text:
        return f"{label} tarjimada savol matni yo'q — tarjima o'tkazib yuborildi."

    if payload["qtype"] in ("text", "fillblank"):
        if not text_answer:
            return f"{label} tarjimada to'g'ri javob (\"=\" bilan) ko'rsatilmagan — tarjima o'tkazib yuborildi."
        payload.setdefault("i18n", {})[lang] = {"text": text, "correct_text": text_answer}
        return None

    base_options = payload.get("options") or []
    if len(options) != len(base_options):
        return (f"{label} tarjimada variantlar soni mos emas "
                f"(asosiy tilda {len(base_options)} ta, tarjimada {len(options)} ta) — "
                f"tarjima o'tkazib yuborildi.")
    mismatched = [i + 1 for i, (b, t) in enumerate(zip(base_options, options))
                  if b["is_correct"] != t["is_correct"]]
    if mismatched:
        return (f"{label} tarjimada \"+\"/\"-\" belgilari mos kelmadi "
                f"({', '.join(map(str, mismatched))}-variant) — variantlar tartibi barcha tillarda "
                f"bir xil bo'lishi kerak, tarjima o'tkazib yuborildi.")

    payload.setdefault("i18n", {})[lang] = {"text": text}
    for base_opt, tr_opt in zip(base_options, options):
        base_opt.setdefault("i18n", {})[lang] = {"text": tr_opt["text"]}
    return None


# CSV/Excel'da tarjima ustunlari: savol_ru, variant1_ru, javob_ru, savol_krill, ...
CSV_LANG_SUFFIXES = {
    "ru": ("_ru", "_rus"),
    "uz-cyrl": ("_krill", "_kril", "_kiril", "_kirill", "_cyrl"),
}


def _csv_value(row, base, suffixes):
    for suffix in suffixes:
        value = (row.get(base + suffix) or "").strip()
        if value:
            return value
    return ""


def _attach_csv_translations(row, payload):
    """CSV qatoridagi tarjima ustunlarini savolga biriktiradi -> xatolar ro'yxati."""
    errors = []
    for lang, suffixes in CSV_LANG_SUFFIXES.items():
        text = _csv_value(row, "savol", suffixes)
        if not text:
            continue  # bu til uchun tarjima berilmagan — savol asosiy tilda qoladi
        options = [
            {"text": _csv_value(row, f"variant{i}", suffixes), "is_correct": base_opt["is_correct"]}
            for i, base_opt in enumerate(payload.get("options") or [], start=1)
        ]
        if payload["qtype"] == "truefalse" and not any(o["text"] for o in options):
            options = [{"text": t, "is_correct": base_opt["is_correct"]}
                       for t, base_opt in zip(("Тўғри", "Нотўғри") if lang == "uz-cyrl" else ("Верно", "Неверно"),
                                              payload["options"])]
        if any(not o["text"] for o in options):
            errors.append(f"{LANG_LABELS.get(lang, lang)} tarjimada variant ustunlari to'liq emas "
                          f"— tarjima o'tkazib yuborildi.")
            continue
        err = _attach_translation(payload, lang, text, options, _csv_value(row, "javob", suffixes))
        if err:
            errors.append(err)
    return errors


def _parse_import_row(row, order):
    """CSV qatoridan QuestionAdminSerializer uchun payload tayyorlaydi. Bo'sh savol -> None."""
    text = (row.get("savol") or "").strip()
    if not text:
        return None

    qtype = (row.get("tur") or "single").strip().lower()
    if qtype not in IMPORT_QTYPES:
        qtype = "single"

    try:
        points = int((row.get("ball") or "1").strip() or "1")
    except ValueError:
        points = 1

    explanation = (row.get("izoh") or "").strip()
    correct_raw = (row.get("togri") or "").strip()

    if qtype in ("text", "fillblank"):
        return {
            "qtype": qtype, "text": text, "points": points, "explanation": explanation,
            "correct_text": correct_raw, "options": [], "order": order,
        }

    if qtype == "truefalse":
        variants = ["To'g'ri", "Noto'g'ri"]
    else:
        variants = [(row.get(f"variant{i}") or "").strip() for i in range(1, 5)]
        variants = [v for v in variants if v]

    correct_idx = set()
    for part in correct_raw.split(","):
        part = part.strip()
        if part.isdigit():
            correct_idx.add(int(part))

    options = [{"text": v, "is_correct": (i + 1) in correct_idx} for i, v in enumerate(variants)]
    return {
        "qtype": qtype, "text": text, "points": points, "explanation": explanation,
        "correct_text": "", "options": options, "order": order,
    }


def _parse_csv_questions(content, start_order):
    """CSV matnidan (savol,tur,ball,variant1..4,togri,izoh) savollar ro'yxatini tayyorlaydi."""
    reader = csv.DictReader(io.StringIO(content))
    payloads = []
    errors = []
    order = start_order
    for row_num, row in enumerate(reader, start=2):
        data = _parse_import_row(row, order)
        if data is None:
            continue
        for err in _attach_csv_translations(row, data):
            errors.append({"row": row_num, "error": err})
        data["_row"] = row_num
        payloads.append(data)
        order += 1
    return payloads, errors


def _parse_txt_questions(content, start_order):
    """Oddiy TXT formatdagi savollarni ajratadi.

    Har bir savol bo'sh qator bilan ajratiladi. Birinchi qator — savol matni
    (boshidagi "1." kabi raqamlash e'tiborsiz qoldiriladi). Keyingi qatorlar:
    "+variant matni" — to'g'ri javob, "-variant matni" — noto'g'ri javob,
    "=javob matni" — ochiq (matn) savol uchun to'g'ri javob.

    Savol ichida "#ru" / "#krill" kabi til belgisidan keyin o'sha savolning
    boshqa tildagi matni yoziladi (avval o'zbekcha, keyin ruscha, keyin krillcha):

        Nasos bosimi qancha?
        +5 bar
        -10 bar
        #ru
        Каким должно быть давление насоса?
        +5 бар
        -10 бар

    Til bo'limidan oldin bo'sh qator qoldirilsa ham ishlaydi — til belgisi bilan
    boshlangan blok avtomatik oldingi savolga biriktiriladi.
    """
    blocks = re.split(r"\n\s*\n", content.strip())
    payloads = []
    errors = []
    order = start_order

    for block_num, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        # Blokni til bo'limlariga ajratamiz: [(til yoki None, [qatorlar]), ...]
        sections = []
        cur_lang, cur_lines = None, []
        for line in lines:
            lang = _lang_marker(line)
            if lang:
                if cur_lines:
                    sections.append((cur_lang, cur_lines))
                cur_lang, cur_lines = lang, []
            else:
                cur_lines.append(line)
        if cur_lines:
            sections.append((cur_lang, cur_lines))
        if not sections:
            continue

        # Blok tarjima belgisi bilan boshlangan bo'lsa — bu oldingi savolning davomi.
        if sections[0][0] not in (None, BASE_LANG):
            if not payloads:
                errors.append({"row": block_num, "error": "Tarjima bo'limidan oldin savol yo'q."})
                continue
            for lang, sec_lines in sections:
                err = _attach_translation(payloads[-1], lang, *_parse_txt_section(sec_lines))
                if err:
                    errors.append({"row": payloads[-1]["_row"], "error": err})
            continue

        question_text, options, text_answer = _parse_txt_section(sections[0][1])
        translations = sections[1:]

        if not question_text:
            continue

        if text_answer is not None and not options:
            payload = {
                "qtype": "text", "text": question_text, "points": 1, "explanation": "",
                "correct_text": text_answer, "options": [], "order": order, "_row": block_num,
            }
        else:
            if len(options) < 2:
                errors.append({"row": block_num, "error": "Kamida 2 ta variant kerak (\"+\" yoki \"-\" bilan belgilangan)."})
                continue
            if not any(o["is_correct"] for o in options):
                errors.append({"row": block_num, "error": "Hech bo'lmaganda bitta to'g'ri variant (\"+\") belgilanmagan."})
                continue

            correct_count = sum(1 for o in options if o["is_correct"])
            texts_lower = {o["text"].strip().lower() for o in options}
            if len(options) == 2 and texts_lower == {"to'g'ri", "noto'g'ri"}:
                qtype = "truefalse"
            elif correct_count > 1:
                qtype = "multiple"
            else:
                qtype = "single"

            payload = {
                "qtype": qtype, "text": question_text, "points": 1, "explanation": "",
                "correct_text": "", "options": options, "order": order, "_row": block_num,
            }

        for lang, sec_lines in translations:
            err = _attach_translation(payload, lang, *_parse_txt_section(sec_lines))
            if err:
                errors.append({"row": block_num, "error": err})

        payloads.append(payload)
        order += 1

    return payloads, errors


def _grade_question(q, given, lang=BASE_LANG):
    """Bitta savol uchun berilgan javobni tekshiradi.
    (is_correct, answered, turga xos tafsilotlar lug'ati) qaytaradi.

    `lang` faqat NATIJADA ko'rsatiladigan matnlarga ta'sir qiladi — to'g'ri javob
    asosiy tilda bir marta belgilangan (variant id'lari barcha tillarda bir xil),
    shuning uchun baho tanlangan tilga bog'liq emas."""
    if q.qtype in ("text", "fillblank"):
        given_text = given if isinstance(given, str) else ""
        answered = bool(given_text.strip())
        # Xodim testni ruschada topshirib, javobni ruscha yozishi mumkin —
        # shuning uchun har qanday tildagi to'g'ri javob qabul qilinadi.
        accepted = [q.correct_text] + list(_tr_all(q, "correct_text").values())
        is_correct = answered and any(
            _normalize_text(given_text) == _normalize_text(a) for a in accepted if a
        )
        return is_correct, answered, {
            "given_text": given_text, "correct_text": _tr(q, lang, "correct_text"),
        }

    if q.qtype == "ordering":
        options_by_id = {o.id: o for o in q.options.all()}
        correct_sequence = [o.id for o in sorted(options_by_id.values(), key=lambda o: o.order)]
        given_sequence = [int(x) for x in (given or []) if str(x).isdigit()]
        answered = bool(given_sequence)
        is_correct = given_sequence == correct_sequence and len(given_sequence) == len(correct_sequence)
        return is_correct, answered, {
            "given_order": [_tr(options_by_id[i], lang, "text") for i in given_sequence if i in options_by_id],
            "correct_order": [_tr(options_by_id[i], lang, "text") for i in correct_sequence],
        }

    if q.qtype == "matching":
        options = list(q.options.all())
        given = given if isinstance(given, dict) else {}
        answered = any(bool(v) for v in given.values())
        pairs = []
        pairs_correct = 0
        for o in options:
            chosen = given.get(str(o.id), "")
            # Xodim tilni almashtirgan bo'lsa, tanlangan matn tarjima bo'lishi mumkin.
            accepted = {o.match_text} | set(_tr_all(o, "match_text").values())
            pair_ok = bool(chosen) and chosen in accepted
            if pair_ok:
                pairs_correct += 1
            pairs.append({"left": _tr(o, lang, "text"), "chosen": chosen,
                          "correct": _tr(o, lang, "match_text"), "is_correct": pair_ok})
        is_correct = bool(options) and pairs_correct == len(options)
        return is_correct, answered, {"pairs": pairs}

    options = list(q.options.all())
    correct_ids = {o.id for o in options if o.is_correct}
    chosen_ids = set(int(x) for x in (given or []) if str(x).isdigit())
    answered = bool(chosen_ids)
    is_correct = (chosen_ids == correct_ids and len(correct_ids) > 0)
    return is_correct, answered, {
        # `image` — variantning rasmi (bo'lsa). U tekshirish oynasida ham,
        # natija tahlilida ham ko'rsatiladi: rasmli variantda faqat matnni
        # ko'rsatish "qaysi rasmni tanlagandim?" degan savolni ochiq qoldirardi.
        # Nisbiy manzil (`/media/...`) — sahifa va media bitta manzildan beriladi.
        "options": [{"text": _tr(o, lang, "text"), "is_correct": o.is_correct,
                     "image": o.image.url if o.image else None,
                     "chosen": o.id in chosen_ids} for o in options],
    }


def _build_questions_payload(request, test, question_ids, attempt=None):
    """Berilgan tartibdagi savollarni (to'g'ri javobsiz) tayyorlaydi.

    `attempt` berilsa, aralashtirilgan tartib o'sha seansda saqlanadi va keyingi
    chaqiruvlarda (masalan xodim sahifani yangilagach) aynan qayta tiklanadi."""
    qmap = {
        q.id: q for q in Question.objects.filter(id__in=question_ids)
        .select_related("group").prefetch_related("options")
    }
    layout = dict(attempt.layout or {}) if attempt else {}
    layout_changed = False
    payload = []
    for qid in question_ids:
        q = qmap.get(qid)
        if not q:
            continue
        options = list(q.options.all())
        saved = layout.get(str(qid))
        if saved:
            by_id = {o.id: o for o in options}
            options = [by_id[i] for i in saved.get("options", []) if i in by_id] or options
            match_options = saved.get("match")
        else:
            match_options = None
            if q.qtype == "matching":
                match_options = [o.match_text for o in options]
                random.shuffle(match_options)
            if test.shuffle_options or q.qtype in ("ordering", "matching"):
                random.shuffle(options)
            if attempt is not None:
                layout[str(qid)] = {"options": [o.id for o in options], "match": match_options}
                layout_changed = True
        payload.append({
            "id": q.id,
            "qtype": q.qtype,
            "text": q.text,
            # Barcha tarjimalar savol bilan birga yuboriladi — xodim test davomida
            # tilni almashtirganda hech qanday so'rov jo'natilmaydi, matn darhol
            # almashadi va javoblari (variant id'lari o'zgarmagani uchun) saqlanadi.
            "text_i18n": _tr_all(q, "text"),
            "points": q.points,
            "group_name": q.group.name if q.group_id else None,
            "image": request.build_absolute_uri(q.image.url) if q.image else None,
            "match_options": match_options,
            # {asosiy matn: {"ru": tarjima, ...}} — RO'YXAT emas, LUG'AT, chunki
            # `match_options` mustaqil aralashtiriladi va indekslar variantlar
            # tartibiga mos kelmaydi. Mijoz tanlangan qiymatni (asosiy matnni)
            # o'zgartirmasdan, faqat ko'rsatiladigan yozuvni almashtiradi.
            "match_i18n": {
                o.match_text: _tr_all(o, "match_text") for o in options if o.match_text
            } if q.qtype == "matching" else None,
            # `context` shart: usiz variant rasmining to'liq manzili
            # shakllanmaydi (`_abs_image_url` `request` ni shu yerdan oladi).
            "options": OptionPublicSerializer(
                options, many=True, context={"request": request}).data,
        })
    if attempt is not None and layout_changed:
        attempt.layout = layout
        attempt.save(update_fields=["layout"])
    return payload


def _fmt_hms(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_ms(seconds):
    seconds = max(0, int(round(seconds)))
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def _fmt_num(value):
    return f"{value:.1f}".replace(".", ",")


def build_protocol(result):
    """"Протокол тестирования" shabloni uchun ma'lumotlarni tayyorlaydi (natijalar TZ 4.9/4.10)."""
    employee = result.employee
    attempt = result.attempt
    review = result.answers or []

    started = timezone.localtime(attempt.created) if attempt else None
    finished = timezone.localtime(result.created)
    duration_seconds = int((result.created - attempt.created).total_seconds()) if attempt else None

    total = result.total
    attempted = sum(1 for r in review if r.get("answered"))
    wrong = total - result.correct
    correct_pct = round((result.correct / total) * 100, 1) if total else 0
    wrong_pct = round((wrong / total) * 100, 1) if total else 0

    topics = OrderedDict()
    topics[None] = {"correct": 0, "wrong": 0, "time": 0, "points": 0, "count": 0}
    for r in review:
        key = r.get("group_name")
        t = topics.setdefault(key, {"correct": 0, "wrong": 0, "time": 0, "points": 0, "count": 0})
        t["count"] += 1
        if r.get("is_correct"):
            t["correct"] += 1
        else:
            t["wrong"] += 1
        t["time"] += r.get("time_seconds", 0)
        t["points"] += r.get("earned", 0)

    by_topic = []
    for name, t in topics.items():
        if t["count"]:
            result_pct = _fmt_num(round((t["correct"] / t["count"]) * 100, 1)) + "%"
            avg_time = _fmt_ms(t["time"] / t["count"])
            avg_points = _fmt_num(t["points"] / t["count"])
        else:
            result_pct = avg_time = avg_points = "-"
        by_topic.append({
            "name": name or result.test_name,
            "correct": t["correct"], "wrong": t["wrong"],
            "result_pct": result_pct, "avg_time": avg_time, "avg_points": avg_points,
        })

    per_question = [{
        "index": i + 1,
        "is_correct": bool(r.get("is_correct")),
        "time": _fmt_ms(r.get("time_seconds", 0)),
    } for i, r in enumerate(review)]

    return {
        "full_name": result.full_name,
        "department": employee.department if employee else "",
        "test_name": result.test_name,
        "date": finished.strftime("%d.%m.%Y"),
        "started_at": started.strftime("%H:%M:%S") if started else None,
        "finished_at": finished.strftime("%H:%M:%S"),
        "duration": _fmt_hms(duration_seconds) if duration_seconds is not None else None,
        "total": total,
        "attempted": attempted,
        "correct": result.correct,
        "wrong": wrong,
        "correct_pct": _fmt_num(correct_pct),
        "wrong_pct": _fmt_num(wrong_pct),
        "hints_used": attempt.hints_used if attempt else 0,
        "violations": result.violations,
        "points_earned": result.points_earned,
        "points_total": result.points_total,
        "result_pct": _fmt_num(result.pct),
        "grade": result.grade or "-",
        "per_question": per_question,
        "by_topic": by_topic,
        "generated_at": timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M:%S"),
    }




def _attempt_by_token(token, related=(), **filters):
    """Token bo'yicha seansni topadi. Token noto'g'ri shaklda bo'lsa (masalan
    brauzerda eskirgan/buzilgan qiymat qolib ketgan bo'lsa) Django UUID maydonida
    ValidationError ko'tarilib, 500 ("server ishlamayapti") xatosi qaytardi —
    bu yerda u oddiy "topilmadi" ga aylantiriladi, ya'ni mijoz tushunarli javob
    oladi va kirish sahifasiga qaytara oladi.

    Token bilan ishlaydigan HAR BIR endpoint shu funksiyadan foydalanishi kerak.

    Testi yoki xodimi o'chirilgan seans "topilmadi" deb qaraladi: seansning
    o'zi arxivda saqlanadi (`SET_NULL`), lekin uni davom ettirib bo'lmaydi —
    savollar va baholash mezoni endi mavjud emas. Bu tekshiruv shu yerda
    turgani uchun quyidagi barcha endpointlar `attempt.test` ni xavfsiz
    ishlatishi mumkin."""
    if not token:
        return None
    try:
        uuid.UUID(str(token))
    except (ValueError, AttributeError, TypeError):
        return None
    qs = Attempt.objects.filter(token=token, test__isnull=False, employee__isnull=False, **filters)
    if related:
        qs = qs.select_related(*related)
    return qs.first()


def _is_stale_attempt(attempt):
    """Tashlab ketilgan seansmi? (vaqti tugagan yoki juda eskirgan)

    Vaqt chegarasi butun test uchun bo'lsa — chegaradan oshgan seans tashlab
    ketilgan hisoblanadi (mijozdagi taymer uni avtomatik yakunlashi kerak edi;
    yakunlamagan bo'lsa, demak brauzer yopilgan). Boshqa hollarda 3 soatlik
    umumiy chegara qo'llanadi."""
    elapsed = (timezone.now() - attempt.created).total_seconds()
    test = attempt.test
    # Testi o'chirilgan seansni davom ettirib bo'lmaydi — u har doim
    # "tashlab ketilgan" hisoblanadi. (Ilgari bu yerda `test.time_limit`
    # to'g'ridan-to'g'ri o'qilib, "Tizim holati" sahifasi 500 bilan yiqilardi.)
    if test is None:
        return True
    if test.time_limit and test.time_limit_scope == "test":
        return elapsed > test.time_limit * 60
    return elapsed > STALE_ATTEMPT_SECONDS


def _session_payload(request, attempt):
    """Xodim ilovasi kutadigan seans ma'lumoti. Yangi seans uchun ham,
    sahifa yangilangandan keyin tiklash uchun ham shu funksiya ishlatiladi —
    ikkalasida bir xil savollar, bir xil variantlar tartibi qaytadi."""
    employee, test = attempt.employee, attempt.test
    return {
        "token": str(attempt.token),
        "language": attempt.language or employee.language,
        "employee": employee.full_name,
        "test": TestInfoSerializer(test).data,
        "questions": _build_questions_payload(request, test, attempt.question_ids, attempt),
        # Seans boshlanganidan beri o'tgan vaqt — butun test uchun taymer shundan
        # hisoblanadi, shuning uchun sahifa yangilansa ham vaqt nolga qaytmaydi.
        "elapsed_seconds": int((timezone.now() - attempt.created).total_seconds()),
        # Serverda allaqachon qulflangan (o'zgartirib bo'lmaydigan) javoblar.
        "locked_answers": attempt.locked_answers or {},
    }


def _finalize_interrupted(request, attempt):
    """Tashlab ketilgan (yoki sahifasi yangilangan) seansni majburan yakunlaydi.

    Faqat SERVER biladigan javoblar hisobga olinadi (`Attempt.locked_answers`) —
    brauzerdagi javoblarga bu yerda ishonib bo'lmaydi, chunki seans allaqachon
    tashlab ketilgan. Oddiy rejimda hech narsa qulflanmagan bo'lishi mumkin,
    ya'ni natija past chiqadi; bu ataylab shunday — seansni yarim tashlab
    ketishning oqibati bor.

    Natija "sahifa yangilangani sababli to'xtatildi" deb belgilanadi, ya'ni
    administrator uni oddiy natijadan ajrata oladi."""
    with transaction.atomic():
        # `of=("self",)` SHART: `employee`/`test` endi null bo'lishi mumkin,
        # ya'ni `select_related` LEFT OUTER JOIN hosil qiladi va PostgreSQL
        # "FOR UPDATE cannot be applied to the nullable side of an outer join"
        # deb rad etadi. `of` bilan qulf faqat seans qatoriga qo'yiladi.
        locked = (Attempt.objects.select_for_update(of=("self",))
                  .select_related("employee", "test").get(pk=attempt.pk))
        if locked.completed:
            return None
        answers = {str(k): v for k, v in (locked.locked_answers or {}).items()}
        return SubmitView()._grade_and_store(
            request, locked, answers, timings={}, violations=0,
            share_stopped=False, interrupted=True,
        )


def _create_attempt_session(request, employee, test):
    """Xodim uchun yangi test seansi (Attempt) yaratadi va Login/Checkin
    javoblarida ishlatiladigan umumiy javob shaklini qaytaradi.
    Savol topilmasa yoki xato bo'lsa (code, error) qaytaradi, aks holda (None, data)."""
    # Tugallanmagan seans bo'lsa — u DAVOM ETTIRILMAYDI, majburan yakunlanadi.
    #
    # Ilgari bunday seans davom ettirilardi (sahifani yangilab testni boshidan
    # boshlashning oldini olish uchun). Endi qoida qattiqroq: seansni tashlab
    # ketish yoki sahifani yangilash testni tugatadi. Aks holda xodim brauzer
    # xotirasini tozalab, qaytadan kirib, o'sha seansni davom ettirishi mumkin
    # edi — ya'ni taqiqni aylanib o'tish yo'li ochiq qolardi.
    #
    # Yangi seans esa baribir yaratiladi: bu yerga faqat ADMINISTRATOR testni
    # boshlaganda kelinadi, ya'ni bu ataylab qilingan qayta biriktirish.
    existing = (Attempt.objects.filter(employee=employee, test=test, completed=False)
                .order_by("-created").first())
    if existing and not _is_stale_attempt(existing):
        _finalize_interrupted(request, existing)
        # Majburiy yakunlash xodimni "topshirgan" holatiga o'tkazadi — lekin biz
        # unga hozir YANGI seans ochyapmiz. Holat qaytarilmasa, xodim ro'yxatda
        # "Topshirilgan" bo'lib ko'rinar va parol bilan qayta kira olmay qolardi.
        employee.refresh_from_db(fields=["status"])
        if employee.status != "assigned":
            employee.status = "assigned"
            employee.save(update_fields=["status"])

    own_qs = list(Question.objects.filter(test=test).values_list("id", flat=True))

    common_qs = []
    if test.common_question_count and not test.is_common_pool:
        pool = list(
            Question.objects.filter(test__is_common_pool=True).exclude(test=test).values_list("id", flat=True)
        )
        random.shuffle(pool)
        common_qs = pool[:test.common_question_count]

    if test.sample_count:
        # TZ: "Savollardan tasodifiy tanlab olish (masalan, 50 tadan 20 tasi)".
        # Ilgari shunchaki birinchi N ta olinardi — aralashtirish o'chiq bo'lsa
        # bankning oxiridagi savollar hech qachon chiqmasdi va barcha xodimlar
        # aynan bir xil savollarni olardi.
        own_take = max(test.sample_count - len(common_qs), 0)
        if own_take < len(own_qs):
            picked = set(random.sample(range(len(own_qs)), own_take))
            # Tanlov tasodifiy, lekin tartib asl holicha qoladi — savollarni
            # aralashtirishni alohida `shuffle_questions` sozlamasi hal qiladi.
            own_qs = [qid for i, qid in enumerate(own_qs) if i in picked]

    qs = own_qs + common_qs
    if test.shuffle_questions:
        random.shuffle(qs)

    if not qs:
        return "no_questions", "Testda savollar yo'q. Administratorga murojaat qiling."

    # Seans tili xodim profilidagi tildan boshlanadi. Ilgari standart "uz"
    # yozilardi va ruscha sozlangan xodim ham testni o'zbekchada boshlardi.
    attempt = Attempt.objects.create(employee=employee, test=test, question_ids=qs,
                                     language=employee.language or "uz")
    log_activity("employee", employee.full_name, "attempt_started",
                 f"{employee.full_name} \"{test.name}\" testini boshladi", {"test_id": test.id})
    return None, (attempt, _session_payload(request, attempt))


class EmployeeManualListView(APIView):
    """BnpzId (employee_service)da mavjud bo'lmagan, administrator tomonidan
    qo'lda (ism-familiya + parol bilan) yaratilgan xodimlar ro'yxati — kirish
    sahifasidagi "Ism-familiyangizni tanlang" ro'yxati uchun ishlatiladi."""

    def get(self, request):
        qs = (Employee.objects.filter(external_slug__isnull=True)
              .exclude(status="completed").order_by("full_name"))
        return Response([{"id": e.id, "full_name": e.full_name} for e in qs])


class EmployeeLoginView(APIView):
    """BnpzId'da mavjud bo'lmagan xodim uchun — administrator oldindan
    yaratib bergan ism-familiya va parol bilan kiradi. Yuz orqali kirishdan
    farqli o'laroq bu yerda kamera/rasm shart emas; muvaffaqiyatli kirgach,
    xodim ham xuddi yuz orqali kelgan xodim kabi "kutish" holatiga (CheckIn)
    tushadi — administrator "Kutish ro'yxati"dan uni ko'rib, lavozim/testni
    tanlab boshlab beradi (EmployeeIdentifyView bilan bir xil oqim)."""

    def post(self, request):
        employee_id = request.data.get("employee_id")
        password = request.data.get("password") or ""
        if not employee_id or not password:
            return Response({"code": "empty", "error": "Ism-familiyangizni tanlang va parolni kiriting."},
                            status=status.HTTP_400_BAD_REQUEST)

        employee = Employee.objects.filter(pk=employee_id, external_slug__isnull=True).first()
        if not employee:
            return Response({"code": "not_found",
                             "error": "Xodim topilmadi. Administratorga murojaat qiling."},
                            status=status.HTTP_404_NOT_FOUND)
        if not employee.check_password(password):
            return Response({"code": "bad_password", "error": "Parol noto'g'ri."},
                            status=status.HTTP_401_UNAUTHORIZED)
        if employee.status == "completed":
            return Response({"code": "completed",
                             "error": "Siz bu testni allaqachon topshirgansiz. Administratorga murojaat qiling."},
                            status=status.HTTP_409_CONFLICT)

        checkin = CheckIn.objects.create(
            employee=employee, full_name=employee.full_name, department_name=employee.department or "",
        )
        log_activity("employee", employee.full_name, "login",
                     f"{employee.full_name} ism/parol orqali tizimga keldi")
        return Response({
            "checkin_token": str(checkin.token),
            "full_name": checkin.full_name,
            "department": checkin.department_name,
        }, status=status.HTTP_201_CREATED)


class EmployeeOfferAcceptView(APIView):
    """Xodim ommaviy oferta shartlariga rozilik bildirganda chaqiriladi —
    faqat audit/tarix uchun qayd etadi, test darhol boshlanmaydi
    (Attempt allaqachon login/checkin bosqichida yaratilgan bo'ladi)."""

    def post(self, request):
        token = request.data.get("token")
        attempt = _attempt_by_token(token, related=("employee",))
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        log_activity("employee", attempt.employee.full_name, "offer_accepted",
                     f"{attempt.employee.full_name} ommaviy oferta shartlariga rozilik bildirdi")
        return Response({"ok": True})


class SubmitView(APIView):
    def post(self, request):
        token = request.data.get("token")
        answers = request.data.get("answers") or {}  # {"<qid>": [optionId, ...]}
        timings = request.data.get("timings") or {}  # {"<qid>": seconds}
        try:
            violations = max(0, int(request.data.get("violations", 0) or 0))
        except (TypeError, ValueError):
            violations = 0
        share_stopped = bool(request.data.get("share_stopped"))
        # Sahifa yangilangani sababli majburan yakunlanmoqda (qarang: TAQIQ
        # izohi `EmployeeSessionView` da).
        interrupted = bool(request.data.get("interrupted"))

        attempt = _attempt_by_token(token)
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # Ikki marta yakunlashdan himoya. "Yakunlash" tugmasi ikki marta bosilsa
        # (yoki tarmoq sekinligidan so'rov takrorlansa), ilgari har bir so'rov
        # alohida natija yaratardi — bitta testdan bir necha bir xil natija paydo
        # bo'lib, hisobot buzilardi.
        #
        # Seans qatori butun baholash davomida qulflanadi (`select_for_update`) —
        # qulf natija YARATILGANDAN keyin bo'shaydi. Bu muhim: agar qulf faqat
        # bayroq qo'yish uchun olinganda, parallel so'rov "yakunlangan, lekin
        # natija hali yo'q" oralig'iga tushib, xato qaytarardi. Endi u kutadi va
        # tayyor natijani oladi — ya'ni takroriy so'rov xodim uchun xatoga
        # aylanmaydi, shunchaki o'sha natijani ko'rsatadi.
        with transaction.atomic():
            # `of=("self",)` — faqat seans qatorini qulflaymiz. `employee`/`test`
            # null bo'lishi mumkin bo'lgani uchun `select_related` outer join
            # beradi, PostgreSQL esa uning nullable tomonini qulflashni rad etadi.
            attempt = (Attempt.objects.select_for_update(of=("self",))
                       .select_related("employee", "test").get(pk=attempt.pk))
            if attempt.completed:
                existing = Result.objects.filter(attempt=attempt).order_by("-id").first()
                if existing:
                    return Response(_result_response(existing))
                return Response({"error": "Seans allaqachon yakunlangan."},
                                status=status.HTTP_400_BAD_REQUEST)
            return Response(self._grade_and_store(
                request, attempt, answers, timings, violations, share_stopped, interrupted,
            ))

    def _grade_and_store(self, request, attempt, answers, timings, violations,
                         share_stopped, interrupted=False):
        """Seans qulflangan holda chaqiriladi (qarang: `post`)."""
        # Xodim test davomida tilni almashtirgan bo'lishi mumkin — natija va
        # protokol aynan u yakunlagan tilda saqlanadi.
        lang = _clean_lang(request.data.get("language"), attempt.employee.language)
        attempt.language = lang

        test = attempt.test
        questions = {q.id: q for q in Question.objects.filter(id__in=attempt.question_ids)
                     .select_related("group").prefetch_related("options")}

        total = 0
        correct_count = 0
        earned_points = 0
        total_points = 0
        review = []
        penalty_mode = test.mode == "jarima"

        locked = attempt.locked_answers or {}
        for qid in attempt.question_ids:
            q = questions.get(qid)
            if not q:
                continue
            total += 1
            total_points += q.points
            # Qulflangan javob mijoz yuborganidan ustun: "Tekshirish" orqali
            # to'g'ri javobni ko'rgandan keyin (yoki Maksimal rejimda savol
            # ortda qolgandan keyin) javobni o'zgartirib yuborish mumkin emas.
            given = locked[str(qid)] if str(qid) in locked else answers.get(str(qid))
            is_correct, answered, type_entry = _grade_question(q, given, lang)
            q_earned = 0
            if is_correct:
                correct_count += 1
                q_earned = q.points
                earned_points += q.points
            elif penalty_mode and answered:
                q_earned = -q.points
                earned_points -= q.points
            try:
                time_seconds = max(0, int(timings.get(str(qid), 0) or 0))
            except (TypeError, ValueError):
                time_seconds = 0
            review.append({
                "question": _tr(q, lang, "text"),
                "explanation": _tr(q, lang, "explanation"),
                "is_correct": is_correct,
                "answered": answered,
                "group_name": q.group.name if q.group_id else None,
                "points": q.points,
                "earned": q_earned,
                "time_seconds": time_seconds,
                **type_entry,
            })

        earned_points = max(0, earned_points)
        pct = round((earned_points / total_points) * 100) if total_points else 0
        passed = pct >= test.pass_percent
        grade = _scale_grade(test, pct)

        # Chaqiruvchi (`post`) allaqachon tranzaksiya ichida va seansni qulflagan —
        # bu yerda alohida tranzaksiya ochilmaydi.
        result = Result.objects.create(
            employee=attempt.employee, test=test, attempt=attempt,
            test_name=test.name, full_name=attempt.employee.full_name,
            tabel_number=attempt.employee.tabel_number,
            correct=correct_count, total=total, pct=pct,
            points_earned=earned_points, points_total=total_points,
            violations=violations,
            share_stopped=share_stopped,
            interrupted=interrupted,
            grade=grade or "", passed=passed,
            answers=review,
        )
        attempt.completed = True
        attempt.save(update_fields=["completed", "language"])
        attempt.employee.status = "completed"
        attempt.employee.save(update_fields=["status"])
        attempt.recordings.update(result=result)

        checkin = CheckIn.objects.filter(attempt=attempt).first()
        if checkin and checkin.synced_employee_id:
            ExpectedEmployee.objects.filter(synced_employee_id=checkin.synced_employee_id).delete()

        verdict_word = "o'tdi" if passed else "o'tmadi"
        why = " — sahifa yangilangani sababli majburan to'xtatildi" if interrupted else ""
        log_activity(
            "employee", result.full_name, "attempt_finished",
            f"{result.full_name} \"{test.name}\" testini yakunladi — {pct}% ({verdict_word}){why}",
            {"result_id": result.id, "pct": pct, "passed": passed,
             "violations": violations, "share_stopped": share_stopped,
             "interrupted": interrupted},
        )

        # Jonli ko'rish (WebRTC) seansini tozalaymiz — aks holda `_live_sessions`
        # lug'ati yakunlangan seanslar bilan cheksiz to'lib borardi (xotira oqishi).
        with _live_lock:
            _live_sessions.pop(str(attempt.id), None)

        return _result_response(result)


def _result_response(result):
    """Yakunlash javobining umumiy shakli. Takroriy "Yakunlash" so'rovi kelganda
    ham xuddi shu shakl (mavjud natijadan) qaytariladi, shuning uchun xodim
    ekranida hech qanday farq sezilmaydi."""
    return {
        "result": {
            "full_name": result.full_name, "test_name": result.test_name,
            "correct": result.correct, "total": result.total, "pct": result.pct,
            "grade": result.grade or None, "passed": result.passed,
            # Xodim natija ekranida testi NEGA yopilganini ko'rishi kerak —
            # aks holda "men tugatmagan edim-ku?" degan savol javobsiz qoladi.
            "interrupted": result.interrupted,
        },
        "review": result.answers or [],
    }


class CheckAnswerView(APIView):
    """Darhol javob nazorati (instant_feedback) yoqilgan testlar uchun."""

    def post(self, request):
        token = request.data.get("token")
        qid = request.data.get("question_id")
        given = request.data.get("answer")

        attempt = _attempt_by_token(token, related=("test",), completed=False)
        if not attempt or qid not in attempt.question_ids:
            return Response({"error": "Seans yoki savol topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        if not attempt.test.instant_feedback:
            return Response({"error": "Bu funksiya ushbu test uchun yoqilmagan."},
                            status=status.HTTP_403_FORBIDDEN)

        lang = _clean_lang(request.data.get("language"), attempt.language)
        # Savol test davomida administrator tomonidan o'chirilgan bo'lishi
        # mumkin — `get()` bu holatda 500 berardi, xodim esa "server ishlamayapti"
        # deb qolardi. Aniq javob qaytaramiz.
        q = Question.objects.prefetch_related("options").filter(pk=qid).first()
        if not q:
            return Response({"error": "Bu savol o'chirilgan. Keyingi savolga o'ting."},
                            status=status.HTTP_400_BAD_REQUEST)

        # To'g'ri javobni ko'rsatishdan OLDIN javobni qulflaymiz. Aks holda xodim
        # ataylab xato javob berib, javobni ko'rib, keyin to'g'rilab yuborardi —
        # bu rejimdagi har qanday testda 100% olish mumkin bo'lib qolgan edi.
        # Savol allaqachon tekshirilgan bo'lsa, javob o'zgarmaydi: qayta-qayta
        # tekshirib, variantlarni birma-bir sinab ko'rishning oldi olinadi.
        # Seans qatorini qulflaymiz — tez ketma-ket "Tekshirish" so'rovlari
        # `locked_answers` ni bir-birini yozib yubormasligi (savol qulfi
        # yo'qolmasligi) uchun. `of=("self",)`: employee/test nullable bo'lgani
        # uchun outer join hosil bo'ladi, qulf faqat seans qatoriga qo'yiladi.
        with transaction.atomic():
            locked_attempt = (Attempt.objects.select_for_update(of=("self",)).get(pk=attempt.pk))
            locked = locked_attempt.locked_answers or {}
            already = str(qid) in locked
            if already:
                given = locked[str(qid)]
            else:
                locked[str(qid)] = given
                locked_attempt.locked_answers = locked
                locked_attempt.hints_used += 1
                locked_attempt.save(update_fields=["locked_answers", "hints_used"])

        is_correct, _answered, entry = _grade_question(q, given, lang)
        return Response({
            "is_correct": is_correct,
            "explanation": _tr(q, lang, "explanation"),
            "locked": True,  # mijoz shu savol variantlarini bloklaydi
            **entry,
        })


class EmployeeSessionView(APIView):
    """YOPILGAN: test davomida sahifani yangilash TAQIQLANGAN.

    Ilgari bu endpoint sahifa yangilangandan keyin seansni tiklab berardi va
    xodim testni o'sha joyidan davom ettirardi. Endi qoida boshqacha: sahifani
    yangilagan xodim testga QAYTMAYDI — test o'sha ondagi javoblari bilan
    yakunlanadi (buni mijoz `POST /employee/submit/` ga `interrupted: true`
    yuborib bajaradi).

    Endpoint o'chirilmadi, chunki brauzerda eski nusxa ochiq qolgan bo'lishi
    mumkin — bunday mijoz jimgina testga qaytib kirmasligi, aniq rad javobini
    olishi kerak."""

    def get(self, request):
        return Response(
            {"error": "Test davomida sahifani yangilash mumkin emas. "
                      "Seans yakunlandi — administratorga murojaat qiling."},
            status=status.HTTP_410_GONE,
        )


class EmployeeLockAnswerView(APIView):
    """Javobni serverda qulflaydi (to'g'ri javobni ko'rsatmasdan).

    "Maksimal" rejimda savoldan keyingisiga o'tilganda chaqiriladi — shu rejimda
    orqaga qaytish taqiqlangani endi faqat brauzerda emas, serverda ham amal
    qiladi. Qulflangan javob keyin o'zgartirilmaydi."""

    def post(self, request):
        token = request.data.get("token")
        qid = request.data.get("question_id")
        given = request.data.get("answer")

        attempt = _attempt_by_token(token, related=("test",), completed=False)
        if not attempt or qid not in attempt.question_ids:
            return Response({"error": "Seans yoki savol topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # Qulf — parallel so'rovlar bir-birini yozib yubormasligi uchun (qarang:
        # CheckAnswerView). `of=("self",)`: faqat seans qatorini qulflaymiz.
        with transaction.atomic():
            locked_attempt = (Attempt.objects.select_for_update(of=("self",)).get(pk=attempt.pk))
            locked = locked_attempt.locked_answers or {}
            if str(qid) not in locked:
                locked[str(qid)] = given
                locked_attempt.locked_answers = locked
                locked_attempt.save(update_fields=["locked_answers"])
        return Response({"ok": True, "locked": True})


class RecordingUploadView(APIView):
    """Xodim yozib olayotgan ekran/yuz videosining BO'LAGINI qabul qiladi.

    Video test tugashini kutmaydi: mijoz har 10 soniyada bir bo'lak yuboradi
    (qarang: frontend/src/proctoring.js, CHUNK_MS). Bu yerda bo'laklar
    ketma-ket BITTA faylga qo'shib boriladi.

    Ilgari butun video oxirida bitta so'rovda kelardi. Ikki muammo bor edi:
    brauzer yopilsa yoki yuklash uzilsa BUTUN yozuv yo'qolardi, va barcha
    xodimlar testni bir vaqtda tugatgani uchun yuk aynan eng band lahzaga
    to'planardi.

    `index` — bo'lak tartibi. 0 yangi yozuv ochadi, qolganlari mavjud faylga
    qo'shiladi. Tartib muhim: WebM bo'laklari faqat to'g'ri ketma-ketlikda
    ulanganda ochiladi (birinchi bo'lakda konteyner sarlavhasi bo'ladi).
    Mijoz ularni navbat bilan yuboradi, bu yerda esa qator qulflanadi.

    Fayl diskda (MEDIA_ROOT/recordings/...) saqlanadi, bazada faqat yo'l turadi.
    """
    parser_classes = [MultiPartParser]

    def post(self, request):
        token = request.data.get("token")
        kind = request.data.get("kind")
        file = request.FILES.get("file")
        if kind not in ("screen", "face") or not file:
            return Response({"error": "Noto'g'ri so'rov."}, status=status.HTTP_400_BAD_REQUEST)
        index = _int_param(request.data.get("index"), 0)

        attempt = _attempt_by_token(token, related=("employee", "test"))
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        if index > 0:
            return self._append(attempt, kind, file)
        return self._start(attempt, kind, file)

    @staticmethod
    def _start(attempt, kind, file):
        """Birinchi bo'lak — yozuvni ochadi. TAKRORLANSA yangi yozuv yaratmaydi.

        Mijoz bo'lakni yubordi, server uni qabul qildi, lekin javob tarmoqda
        yo'qoldi — mijoz uchun bu "yetib bormadi" degani va u qayta yuboradi.
        Har safar yangi yozuv ochilsa, bitta seansda ikkita fayl paydo bo'lardi:
        birinchisi faqat sarlavha bilan yetim qolib, keyingi bo'laklar esa
        ikkinchisiga tushardi. Shuning uchun bu yerda takroriy birinchi bo'lak
        mavjud faylni QAYTA YOZADI — ya'ni amal necha marta takrorlansa ham
        natija bir xil bo'ladi."""
        with transaction.atomic():
            # Seans qatori qulflanadi. Aynan SEANS, chunki yozuv hali mavjud
            # bo'lmasligi mumkin — bo'sh natijani qulflab bo'lmaydi va ikkita
            # bir vaqtdagi "birinchi bo'lak" baribir ikkita yozuv yaratardi.
            Attempt.objects.select_for_update().filter(pk=attempt.pk).first()

            existing = (Recording.objects.filter(attempt=attempt, kind=kind)
                        .order_by("-created").first())
            if existing and existing.file:
                with open(existing.file.path, "wb") as fh:
                    for piece in file.chunks():
                        fh.write(piece)
                return Response(status=status.HTTP_201_CREATED)

            full_name = attempt.employee.full_name if attempt.employee else "xodim"
            slug = re.sub(r"[^\w\-]+", "_", full_name, flags=re.UNICODE).strip("_") or "xodim"
            stamp = timezone.localtime(timezone.now()).strftime("%Y%m%d_%H%M%S")
            ext = (file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "webm")
            if ext not in ("webm", "mp4"):
                ext = "webm"
            file.name = f"{slug}_{stamp}.{ext}"

            # Yozuv test BOSHIDA ochiladi, ya'ni natija hali yo'q — u `submit`
            # paytida bog'lanadi (`attempt.recordings.update(result=...)`).
            # Xodim va test nomi nusxa qilib saqlanadi: keyinchalik test yoki
            # xodim o'chirilsa ham arxivda "kimning, qaysi test videosi" ko'rinadi.
            Recording.objects.create(
                attempt=attempt,
                result=Result.objects.filter(attempt=attempt).order_by("-created").first(),
                kind=kind, file=file,
                employee_name=full_name,
                test_name=attempt.test.name if attempt.test else "",
                # Tabel va sex ham shu yerda nusxa qilinadi: arxiv filtri
                # aynan shu ustunlar bo'yicha ishlaydi va bog'lanish keyin
                # uzilsa ham ishlashda davom etishi kerak (qarang: Recording).
                tabel_number=(attempt.employee.tabel_number if attempt.employee else ""),
                tsex=(attempt.test.tsex if attempt.test else ""),
            )
        # "Tizim holati" dagi disk hajmi keshi bu yerda ATAYLAB tozalanmaydi —
        # sababi `_recordings_total_bytes` izohida.
        return Response(status=status.HTTP_201_CREATED)

    @staticmethod
    def _append(attempt, kind, file):
        """Keyingi bo'lakni mavjud faylning oxiriga qo'shadi."""
        with transaction.atomic():
            # Qator qulflanadi — bir vaqtda ikkita bo'lak yozilib, fayl
            # aralashib ketmasligi uchun. `select_related` ATAYLAB yo'q:
            # `attempt`/`result` null bo'lishi mumkin, outer join'ning nullable
            # tomonini PostgreSQL qulflay olmaydi.
            rec = (Recording.objects.select_for_update()
                   .filter(attempt=attempt, kind=kind).order_by("-created").first())
            if not rec or not rec.file:
                # Birinchi bo'lak yetib bormagan — davomini ilib qo'yadigan
                # joy yo'q. Mijoz buni "muvaffaqiyatsiz" deb qabul qiladi va
                # keyingilarini yubormaydi.
                return Response({"error": "Yozuvning boshi topilmadi."},
                                status=status.HTTP_409_CONFLICT)
            with open(rec.file.path, "ab") as fh:
                for piece in file.chunks():
                    fh.write(piece)
        return Response(status=status.HTTP_201_CREATED)


class RecordingDurationView(APIView):
    """Xodim brauzeri O'ZI o'lchagan yozuv davomiyligini qabul qiladi.

    Video bo'lak-bo'lak yozilgani uchun (yuqoridagi `RecordingUploadView`)
    faylning o'zida umumiy davomiylik hech qachon bo'lmaydi — pleyer buni
    "jonli oqim" deb hisoblab, katta faylda ochilishni sekinlashtiradi
    (qarang: `_ensure_recording_duration_fixed`). Buni tuzatish uchun aniq
    son kerak, va uni ENG ISHONCHLI joy — yozib olgan brauzerning o'zi
    biladi (qarang: App.jsx, `handleFinish`).

    Bu yerda faylga TEGILMAYDI — faqat son bazaga saqlanadi. Faylning o'zi
    keyinroq, birinchi ko'rilganda (va, muhimi, oxirgi bo'lak allaqachon
    yuklanib bo'lgach) tuzatiladi — chaqiruv vaqti bilan yuklash vaqti mos
    kelmasligi mumkin (qarang: App.jsx dagi izoh, `uploaderRef.finish()`)."""

    def post(self, request):
        token = request.data.get("token")
        kind = request.data.get("kind")
        duration_ms = _int_param(request.data.get("duration_ms"))
        if kind not in ("screen", "face") or duration_ms <= 0:
            return Response({"error": "Noto'g'ri so'rov."}, status=status.HTTP_400_BAD_REQUEST)

        attempt = _attempt_by_token(token)
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        rec = (Recording.objects.filter(attempt=attempt, kind=kind)
               .order_by("-created").first())
        if rec:
            rec.duration_ms = duration_ms
            rec.save(update_fields=["duration_ms"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeIdentifyView(APIView):
    """Kamera orqali kirish: suratdan yuzni aniqlaydi, mahalliy sinxronlangan
    xodimlar (SyncedEmployee) orasidan eng mos kelganini topadi va
    administrator test tayinlashini kutadigan CheckIn yozuvini yaratadi."""
    parser_classes = [MultiPartParser]

    def post(self, request):
        photo = request.FILES.get("photo")
        if not photo:
            return Response({"error": "Rasm yuborilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # Admin "bugun kelishi kutilayotgan xodimlar" ro'yxatini oldindan
        # belgilashi shart — qidiruv FAQAT shu ro'yxat ichida bo'ladi (server
        # yukini kamaytiradi, 3000+ xodimning barchasini solishtirish shart
        # emas). Ro'yxat bo'sh bo'lsa, yuzni tekshirishga ham urinmasdan
        # darhol xatolik qaytariladi.
        expected_ids = list(ExpectedEmployee.objects.values_list("synced_employee_id", flat=True))
        if not expected_ids:
            return Response(
                {"error": "Bugun kutilayotgan xodimlar ro'yxati bo'sh. Administratorga murojaat qiling."},
                status=status.HTTP_404_NOT_FOUND,
            )

        embedding = face.extract_embedding(photo.read())
        if embedding is None:
            return Response(
                {"error": "Yuzingiz aniqlanmadi. Kameraga yaqinroq va yorug' joyda turing."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pool = SyncedEmployee.objects.exclude(face_embedding__isnull=True).filter(id__in=expected_ids)
        candidates = list(pool.values_list("id", "face_embedding"))
        best_id, best_score = face.find_best_match(embedding, candidates)
        if best_id is None or not face.is_match(best_score):
            return Response(
                {"error": "Xodim topilmadi. Administratorga murojaat qiling."},
                status=status.HTTP_404_NOT_FOUND,
            )

        synced = SyncedEmployee.objects.get(pk=best_id)
        employee, _ = Employee.objects.get_or_create(
            external_slug=synced.slug,
            defaults={
                "full_name": synced.full_name, "department": synced.department_name,
                "tabel_number": synced.tabel_number,
            },
        )
        if (employee.full_name != synced.full_name or employee.department != synced.department_name
                or employee.tabel_number != synced.tabel_number):
            employee.full_name = synced.full_name
            employee.department = synced.department_name
            employee.tabel_number = synced.tabel_number
            employee.save(update_fields=["full_name", "department", "tabel_number"])

        checkin = CheckIn.objects.create(
            synced_employee=synced, employee=employee,
            full_name=synced.full_name, department_name=synced.department_name,
            match_score=best_score,
        )
        log_activity("employee", synced.full_name, "checkin",
                     f"{synced.full_name} yuz orqali tizimga keldi (moslik: {round(best_score, 3)})")
        return Response({
            "checkin_token": str(checkin.token),
            "full_name": checkin.full_name,
            "department": checkin.department_name,
        }, status=status.HTTP_201_CREATED)


CHECKIN_TIMEOUT_SECONDS = 10 * 60  # admin shuncha vaqt ichida test tayinlamasa, kutish bekor qilinadi


def _expire_checkin_if_stale(checkin):
    """Agar xodim kutayotgan bo'lsa-yu, admin CHECKIN_TIMEOUT_SECONDS ichida test
    tayinlamagan bo'lsa — kutishni bekor qiladi (xodim qaytadan yuzini ko'rsatishi kerak)."""
    if checkin.status == "waiting" and not checkin.attempt:
        elapsed = (timezone.now() - checkin.created).total_seconds()
        if elapsed > CHECKIN_TIMEOUT_SECONDS:
            checkin.status = "cancelled"
            checkin.save(update_fields=["status"])


class EmployeeCheckinStatusView(APIView):
    """Xodim brauzeri administrator test tayinlab, boshlab berishini shu
    endpoint orqali (bir necha soniyada bir marta) so'rab turadi."""

    def get(self, request):
        token = request.query_params.get("token")
        # `CheckIn.token` ham UUID — noto'g'ri qiymat 500 bermasligi uchun
        # oldindan tekshiriladi (qarang: `_attempt_by_token`).
        checkin = None
        if token:
            try:
                uuid.UUID(str(token))
                checkin = (CheckIn.objects.filter(token=token)
                           .select_related("attempt", "test").first())
            except (ValueError, AttributeError, TypeError):
                checkin = None
        if not checkin:
            return Response({"error": "Kutish seansi topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        _expire_checkin_if_stale(checkin)

        if checkin.status == "cancelled":
            return Response({"status": "cancelled"})
        if checkin.status == "waiting" or not checkin.attempt:
            return Response({"status": "waiting", "full_name": checkin.full_name})

        # Seans ma'lumoti `_session_payload` orqali tayyorlanadi — testni boshlash
        # ham, sahifa yangilangandan keyin tiklash ham AYNAN bir xil javob berishi
        # shart. Ilgari bu yerda payload qo'lda yig'ilar va `attempt` uzatilmasdi,
        # shu sabab variantlar tartibi seansda saqlanmay, har so'rovda (bu endpoint
        # har uch soniyada so'raladi) qayta aralashib ketardi.
        return Response({"status": "started", **_session_payload(request, checkin.attempt)})


def _fetch_face_embedding(synced, known_url=None):
    """Xodimning JORIY rasmini BnpzId'dan olib, yuz embeddingini hisoblaydi.

    Faqat ro'yxatga qo'shilayotgan (yoki qidiruvda tanlangan) BITTA xodim uchun
    chaqiriladi — ommaviy sinxronizatsiya emas. Shu tufayli 3000+ xodimning
    rasmini oldindan yuklab/hisoblab o'tirishga hojat yo'q: yuz belgisi aynan
    kerak bo'lgan xodim uchun, aynan qo'shilayotgan paytda olinadi.

    (embedding, image_url) qaytaradi. Rasm topilmasa yoki yuz aniqlanmasa
    embedding None bo'ladi. Mahalliy `base_image_url` eskirgan bo'lishi mumkin,
    shuning uchun avval xodimning joriy ma'lumoti (slug bo'yicha) so'raladi."""
    # Manzil chaqiruvchi tomonidan allaqachon aniqlangan bo'lsa, detail
    # so'rovini takrorlamaymiz (qarang: `_current_image_url`).
    image_url = known_url if known_url is not None else _current_image_url(synced)

    if not image_url:
        return None, ""
    content = bnpzid.fetch_image(image_url)
    if content is None:
        return None, image_url
    return face.extract_embedding(content), image_url


def _embedding_from_local_photo(synced):
    """Shu loyihada qo'lda olingan rasmdan yuz belgisini hisoblaydi.

    BnpzId'ga umuman murojaat qilinmaydi — rasm mahalliy diskda yotibdi."""
    if not synced.local_photo:
        return None
    try:
        with synced.local_photo.open("rb") as fh:
            return face.extract_embedding(fh.read())
    except (OSError, ValueError):
        # Fayl diskdan yo'qolgan bo'lishi mumkin — bu ro'yxatga qo'shishni
        # yiqitmasligi kerak, chaqiruvchi None ni tushunarli xabarga aylantiradi.
        return None


def _current_image_url(synced):
    """Xodimning BnpzId'dagi JORIY rasm manzili.

    Mahalliy `base_image_url` eskirgan bo'lishi mumkin (HR rasmni almashtirsa
    manzil ham o'zgaradi), shuning uchun manba tizimdan so'raladi. BnpzId
    javob bermasa — mahalliy qiymatga tayanamiz, ya'ni bu funksiya hech qachon
    ish jarayonini to'xtatmaydi."""
    image_url = synced.base_image_url or ""
    if synced.slug:
        # Joriy ma'lumot olinmasa, mahalliy (eski) manzilga tayanamiz.
        item, ok = bnpzid.get_employee(synced.slug)
        if ok:
            image_url = bnpzid.image_url_of(item) or image_url
    return image_url


# BnpzId'ning maksimal sahifa hajmi (o'lchandi: bundan kattasi ham 200 qaytaradi).
# Ilgari bu yerda 30 turardi va `next` havolasi umuman o'qilmasdi: keng tarqalgan
# familiya bo'yicha qidirganda admin faqat birinchi 30 tasini ko'rar, yana borligi
# esa hech qayerda ko'rinmasdi — ya'ni kerakli xodim ro'yxatga tushmasa, u
# "bunday xodim yo'q" degan xulosaga kelardi.
BNPZ_SEARCH_PAGE_SIZE = 200


def _bnpz_fetch(params):
    """BnpzId'ga bitta qidiruv so'rovi. (items, total, ok) qaytaradi."""
    return bnpzid.search_employees({**params, "page_size": BNPZ_SEARCH_PAGE_SIZE})


def _bnpz_search(q):
    """BnpzId'dan ism/tabel bo'yicha TIRIK qidiradi va har bir topilgan xodimning
    metama'lumotini (ism, tabel, bo'lim, rasm manzili) mahalliy SyncedEmployee'ga
    yozib qo'yadi. Rasm YUKLANMAYDI, embedding hisoblanmaydi — bu qo'shish paytida,
    faqat tanlangan xodim uchun bo'ladi (ommaviy sinxron yo'q).

    Xodimlar ro'yxatining YAGONA manbai — BnpzId. Mahalliy `SyncedEmployee`
    jadvali bu yerda manba emas, faqat nusxa: unda ishdan bo'shagan yoki ismi
    o'zgargan xodim qolib ketishi mumkin, shuning uchun qidiruvga aralashtirilmaydi.

    BITTA so'rov yetarli: BnpzId'ning `search` filtri tabel raqamini ham
    qamraydi (o'lchandi: `search=9487` → aynan 1 ta natija). Ilgari bu yerda
    "BnpzId `tabel_number` ni bilmasligi mumkin" degan taxmin ustiga qurilgan
    ikkinchi so'rov va undan keyingi qo'shimcha filtrlash bor edi — u hech qachon
    foyda bermasdi.

    (results, total, ok) qaytaradi. `total` — BnpzId topgan umumiy son;
    ok=False bo'lsa BnpzId javob bermadi."""
    items, total, ok = _bnpz_fetch({"search": q})
    if not ok:
        return [], 0, False

    out = []
    for e in items:
        slug = e.get("slug")
        if not slug:
            continue
        image_url = bnpzid.image_url_of(e)
        synced, _ = SyncedEmployee.objects.update_or_create(
            slug=slug,
            defaults={
                # Faqat metama'lumot yangilanadi — `face_embedding` va `local_photo`
                # bu yerda o'zgarmaydi (defaults ro'yxatida yo'q).
                "tabel_number": e.get("tabel_number") or "",
                "full_name": e.get("full_name") or "",
                "department_name": (e.get("department") or {}).get("name") or "",
                "section_name": (e.get("section") or {}).get("name") or "",
                "position": e.get("position") or "",
                "base_image_url": image_url,
            },
        )
        out.append((synced, bool(image_url)))
    return out, total, True


def _local_search(q):
    """BnpzId javob bermaganda ishlatiladigan ZAXIRA qidiruv — mahalliy nusxadan.

    Bu ro'yxat eskirgan bo'lishi mumkin (ishdan bo'shagan yoki ismi o'zgargan
    xodim), shuning uchun u faqat BnpzId javob bermagan holatda va ochiq
    ogohlantirish bilan ko'rsatiladi.

    `has_photo` bu yerda BnpzId'dagi rasmga qaramaydi, faqat MAHALLIY narsaga:
    BnpzId o'chiq bo'lsa, uning rasmi baribir yuklab bo'lmaydi. Ya'ni belgisi
    yoki qo'lda yuklangan rasmi bori "Ro'yxatga qo'shish" (u tarmoqsiz ham
    ishlaydi), qolgani esa "Rasm olib qo'shish" — kamera yo'li ham to'liq
    mahalliy.

    (results, total) qaytaradi — `total` kesilishdan OLDINGI son."""
    qs = (SyncedEmployee.objects
          .filter(Q(full_name__icontains=q) | Q(tabel_number__icontains=q))
          .order_by("full_name"))
    total = qs.count()
    rows = [(se, bool(se.face_embedding) or bool(se.local_photo))
            for se in qs[:BNPZ_SEARCH_PAGE_SIZE]]
    return rows, total


def _synced_row(synced, expected_ids, has_photo):
    return {
        "id": synced.id,
        "full_name": synced.full_name,
        "tabel_number": synced.tabel_number,
        "department_name": synced.department_name,
        "is_expected": synced.id in expected_ids,
        "has_photo": has_photo,
    }


class AdminSyncedEmployeeSearchView(APIView):
    """Admin "bugun kelishi kutilayotgan xodimlar" ro'yxatini tuzayotganda,
    xodimni ism yoki tabel raqami bo'yicha qidirib topishi uchun.

    Qidiruv BnpzId'dan boradi — mahalliy `SyncedEmployee` jadvali manba
    sifatida ishlatilmaydi (u faqat BnpzId javob bermaganda, zaxira sifatida
    ko'rsatiladi — pastga qarang). Sabab: mahalliy nusxa eskirgan bo'lishi mumkin
    (ishdan bo'shagan, ismi yoki bo'limi o'zgargan xodim), qidiruv esa har
    doim joriy holatni ko'rsatishi kerak. Shu tufayli rasm bor-yo'qligi ham
    aniq bo'ladi: rasmi bori "Ro'yxatga qo'shish", rasmsizi esa "Rasm olib
    qo'shish" (kamera) ko'rsatadi.

    BnpzId javob bermasa — `bnpz_ok: false` qaytadi va ro'yxat MAHALLIY
    nusxadan to'ldiriladi (`stale: true`). Bu uch holat admin uchun uchta
    boshqa-boshqa xabar: "bunday xodim yo'q", "hozir BnpzId javob bermayapti,
    quyidagilar eskirgan ma'lumot" va "topildi". Ularni aralashtirib yuborish
    admini mavjud xodimni qo'lda qayta yaratishga olib boradi.

    `total` va `truncated` — BnpzId topgan umumiy son va javob sahifa
    chegarasida kesilganini bildiradi. Kesilgani jimgina qolsa, ro'yxatga
    tushmagan xodim "yo'q" bo'lib ko'rinadi.

    Yuz belgisi qo'shish paytida, faqat tanlangan xodim uchun hisoblanadi —
    ommaviy sinxron yo'q."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "expected"

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()
        if len(q) < 2:
            return Response({"results": [], "bnpz_ok": True, "stale": False,
                             "total": 0, "truncated": False})

        expected_ids = set(ExpectedEmployee.objects.values_list("synced_employee_id", flat=True))
        found, total, bnpz_ok = _bnpz_search(q)
        stale = not bnpz_ok
        if stale:
            found, total = _local_search(q)

        results = [
            _synced_row(synced, expected_ids, has_img or bool(synced.face_embedding))
            for synced, has_img in found
        ]
        # Tabel raqami AYNAN so'ralganidek bo'lgan xodim eng tepada tursin —
        # tabel bo'yicha qidirganda odatda aynan o'sha bitta odam kerak bo'ladi.
        # `sort` barqaror, shuning uchun qolganlarning tartibi o'zgarmaydi.
        results.sort(key=lambda r: (r["tabel_number"] or "").strip() != q)
        return Response({
            "results": results,
            "bnpz_ok": bnpz_ok,
            "stale": stale,
            "total": total,
            "truncated": total > len(results),
        })


class AdminSyncedEmployeePhotoUploadView(APIView):
    """Rasmi (employee_service'da) bo'lmagan yoki eskirgan xodim uchun admin
    panelda qo'lda rasm yuklash — shu rasmdan yuz embedding'i hisoblanadi,
    shundan so'ng xodim "kutilayotganlar" ro'yxatiga ham avtomatik qo'shiladi.

    RASM FAQAT SHU LOYIHADA QOLADI — BnpzId'ga YUBORILMAYDI.

    Bu ataylab shunday va o'zgartirilmasligi kerak. BnpzId'da rasm yangilash
    endpointi bor (`PATCH /employees/<slug>/base-image/`) va u — boshqa barcha
    endpointlardan farqli o'laroq — bizning "faqat o'qish" servis kalitimizni
    ham qabul qiladi (tekshirilgan: kalitsiz 403, kalit bilan 400 "fayl kerak",
    ya'ni kalit o'tadi). Ya'ni bu yerdan BnpzId'dagi rasmni yozib yuborish
    texnik jihatdan MUMKIN.

    Shunga qaramay qilinmaydi: BnpzTest — BnpzId ma'lumotining ISTE'MOLCHISI,
    manbasi emas. Test punktida shosha-pisha olingan surat HR'ning rasmiy
    rasmidan yomonroq bo'lishi mumkin, va u bir marta yozilsa BnpzId'dan
    o'qiydigan BARCHA tizimlarga tarqaladi.

    Shuning uchun bu loyihada BnpzId'ga hech qanday yozish amali yo'q —
    butun kod bazasida faqat `requests.get` ishlatiladi — barchasi bitta
    joyda, `core/bnpzid.py` modulida."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "expected"
    parser_classes = [MultiPartParser]

    def post(self, request, pk):
        synced = SyncedEmployee.objects.filter(pk=pk).first()
        if not synced:
            return Response({"error": "Xodim topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        photo = request.FILES.get("photo")
        if not photo:
            return Response({"error": "Rasm yuborilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        embedding = face.extract_embedding(photo.read())
        if embedding is None:
            return Response(
                {"error": "Rasmda yuz aniqlanmadi. Boshqa, yorug' va aniq rasm tanlang."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        photo.seek(0)
        synced.local_photo = photo
        synced.face_embedding = embedding
        synced.save(update_fields=["local_photo", "face_embedding"])
        ExpectedEmployee.objects.get_or_create(synced_employee=synced)
        log_activity("admin", request.user.username, "employee_photo_uploaded",
                     f"Xodim uchun rasm yuklandi: {synced.full_name}")

        return Response({"ok": True, "has_photo": True})


class AdminExpectedEmployeeListView(APIView):
    """"Bugun kelishi kutilayotgan xodimlar" ro'yxati — yuz orqali kirish
    shu ro'yxat ichida qidiradi (ro'yxat bo'sh bo'lmasa), serverga tushadigan
    yukni kamaytiradi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "expected"

    def get(self, request):
        entries = ExpectedEmployee.objects.select_related("synced_employee")
        data = [{
            "id": ee.id,
            "synced_employee_id": ee.synced_employee_id,
            "full_name": ee.synced_employee.full_name,
            "tabel_number": ee.synced_employee.tabel_number,
            "department_name": ee.synced_employee.department_name,
        } for ee in entries]
        return Response(data)

    def post(self, request):
        synced_employee_id = request.data.get("synced_employee_id")
        synced = SyncedEmployee.objects.filter(pk=synced_employee_id).first()
        if not synced:
            return Response({"error": "Xodim topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # --- 1) Shu loyihada qo'lda olingan rasm bor bo'lsa — FAQAT O'SHA ----
        #
        # Admin kamera orqali rasm olgan bo'lsa, u BnpzId'dagi rasmdan USTUN
        # turadi va xodim keyin necha marta ro'yxatga qo'shilsa ham o'sha rasm
        # ishlatiladi. Bu holatda BnpzId'ga UMUMAN murojaat qilinmaydi.
        #
        # Sabab: admin rasmni ataylab, aynan shu xodim tanilmagani uchun olgan.
        # BnpzId'dagi rasm esa aynan ishlamagani ma'lum — unga qaytish
        # muammoni qaytarish bo'lardi.
        if synced.local_photo:
            if not synced.face_embedding:
                # Rasm bor-u belgi yo'q (masalan eski sinxron uni o'chirgan).
                # BnpzId'dan emas, AYNAN SHU rasmdan qayta hisoblaymiz.
                embedding = _embedding_from_local_photo(synced)
                if embedding is None:
                    return Response(
                        {"code": "no_face",
                         "error": "Qo'lda yuklangan rasmda yuz aniqlanmadi. "
                                  "Kamera orqali qaytadan rasm oling."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                synced.face_embedding = embedding
                synced.save(update_fields=["face_embedding"])

            ExpectedEmployee.objects.get_or_create(synced_employee=synced)
            log_activity("admin", request.user.username, "expected_added",
                         f"Kutilayotganlar ro'yxatiga qo'shildi: {synced.full_name} "
                         f"(qo'lda yuklangan rasm bilan)")
            return Response({"ok": True}, status=status.HTTP_201_CREATED)

        # --- 2) Aks holda — BnpzId'dagi rasm -------------------------------
        #
        # Belgi ikki holatda hisoblanadi:
        #   a) umuman yo'q bo'lsa;
        #   b) BnpzId'dagi RASM ALMASHTIRILGAN bo'lsa (`base_image_url`
        #      o'zgargan) — xodim soqol qo'ygan, ko'zoynak taqqan yoki HR
        #      sifatliroq rasm yuklagan bo'lishi mumkin.
        #
        # (b) ilgari yo'q edi: belgi bir marta hisoblanib, keyin hech qachon
        # yangilanmasdi. Uni faqat tungi sinxron tuzatardi, u esa endi olib
        # tashlandi (qarang: core/apps.py) — ya'ni bu tekshiruvsiz belgi
        # abadiy eskirib qolardi.
        current_url = _current_image_url(synced)
        photo_changed = bool(current_url) and current_url != (synced.base_image_url or "")

        if not synced.face_embedding or photo_changed:
            embedding, image_url = _fetch_face_embedding(synced, known_url=current_url)
            if embedding is None:
                # Rasm almashgan-u, yangisidan yuz chiqmasa — ESKI belgi
                # joyida qoladi, ya'ni xodim baribir kira oladi. Faqat umuman
                # belgisi bo'lmagan xodimda bu haqiqiy to'siq.
                if not synced.face_embedding:
                    return Response(
                        {"code": "no_face",
                         "error": "BnpzId'da bu xodimning rasmi topilmadi yoki rasmda yuz "
                                  "aniqlanmadi. Kamera orqali rasm olib qo'shing."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            else:
                synced.face_embedding = embedding
                fields = ["face_embedding"]
                if image_url and image_url != synced.base_image_url:
                    synced.base_image_url = image_url
                    fields.append("base_image_url")
                synced.save(update_fields=fields)

        ExpectedEmployee.objects.get_or_create(synced_employee=synced)
        log_activity("admin", request.user.username, "expected_added",
                     f"Kutilayotganlar ro'yxatiga qo'shildi: {synced.full_name}")
        return Response({"ok": True}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        count = ExpectedEmployee.objects.count()
        ExpectedEmployee.objects.all().delete()
        log_activity("admin", request.user.username, "expected_cleared",
                     f"Kutilayotganlar ro'yxati tozalandi ({count} ta)")
        return Response({"ok": True})


class AdminExpectedEmployeeDeleteView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "expected"

    def delete(self, request, pk):
        ee = ExpectedEmployee.objects.filter(pk=pk).select_related("synced_employee").first()
        name = ee.synced_employee.full_name if ee else ""
        ExpectedEmployee.objects.filter(pk=pk).delete()
        log_activity("admin", request.user.username, "expected_removed",
                     f"Kutilayotganlar ro'yxatidan olib tashlandi: {name}")
        return Response({"ok": True})


class AdminCheckinListView(APIView):
    """Admin uchun: hozir kamera oldida turib, test tayinlanishini kutayotgan
    xodimlar ro'yxati (TZ: \"xodim testga keldi\")."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "checkins"

    def get(self, request):
        checkins = CheckIn.objects.filter(status="waiting").select_related("employee").order_by("-created")
        for c in checkins:
            _expire_checkin_if_stale(c)
        checkins = [c for c in checkins if c.status == "waiting"]
        data = [{
            "id": c.id,
            "full_name": c.full_name,
            "department": c.department_name,
            "match_score": round(c.match_score, 3),
            "via": "face" if c.synced_employee_id else "password",
            "arrived_at": timezone.localtime(c.created).strftime("%H:%M:%S"),
        } for c in checkins]
        return Response(data)


class AdminCheckinStartView(APIView):
    """Admin xodimga test tayinlab, boshlab beradi — shundan so'ng xodim
    brauzeri (checkin-status orqali) avtomatik testga o'tadi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "checkins"

    def post(self, request, pk):
        checkin = CheckIn.objects.filter(pk=pk, status="waiting").select_related("employee").first()
        if not checkin:
            return Response({"error": "Kutish yozuvi topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        test_id = request.data.get("test_id")
        test = Test.objects.filter(pk=test_id).first()
        if not test:
            return Response({"error": "Test topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

        # "Testni boshlash" oynasida o'zgartirilgan test sozlamalari shu so'rov
        # bilan birga keladi va SHU YERDA qo'llanadi. Ilgari panel ularni alohida
        # `PATCH /admin/tests/` bilan saqlardi — u esa "tests" ruxsatini talab
        # qiladi. Faqat "Kutish ro'yxati" ruxsati berilgan administrator shu
        # sabab testni umuman boshlay olmasdi (403 olib, paneldan chiqarib
        # yuborilardi). Sozlamalarni tayinlash paytida belgilash — aynan shu
        # bo'limning ishi, shuning uchun u "checkins" ruxsati bilan bajariladi.
        params = request.data.get("params")
        if isinstance(params, dict) and params:
            ser = TestAdminSerializer(test, data=params, partial=True)
            if not ser.is_valid():
                return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
            ser.save()
            test.refresh_from_db()

        employee = checkin.employee
        if employee is None:
            return Response({"error": "Bu kutish yozuvining xodimi o'chirilgan."},
                            status=status.HTTP_400_BAD_REQUEST)
        employee.assigned_test = test
        employee.status = "assigned"
        employee.save(update_fields=["assigned_test", "status"])

        err_code, result = _create_attempt_session(request, employee, test)
        if err_code:
            return Response({"error": result}, status=status.HTTP_400_BAD_REQUEST)
        attempt, _data = result

        checkin.test = test
        checkin.attempt = attempt
        checkin.status = "started"
        checkin.save(update_fields=["test", "attempt", "status"])
        log_activity("admin", request.user.username, "test_assigned",
                     f"{employee.full_name}ga \"{test.name}\" testi tayinlandi", {"test_id": test.id})
        return Response({"ok": True})


class AdminEmployeeSyncView(APIView):
    """BnpzId'dagi xodimlar METAMA'LUMOTINI mahalliy nusxaga ko'chiradi.

    Rasm yuklanmaydi va yuz belgisi hisoblanmaydi — belgi xodim
    "Kutilayotganlar" ro'yxatiga qo'shilganda, faqat o'sha bitta xodim uchun
    olinadi (qarang: `sync_employees` komandasi izohi). Bu yerda ommaviy
    sinxron YO'Q, davriy sinxron ham yo'q: bu qo'lda bosiladigan, ixtiyoriy
    yangilash.

    Bir necha ming yozuv bo'lgani uchun fonda (background thread) ishga
    tushiriladi, javob darhol qaytadi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "settings"

    def post(self, request):
        import threading
        from django.core.management import call_command

        if getattr(AdminEmployeeSyncView, "_running", False):
            return Response({"error": "Sinxronizatsiya allaqachon ishlamoqda."}, status=status.HTTP_409_CONFLICT)

        def run():
            AdminEmployeeSyncView._running = True
            try:
                call_command("sync_employees")
            finally:
                AdminEmployeeSyncView._running = False
                # Bu oqim so'rov emas — Django uning ulanishini o'zi yopmaydi,
                # ulanishlar esa endi qayta ishlatiladi (DB_CONN_MAX_AGE).
                connection.close()

        threading.Thread(target=run, daemon=True).start()
        return Response({"ok": True, "message": "Sinxronizatsiya fonda boshlandi."})


class AdminEmployeeSyncStatusView(APIView):
    """Qo'lda ishga tushirilgan sinxronizatsiya holati.

    Sonlar MAHALLIY nusxaga tegishli — "BnpzId'da nechta xodim bor" degani
    emas. Nomlar shuning uchun aniq: davriy sinxron bor paytda ikkisi bir xil
    bo'lardi va farqi sezilmasdi, endi esa mahalliy nusxa BnpzId'dan orqada
    qolishi mumkin."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "settings"

    def get(self, request):
        running = getattr(AdminEmployeeSyncView, "_running", False)
        return Response({
            "running": running,
            "local_total": SyncedEmployee.objects.count(),
            "local_with_face": SyncedEmployee.objects.exclude(face_embedding__isnull=True).count(),
        })


# Sexlar katalogi qisqa muddatga keshlanadi. Kesh TEJASH uchun emas — o'lchandi:
# `/departments/` 4.7 KB va 44–111 ms, va u butun loyihada bitta joyda, admin
# "Testlar" tabini ochganda so'raladi (~30 marta kunda). Kesh BnpzId sekinlashsa
# yoki o'chsa, admin paneli timeout kutib turmasligi uchun.
DEPARTMENTS_TTL = 300
# "Oxirgi muvaffaqiyatli ro'yxat" alohida, uzoq muddat bilan saqlanadi: BnpzId
# vaqtincha o'chganda ro'yxat bo'sh chiqib qolmasin.
DEPARTMENTS_LAST_GOOD_TTL = 30 * 24 * 3600
DEPARTMENTS_KEY = "bnpzid:departments"
DEPARTMENTS_LAST_GOOD_KEY = "bnpzid:departments:last-good"


def _department_names():
    """Sex nomlari — MANBADAN (`GET /departments/`), uch pog'onali zaxira bilan.

    Ilgari bu ro'yxat `SyncedEmployee` jadvalidan yig'ilardi, ya'ni sinxronizatsiya
    nimani ko'chirgan bo'lsa — shu. Undan ikkita kamchilik kelib chiqardi: hali
    hech kim ishlamayotgan sex ro'yxatga umuman tushmasdi, va tartib alifbo
    bo'yicha bo'lib qolardi. Katalog esa nomlarni manbadagi imlo va tartibda
    beradi (`sort_order`).

    Ro'yxat ILOVA ISHGA TUSHGANDA emas, BIRINCHI SO'RALGANDA yuklanadi:
    `AppConfig.ready()` ichidagi tarmoq so'rovi `migrate` va boshqa
    komandalarda ham ishlab, konteyner ko'tarilishini BnpzId'ga bog'lab
    qo'yardi — va ro'yxat qayta ishga tushirilmaguncha muzlab qolardi.

    Zaxira tartibi: yangi kesh → oxirgi muvaffaqiyatli ro'yxat → mahalliy
    nusxadagi sex nomlari. Oxirgisi jarayon qayta ko'tarilgan va BnpzId ham
    javob bermayotgan holat uchun: kesh xotirada, ya'ni qayta ishga tushirilsa
    yo'qoladi, `SyncedEmployee` esa joyida qoladi."""
    names = cache.get(DEPARTMENTS_KEY)
    if names is not None:
        return names

    items, ok = bnpzid.list_departments()
    if ok and items:
        names = bnpzid.department_names(items)
        cache.set(DEPARTMENTS_KEY, names, DEPARTMENTS_TTL)
        cache.set(DEPARTMENTS_LAST_GOOD_KEY, names, DEPARTMENTS_LAST_GOOD_TTL)
        return names

    last_good = cache.get(DEPARTMENTS_LAST_GOOD_KEY)
    if last_good:
        return last_good

    return list(
        SyncedEmployee.objects.exclude(department_name="")
        .values_list("department_name", flat=True).distinct().order_by("department_name")
    )


class AdminTsexListView(APIView):
    """Sex/tsex nomlari — testlarni sexlarga guruhlashda tanlov ro'yxati.

    Nomlar BnpzId katalogidan olinadi; batafsil: `_department_names`."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(_department_names())


class AdminLoginView(APIView):
    """YAGONA kirish eshigi: barcha administratorlar — test administratori,
    o'quv qismi administratori, superuser — shu bitta sahifadan o'z login va
    paroli bilan kiradi. Kim nimani ko'rishini rol hal qiladi, alohida manzil
    yoki alohida panel emas.

    Hisoblar Django'ning o'z foydalanuvchi tizimida (auth.User): faqat "Xodim
    (Staff status)" belgisi qo'yilganlar kira oladi. Ularni superuser panelning
    "Foydalanuvchilar" bo'limida (yoki /it-center orqali) boshqaradi."""

    def post(self, request):
        from django.contrib.auth import authenticate

        login = (request.data.get("login") or "").strip()
        password = request.data.get("password") or ""
        if not login or not password:
            return Response({"error": "Login yoki parol noto'g'ri."}, status=status.HTTP_401_UNAUTHORIZED)

        user = authenticate(request, username=login, password=password)
        if not user or not user.is_active or not user.is_staff:
            return Response({"error": "Login yoki parol noto'g'ri."}, status=status.HTTP_401_UNAUTHORIZED)

        permissions = sorted(permissions_for(user))
        # Roli olib qo'yilgan (yoki hali berilmagan) administrator kira olsa
        # ham hech qanday bo'lim ko'rmaydi — bo'sh panelda "nega hech narsa
        # yo'q?" degan savol tug'ilmasligi uchun buni ochiq aytamiz.
        if not permissions:
            log_activity("admin", user.username, "login_denied",
                         f"Rol berilmagan administrator kirishga urindi: {user.username}")
            return Response(
                {"error": "Hisobingizga hali rol berilmagan. Superuserga murojaat qiling."},
                status=status.HTTP_403_FORBIDDEN,
            )

        log_activity("admin", user.username, "login", f"Administrator panelga kirdi: {user.username}")
        return Response({
            "token": make_admin_token(user.username),
            "username": user.username,
            "is_superuser": user.is_superuser,
            "role": role_name_for(user),
            # Panel menyusi shu ro'yxat bo'yicha yig'iladi. Haqiqiy himoya esa
            # serverda (`IsAdmin` + `required_permission`) — bu faqat ko'rinish
            # uchun, brauzerda o'zgartirish hech qanday huquq bermaydi.
            "permissions": permissions,
        })


class AdminMeView(APIView):
    """Joriy administrator kim va nimaga ruxsati bor.

    Panel har ochilganda shu yerdan so'raydi — shunda superuser rolni
    o'zgartirsa, administrator qayta kirmasdan (sahifani yangilashi bilan)
    yangi menyuni ko'radi va eski tokenidagi eskirgan ro'yxatga tayanmaydi."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({
            "username": request.user.username,
            "is_superuser": request.user.is_superuser,
            "role": request.user.role_name,
            "permissions": sorted(request.user.permissions),
        })


class AdminPermissionCatalogView(APIView):
    """Rol tahrirlash oynasi uchun: umuman qanday ruxsatlar mavjud.

    Ro'yxat serverdan olinadi (`core/perms.py`), panelga ko'chirilmagan —
    aks holda yangi bo'lim qo'shilganda ikkita joyni yangilash kerak bo'lardi
    va ular jimgina bir-biridan farq qila boshlardi."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]

    def get(self, request):
        return Response(PERMISSIONS)


class AdminRoleViewSet(viewsets.ModelViewSet):
    """Rollar va ularning ruxsatlari — faqat superuser uchun."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]
    queryset = AdminRole.objects.all()
    serializer_class = AdminRoleSerializer

    def perform_create(self, serializer):
        role = serializer.save()
        log_activity("admin", self.request.user.username, "role_created",
                     f"Rol yaratildi: \"{role.name}\" ({len(role.permissions)} ta ruxsat)")

    def perform_update(self, serializer):
        role = serializer.save()
        log_activity("admin", self.request.user.username, "role_updated",
                     f"Rol o'zgartirildi: \"{role.name}\" ({len(role.permissions)} ta ruxsat)")

    def perform_destroy(self, instance):
        name = instance.name
        count = instance.users.count()
        instance.delete()
        # Rol o'chirilganda foydalanuvchilar o'chmaydi (`SET_NULL`), lekin
        # rolsiz qolgani uchun panelga kira olmaydi — buni tarixda ko'rsatamiz.
        log_activity("admin", self.request.user.username, "role_deleted",
                     f"Rol o'chirildi: \"{name}\" — {count} ta administrator rolsiz qoldi")


class AdminUserViewSet(viewsets.ModelViewSet):
    """Panel foydalanuvchilari (administratorlar) — faqat superuser uchun.

    Faqat `is_staff` hisoblar ko'rinadi va yaratiladi: bu panel oddiy xodimlar
    (test topshiruvchilar) bilan ishlamaydi, ular butunlay boshqa jadvalda."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        return (
            User.objects.filter(is_staff=True)
            .select_related("admin_profile__role")
            .order_by("username")
        )

    def perform_create(self, serializer):
        user = serializer.save()
        log_activity("admin", self.request.user.username, "admin_user_created",
                     f"Administrator yaratildi: {user.username} ({role_name_for(user) or 'rolsiz'})")

    def perform_update(self, serializer):
        user = serializer.save()
        log_activity("admin", self.request.user.username, "admin_user_updated",
                     f"Administrator o'zgartirildi: {user.username} ({role_name_for(user) or 'rolsiz'})")

    def perform_destroy(self, instance):
        # O'zini o'chirib qo'yish — panelga qaytib kira olmaslik demak; shuning
        # uchun taqiqlanadi. Oxirgi superuser ham himoyalanadi.
        if instance.username == self.request.user.username:
            raise ValidationError({"error": "O'z hisobingizni o'chira olmaysiz."})
        if instance.is_superuser and User.objects.filter(is_superuser=True, is_active=True).count() <= 1:
            raise ValidationError({"error": "Oxirgi superuserni o'chirib bo'lmaydi."})
        username = instance.username
        instance.delete()
        log_activity("admin", self.request.user.username, "admin_user_deleted",
                     f"Administrator o'chirildi: {username}")


class TestAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_write_permission = "tests"
    # Savollar soni bitta so'rovda sanaladi (qarang: TestAdminSerializer.question_count).
    # "Kutish ro'yxati" bu ro'yxatni har test boshlanganda qayta so'raydi.
    queryset = (Test.objects.annotate(question_count_annotated=Count("questions"))
                .order_by("-created"))
    serializer_class = TestAdminSerializer

    def perform_create(self, serializer):
        test = serializer.save()
        log_activity("admin", self.request.user.username, "test_created", f"Test yaratildi: \"{test.name}\"")

    def perform_update(self, serializer):
        test = serializer.save()
        log_activity("admin", self.request.user.username, "test_updated", f"Test tahrirlandi: \"{test.name}\"")

    def perform_destroy(self, instance):
        name = instance.name
        instance.delete()
        log_activity("admin", self.request.user.username, "test_deleted", f"Test o'chirildi: \"{name}\"")


class QuestionAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "tests"
    serializer_class = QuestionAdminSerializer

    def get_queryset(self):
        qs = Question.objects.all().order_by("order", "id")
        test_id = self.request.query_params.get("test")
        if test_id:
            qs = qs.filter(test_id=test_id)
        return qs

    def perform_create(self, serializer):
        q = serializer.save()
        log_activity("admin", self.request.user.username, "question_created",
                     f"Savol qo'shildi ({q.test.name}): {q.text[:80]}")

    def perform_update(self, serializer):
        q = serializer.save()
        log_activity("admin", self.request.user.username, "question_updated",
                     f"Savol tahrirlandi ({q.test.name}): {q.text[:80]}")

    def perform_destroy(self, instance):
        test_name = instance.test.name
        text = instance.text[:80]
        instance.delete()
        log_activity("admin", self.request.user.username, "question_deleted",
                     f"Savol o'chirildi ({test_name}): {text}")


def _humanize_errors(errors):
    """DRF xatolar lug'atini odam o'qiy oladigan bitta qatorga aylantiradi.

    Ilgari bu yerda `str(serializer.errors)` turardi va administrator ekranda
    `{'options': [ErrorDetail(string="...", code='invalid')]}` ko'rinishidagi
    xom Python matnini ko'rardi — undan nimani to'g'rilash kerakligi
    tushunarsiz edi."""
    if isinstance(errors, dict):
        parts = []
        for field, messages in errors.items():
            if isinstance(messages, (list, tuple)):
                text = " ".join(str(m) for m in messages)
            else:
                text = str(messages)
            parts.append(text if field == "non_field_errors" else f"{field}: {text}")
        return " ".join(parts)
    if isinstance(errors, (list, tuple)):
        return " ".join(str(m) for m in errors)
    return str(errors)


def _error_sort_key(entry):
    """Xatolarni fayldagi tartib bo'yicha saralash uchun. `row` raqam ham,
    "-" ham bo'lishi mumkin (faylga umuman taalluqli bo'lmagan xato)."""
    row = entry.get("row")
    return (0, row) if isinstance(row, int) else (1, 0)


class QuestionImportView(APIView):
    """Fayldan savollarni import qilish — HAMMASI YOKI HECH NARSA.

    Agar faylda bitta bo'lsa ham xatolik topilsa, HECH QANDAY savol
    qo'shilmaydi: butun import bekor qilinadi va administratorga xatolar
    ro'yxati qaytariladi.

    Ilgari xatosiz savollar saqlanib, xatolilari o'tkazib yuborilardi. Amalda
    bu chalkashlik keltirib chiqarardi: administrator faylni to'g'rilab qayta
    yuklaganida, birinchi safar o'tgan savollar IKKINCHI marta qo'shilib,
    testda takror savollar paydo bo'lardi. Endi fayl yo butunlay qabul
    qilinadi, yo butunlay rad etiladi — qayta yuklash har doim xavfsiz."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "tests"
    parser_classes = [MultiPartParser]

    def post(self, request):
        test_id = request.data.get("test")
        file = request.FILES.get("file")
        if not test_id or not file:
            return Response({"error": "Test va fayl tanlanishi shart."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            test = Test.objects.get(pk=test_id)
        except Test.DoesNotExist:
            return Response({"error": "Test topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        try:
            decoded = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return Response({"error": "Fayl UTF-8 formatida bo'lishi kerak."}, status=status.HTTP_400_BAD_REQUEST)

        next_order = Question.objects.filter(test=test).count()
        filename = (file.name or "").lower()
        is_txt = filename.endswith(".txt")
        if is_txt:
            payloads, errors = _parse_txt_questions(decoded, next_order)
        else:
            payloads, errors = _parse_csv_questions(decoded, next_order)
        # TXT faylda savollar bo'sh qator bilan ajratilgan bloklar, CSV'da esa
        # qatorlar — xato qayerdaligini aytishda shu so'z ishlatiladi.
        row_label = "savol" if is_txt else "qator"

        if not payloads and not errors:
            return Response(
                {"created": 0, "errors": [], "row_label": row_label,
                 "error": "Faylda birorta ham savol topilmadi. Namuna faylni yuklab olib, "
                          "shu ko'rinishda to'ldiring."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Bitta tranzaksiya: xato topilsa hammasi qaytariladi (rollback).
        with transaction.atomic():
            created = 0
            for data in payloads:
                row_id = data.pop("_row", "-")
                data["test"] = test.id
                serializer = QuestionAdminSerializer(data=data)
                if serializer.is_valid():
                    serializer.save()
                    created += 1
                else:
                    errors.append({"row": row_id, "error": _humanize_errors(serializer.errors)})
            if errors:
                transaction.set_rollback(True)
                created = 0

        if errors:
            errors.sort(key=_error_sort_key)
            log_activity("admin", request.user.username, "questions_import_rejected",
                         f"Fayldan import rad etildi ({test.name}): {len(errors)} ta xato — "
                         f"hech qanday savol qo'shilmadi")
            return Response(
                {"created": 0, "errors": errors, "row_label": row_label,
                 "error": f"Faylda {len(errors)} ta xatolik bor — hech qanday savol qo'shilmadi. "
                          f"Xatoliklarni to'g'rilab, faylni qaytadan yuklang."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_activity("admin", request.user.username, "questions_imported",
                     f"Fayldan savollar import qilindi ({test.name}): {created} ta")
        return Response({"created": created, "errors": [], "row_label": row_label})


class QuestionImageView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "tests"
    parser_classes = [MultiPartParser]

    def post(self, request, pk):
        try:
            q = Question.objects.get(pk=pk)
        except Question.DoesNotExist:
            return Response({"error": "Savol topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        image = request.FILES.get("image")
        if not image:
            return Response({"error": "Rasm fayli topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        q.image = image
        q.save(update_fields=["image"])
        log_activity("admin", request.user.username, "question_image_uploaded",
                     f"Savolga rasm yuklandi ({q.test.name}): {q.text[:80]}")
        return Response({"image_url": request.build_absolute_uri(q.image.url)})

    def delete(self, request, pk):
        try:
            q = Question.objects.get(pk=pk)
        except Question.DoesNotExist:
            return Response({"error": "Savol topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        q.image.delete(save=True)
        log_activity("admin", request.user.username, "question_image_deleted",
                     f"Savol rasmi o'chirildi ({q.test.name}): {q.text[:80]}")
        return Response(status=status.HTTP_204_NO_CONTENT)


class OptionImageView(APIView):
    """Variant (javob varianti) rasmi — savol rasmidan alohida.

    Savol rasmi kabi ALOHIDA endpoint: savolni saqlash (JSON) va rasm yuklash
    (multipart) ikki xil so'rov. Shu sababdan savolni qayta-qayta saqlash
    variant rasmiga umuman tegmaydi."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "tests"
    parser_classes = [MultiPartParser]

    def _get(self, pk):
        return Option.objects.select_related("question__test").filter(pk=pk).first()

    def post(self, request, pk):
        opt = self._get(pk)
        if not opt:
            return Response({"error": "Variant topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        image = request.FILES.get("image")
        if not image:
            return Response({"error": "Rasm fayli topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        # Eski rasm almashtirilayotgan bo'lsa, uni diskda qoldirmaymiz.
        if opt.image:
            opt.image.delete(save=False)
        opt.image = image
        opt.save(update_fields=["image"])
        test_name = opt.question.test.name if opt.question and opt.question.test else "—"
        log_activity("admin", request.user.username, "option_image_uploaded",
                     f"Variantga rasm yuklandi ({test_name}): {opt.question.text[:60]}")
        return Response({"image_url": request.build_absolute_uri(opt.image.url)})

    def delete(self, request, pk):
        opt = self._get(pk)
        if not opt:
            return Response({"error": "Variant topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        opt.image.delete(save=True)
        test_name = opt.question.test.name if opt.question and opt.question.test else "—"
        log_activity("admin", request.user.username, "option_image_deleted",
                     f"Variant rasmi o'chirildi ({test_name}): {opt.question.text[:60]}")
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuestionGroupAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "tests"
    serializer_class = QuestionGroupSerializer

    def get_queryset(self):
        qs = QuestionGroup.objects.all().order_by("order", "id")
        test_id = self.request.query_params.get("test")
        if test_id:
            qs = qs.filter(test_id=test_id)
        return qs

    def perform_create(self, serializer):
        g = serializer.save()
        log_activity("admin", self.request.user.username, "group_created",
                     f"Bo'lim qo'shildi ({g.test.name}): {g.name}")

    def perform_update(self, serializer):
        g = serializer.save()
        log_activity("admin", self.request.user.username, "group_updated",
                     f"Bo'lim tahrirlandi ({g.test.name}): {g.name}")

    def perform_destroy(self, instance):
        test_name = instance.test.name
        name = instance.name
        instance.delete()
        log_activity("admin", self.request.user.username, "group_deleted",
                     f"Bo'lim o'chirildi ({test_name}): {name}")


class EmployeeAdminViewSet(viewsets.ModelViewSet):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "expected"
    # `assigned_test_name` uchun — usiz har xodimga alohida so'rov ketardi.
    queryset = Employee.objects.select_related("assigned_test").order_by("-created")
    serializer_class = EmployeeAdminSerializer

    def perform_create(self, serializer):
        emp = serializer.save()
        log_activity("admin", self.request.user.username, "employee_created",
                     f"Xodim qo'shildi: {emp.full_name}")

    def perform_update(self, serializer):
        emp = serializer.save()
        log_activity("admin", self.request.user.username, "employee_updated",
                     f"Xodim tahrirlandi: {emp.full_name}")

    def perform_destroy(self, instance):
        name = instance.full_name
        instance.delete()
        log_activity("admin", self.request.user.username, "employee_deleted",
                     f"Xodim o'chirildi: {name}")


STALE_ATTEMPT_SECONDS = 3 * 3600  # vaqt chegarasi yo'q/har-savol turidagi testlar uchun "tashlab ketilgan" chegara


class AdminActiveAttemptsView(APIView):
    """Hozirda test topshirayotgan xodimlar ro'yxati (jonli monitoring).
    Vaqti o'tib ketgan (tashlab ketilgan, hech qachon yakunlanmagan) seanslar ro'yxatga kiritilmaydi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "active"

    def get(self, request):
        # Testi yoki xodimi o'chirilgan seans "hozir topshirilmoqda" bo'la
        # olmaydi — u arxivda qoladi, lekin jonli ro'yxatga chiqmaydi.
        # `defer`: variantlar tartibi va qulflangan javoblar bu ro'yxatga kerak
        # emas, ular esa seansdagi eng katta maydonlar.
        attempts = (_maybe_live_attempts()
                    .filter(test__isnull=False, employee__isnull=False)
                    .select_related("employee", "test")
                    .defer("layout", "locked_answers")
                    .order_by("-created"))
        now = timezone.now()
        data = []
        for a in attempts:
            elapsed = int((now - a.created).total_seconds())
            test = a.test
            if _is_stale_attempt(a):
                continue  # tashlab ketilgan seans — "hozir topshirmoqda" emas
            data.append({
                "id": a.id,
                "full_name": a.employee.full_name,
                "department": a.employee.department,
                "test_name": test.name,
                "started_at": timezone.localtime(a.created).strftime("%H:%M:%S"),
                "elapsed_seconds": elapsed,
                "total_questions": len(a.question_ids),
                "time_limit": test.time_limit,
                "time_limit_scope": test.time_limit_scope,
                "proctoring": test.proctoring,
            })
        return Response(data)


# =========================================================================
# TASHQI DASHBOARD UCHUN OCHIQ (LOGINSIZ) ENDPOINT
#
# Tabel raqami bo'yicha xodimning test natijasi, protokoli va video yozuvini
# qaytaradi. Boshqa (tashqi) dashboard shu orqali ma'lumot oladi — u yerdagi
# foydalanuvchidan BnpzTest logini so'ralmaydi.
#
# DIQQAT — bu qismning xavfsizlik chegarasi ataylab past, shuning uchun uni
# o'zgartirishdan oldin quyidagini o'qing:
#
#   • Tabel raqami MAXFIY EMAS (nishonda yozilgan, ketma-ket beriladi). Ya'ni
#     u "parol" vazifasini bajara olmaydi: raqamlarni birma-bir sinab chiqqan
#     har kim istalgan xodimning ma'lumotini ko'ra oladi.
#   • Video yozuvda xodimning YUZI va EKRANI bor — bu shaxsiy ma'lumot.
#
# Shu sababli ikkita himoya qo'yilgan (ikkalasi ham foydalanuvchidan hech
# narsa so'ramaydi, ya'ni "loginsiz" talabini buzmaydi):
#
#   1) Video havolasi IMZOLANGAN va MUDDATLI (`_public_recording_url`) —
#      `/media/recordings/...` ochib qo'yilmagan, fayl nomini taxmin qilib
#      yuklab bo'lmaydi, tarqalib ketgan havola esa o'z-o'zidan eskiradi.
#   2) `PUBLIC_API_KEY` — standart holda BO'SH, ya'ni endpoint ochiq. Muhit
#      o'zgaruvchisiga qiymat berilsa, so'rovda `X-Api-Key` sarlavhasi (yoki
#      `?key=`) talab qilinadi. Kодni o'zgartirmasdan yopib qo'yish uchun.
# =========================================================================

PUBLIC_REC_SALT = "bnpztest-public-recording"
PUBLIC_PROTOCOL_SALT = "bnpztest-public-protocol"
PUBLIC_LINK_MAX_AGE = 60 * 60 * 6  # imzolangan havolalar 6 soat yashaydi
PUBLIC_REC_MAX_AGE = PUBLIC_LINK_MAX_AGE  # eski nom — kod bazasida qolgan joylar uchun


def _public_key_denied(request):
    """`PUBLIC_API_KEY` berilgan bo'lsa kalitni tekshiradi.

    Kalit qo'yilmagan bo'lsa (standart holat) — hech narsa so'ralmaydi va
    None qaytadi, ya'ni endpoint ochiq ishlaydi."""
    expected = getattr(django_settings, "PUBLIC_API_KEY", "")
    if not expected:
        return None
    given = request.headers.get("X-Api-Key") or request.query_params.get("key", "")
    if given != expected:
        return Response({"error": "Kirish kaliti noto'g'ri."}, status=status.HTTP_403_FORBIDDEN)
    return None


def _public_recording_url(recording, request):
    """Video uchun imzolangan, muddatli havola.

    Yozuvning haqiqiy fayl manzili (`/media/recordings/...`) BERILMAYDI: u
    faqat administrator tokeni bilan ochiladi va shunday qolishi kerak."""
    token = signing.dumps({"rec": recording.id}, salt=PUBLIC_REC_SALT)
    return request.build_absolute_uri(f"/api/public/recording/?t={token}")


def _public_protocol_url(result, request):
    """Bayonnomani ko'rsatadigan sahifaga imzolangan havola.

    Natija id'si ochiq berilmaydi: imzo bo'lmasa 1, 2, 3 … deb terib, boshqa
    xodimlarning bayonnomasini ochib chiqish mumkin bo'lardi."""
    token = signing.dumps({"res": result.id}, salt=PUBLIC_PROTOCOL_SALT)
    return request.build_absolute_uri(f"/api/public/protocol/view/?t={token}")


def _result_recordings(result):
    """Natijaga tegishli yozuvlar. Video ba'zan submit'dan KEYIN yuklanadi,
    shu sabab avval seans orqali qidiriladi (qarang: ResultDetailSerializer)."""
    return result.attempt.recordings.all() if result.attempt_id else result.recordings.all()


class PublicResultProtocolView(APIView):
    """GET /api/public/protocol/?tabel=10234

    Tabel raqami bo'yicha xodimning BARCHA topshirgan imtixonlarini qaytaradi —
    har biri sanasi, bayonnoma havolasi va video havolasi bilan. Eng yangisi
    birinchi turadi.

    Javob ataylab qisqa: ball, savol-javob tahlili va bo'limlar jadvali
    bayonnoma SAHIFASINING o'zida ko'rinadi, ularni bu yerda takrorlash
    ortiqcha edi.

    Autentifikatsiya ATAYLAB yo'q — qarang: yuqoridagi izoh."""

    # DRF standarti bo'sh, lekin bu yerda ochiq-oydin yozamiz: bu endpoint
    # keyinchalik "nega himoyasiz?" degan savol tug'dirmasligi kerak.
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        denied = _public_key_denied(request)
        if denied:
            return denied

        tabel = (request.query_params.get("tabel") or "").strip()
        if not tabel:
            return Response({"error": "Tabel raqami ko'rsatilmagan (?tabel=...)."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Tabel raqami natijaning O'ZIDA saqlanadi (topshirish paytida nusxa
        # olinadi), shuning uchun xodim keyin o'chirilgan bo'lsa ham topiladi.
        #
        # `prefetch_related` SHART: har bir natija uchun video yozuvi alohida
        # so'ralsa, 20 ta imtixoni bor xodimda 40 ta ortiqcha so'rov ketardi.
        results = list(
            Result.objects.filter(tabel_number=tabel)
            .select_related("attempt")
            .prefetch_related("attempt__recordings", "recordings")
            .order_by("-created")
        )
        if not results:
            return Response(
                {"error": f"«{tabel}» tabel raqami bo'yicha test natijasi topilmadi."},
                status=status.HTTP_404_NOT_FOUND,
            )

        exams = []
        for r in results:
            # Video odatda bitta bo'ladi — ekran va yuz bitta faylga
            # birlashtirib yoziladi (qarang: proctoring.js).
            rec = next((x for x in _result_recordings(r) if x.file), None)
            exams.append({
                "test_name": r.test_name,
                # Test TOPSHIRILGAN (yakunlangan) payt, server vaqt mintaqasida
                # (Asia/Tashkent) va tayyor ko'rinishda — dashboard tarafida
                # qayta formatlash shart bo'lmasin. Bayonnomadagi sana ham shu
                # qiymatdan olinadi, ya'ni ikkalasi doim mos keladi. Soat ham
                # bor: xodim bir kunda ikki marta topshirishi mumkin.
                "date": timezone.localtime(r.created).strftime("%d.%m.%Y %H:%M"),
                "protocol_url": _public_protocol_url(r, request),
                "video_url": _public_recording_url(rec, request) if rec else None,
            })

        # Ism eng so'nggi natijadan olinadi (ro'yxat "-created" bo'yicha) —
        # xodimning ismi o'zgargan bo'lsa, eng yangi yozuvdagisi to'g'riroq.
        return Response({"full_name": results[0].full_name, "exams": exams})


def public_protocol_page(request):
    """GET /api/public/protocol/view/?t=<imzo>

    Bayonnomani to'liq HTML sahifa ko'rinishida chizadi — tashqi dashboard uni
    havola orqali (yangi oynada yoki iframe ichida) ochadi. Sahifa mustaqil:
    CSS ichida, tashqi fayl yuklanmaydi, "Chop etish / PDF saqlash" tugmasi bor.

    `PUBLIC_API_KEY` bu yerda tekshirilmaydi va bu ataylab: havolaning o'zi
    allaqachon imzolangan, ya'ni uni taxmin qilib bo'lmaydi. Kalitni bu yerda
    ham talab qilish — uni havola ichiga yozishni anglatardi, ya'ni dashboard
    sahifasida ochiq ko'rinib qolardi."""
    try:
        payload = signing.loads(
            request.GET.get("t", ""), salt=PUBLIC_PROTOCOL_SALT, max_age=PUBLIC_LINK_MAX_AGE,
        )
    except signing.BadSignature:
        return HttpResponse("Havolaning muddati tugagan yoki u noto'g'ri.", status=403)

    result = Result.objects.filter(pk=payload.get("res")).first()
    if not result:
        return HttpResponse("Natija topilmadi.", status=404)

    protocol = build_protocol(result)
    # Savollar jadvali 10 tadan qatorlarga bo'linadi — Django shablonida bunday
    # bo'lish imkoni yo'q, shu sabab bu yerda tayyorlanadi (qarang: Protocol.jsx).
    per_q = protocol.get("per_question") or []
    question_rows = [per_q[i:i + 10] for i in range(0, len(per_q), 10)]
    return render(request, "core/protocol.html", {"p": protocol, "question_rows": question_rows})


class PublicRecordingView(APIView):
    """GET /api/public/recording/?t=<imzo>

    `PublicResultProtocolView` bergan imzolangan havola bo'yicha video faylni
    uzatadi. Imzo Django'ning SECRET_KEY'i bilan qo'yiladi va 6 soatdan keyin
    yaroqsiz bo'ladi, ya'ni havola tarqalib ketsa ham abadiy ochiq qolmaydi."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            payload = signing.loads(
                request.query_params.get("t", ""), salt=PUBLIC_REC_SALT, max_age=PUBLIC_REC_MAX_AGE,
            )
        except signing.BadSignature:
            # Muddati tugagan va soxta imzo — mijoz uchun bir xil: yangi havola
            # olish uchun protokolni qayta so'rash kerak.
            return HttpResponse("Video havolasining muddati tugagan. Sahifani yangilang.", status=403)

        rec = Recording.objects.filter(pk=payload.get("rec")).first()
        if not rec or not rec.file or not os.path.isfile(rec.file.path):
            return HttpResponse("Video yozuv topilmadi.", status=404)
        _ensure_recording_duration_fixed(rec, rec.file.path)
        return _serve_video_range(request, rec.file.path)


class AdminResultsListView(ListAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "results"
    # `select_related("test")`: ro'yxatdagi `tsex` ustuni testdan olinadi —
    # usiz HAR BIR natija uchun alohida so'rov ketardi (1500 natija = 1500 so'rov).
    # `defer("answers")`: savol-javob tahlili ro'yxatda ko'rsatilmaydi, lekin
    # u natijadagi eng katta maydon — har ochilishda megabaytlab ortiqcha ma'lumot.
    queryset = Result.objects.select_related("test").defer("answers")
    serializer_class = ResultSerializer


class AdminResultDetailView(RetrieveAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "results"
    queryset = Result.objects.all()
    serializer_class = ResultDetailSerializer


class AdminResultProtocolView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "results"

    def get(self, request, pk):
        try:
            result = Result.objects.get(pk=pk)
        except Result.DoesNotExist:
            return Response({"error": "Natija topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        return Response(build_protocol(result))


# =========================================================================
# Tizim bo'limlari (holat, tarix, video arxiv).
#
# Ilgari bular faqat superuserga ochiq edi; endi oddiy bo'limlar kabi rolga
# beriladi — superuser xohlasa istalgan rolga ochib qo'yadi. Har biri o'z
# `required_permission` kaliti bilan SERVERDA tekshiriladi: menyuda bo'limni
# yashirishning o'zi yetarli emas, chunki ruxsati yo'q administrator
# endpointga to'g'ridan-to'g'ri murojaat qilishi mumkin.
# =========================================================================

class AdminActivityLogView(APIView):
    """Amallar tarixi: kim kirdi, kim test yaratdi/o'chirdi, kim topshirdi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "activity"

    def get(self, request):
        qs = ActivityLog.objects.all()

        actor = request.query_params.get("actor")
        if actor in ("admin", "employee"):
            qs = qs.filter(actor=actor)
        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        search = (request.query_params.get("q") or "").strip()
        if search:
            qs = qs.filter(Q(actor_name__icontains=search) | Q(description__icontains=search))

        total = qs.count()
        try:
            offset = max(0, int(request.query_params.get("offset", 0) or 0))
            limit = min(200, max(1, int(request.query_params.get("limit", 50) or 50)))
        except (TypeError, ValueError):
            offset, limit = 0, 50

        rows = [{
            "id": a.id,
            "created": timezone.localtime(a.created).strftime("%d.%m.%Y %H:%M:%S"),
            "actor": a.actor,
            "actor_label": a.get_actor_display(),
            "actor_name": a.actor_name,
            "action": a.action,
            "description": a.description,
            "meta": a.meta,
        } for a in qs[offset:offset + limit]]

        return Response({
            "total": total, "offset": offset, "limit": limit, "rows": rows,
            # Filtr ro'yxatini to'ldirish uchun — mavjud amal turlari.
            # `order_by()` SHART: modelning standart tartibi (-created) bo'lsa,
            # DISTINCT (action, created) juftligiga qo'llanib, ro'yxat takror
            # qiymatlar bilan to'lardi (panelda ham takror bandlar ko'rinardi).
            "actions": sorted(ActivityLog.objects.order_by()
                              .values_list("action", flat=True).distinct()),
        })


def _parse_date_param(value):
    """`<input type="date">` bergan "YYYY-MM-DD" qatorini sanaga aylantiradi.

    Buzuq qiymatda filtr shunchaki QO'LLANMAYDI (500 emas): bu ixtiyoriy
    filtr, uni tushunmaslik butun arxiv ro'yxatini yiqitmasligi kerak."""
    try:
        return date.fromisoformat((value or "").strip())
    except (ValueError, AttributeError, TypeError):
        return None


def _recordings_queryset(params):
    """Arxiv filtri — YAGONA joyda.

    Ro'yxat (`AdminRecordingsListView`) ham, ZIP arxivi
    (`AdminRecordingsArchiveView`) ham SHU funksiyadan foydalanadi. Ikki
    joyda takrorlansa, ular jimgina bir-biridan farq qila boshlardi va
    administrator ekranda bir narsani ko'rib, arxivda boshqa narsani olardi.

    Tabel va sex avval yozuvning O'ZIDAGI nusxadan (`Recording.tabel_number`,
    `Recording.tsex`) qidiriladi — seans o'chirilgan eski yozuv ham filtrga
    tushishi kerak (qarang: Recording modeli izohi). Qo'shimcha ravishda
    seans orqali ham qidiriladi, chunki JADVAL ham xuddi shunday zaxira
    bilan ko'rsatadi (`_recording_row_tabel`/`_recording_row_tsex`): nusxasi
    bo'sh qolgan yozuv ekranda "5-Sex" bo'lib turib, o'sha sex bo'yicha
    filtrlanganda topilmasligi — administrator uchun tushuntirib bo'lmaydigan
    xatti-harakat bo'lardi. Ko'rsatish va filtr BIR XIL manbalarga tayanishi
    shart."""
    qs = (Recording.objects
          .select_related("attempt", "attempt__employee", "attempt__test", "result")
          .order_by("-created"))

    kind = params.get("kind")
    if kind in ("screen", "face"):
        qs = qs.filter(kind=kind)

    search = (params.get("q") or "").strip()
    if search:
        # Nomi yozuvning o'zida ham saqlanadi — seans o'chirilgan eski
        # yozuvlar ham qidiruvda topilishi kerak.
        qs = qs.filter(Q(employee_name__icontains=search)
                       | Q(attempt__employee__full_name__icontains=search))

    tabel = (params.get("tabel") or "").strip()
    if tabel:
        qs = qs.filter(Q(tabel_number__icontains=tabel)
                       | Q(attempt__employee__tabel_number__icontains=tabel))

    tsex = (params.get("tsex") or "").strip()
    if tsex:
        qs = qs.filter(Q(tsex=tsex) | Q(attempt__test__tsex=tsex))

    # Sana oralig'i — ikki chegara ham ICHIGA OLINADI ("1-dan 1-gacha" o'sha
    # kunning o'zini beradi). `__date` taqqoslash server vaqt mintaqasida
    # (Asia/Tashkent) bajariladi, ya'ni admin ko'rgan sana bilan bir xil.
    date_from = _parse_date_param(params.get("date_from"))
    if date_from:
        qs = qs.filter(created__date__gte=date_from)
    date_to = _parse_date_param(params.get("date_to"))
    if date_to:
        qs = qs.filter(created__date__lte=date_to)

    return qs


def _recording_row_tabel(rec):
    return (rec.tabel_number
            or (rec.attempt.employee.tabel_number
                if rec.attempt and rec.attempt.employee else "")
            or "")


def _recording_row_tsex(rec):
    return (rec.tsex
            or (rec.attempt.test.tsex if rec.attempt and rec.attempt.test else "")
            or "")


class AdminRecordingsListView(APIView):
    """Video nazorat yozuvlari arxivi.

    Filtrlar: tur, ism-familiya, tabel raqami, sex va sana oralig'i —
    hammasi `_recordings_queryset` da.

    `with_options=1` berilsa, javobga sex ro'yxati ham qo'shiladi. Ataylab
    SO'RALGANDA: panel uni tab ochilganda bir marta oladi, har qidiruv
    harfida emas."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "recordings"

    def get(self, request):
        qs = _recordings_queryset(request.query_params)

        total = qs.count()
        try:
            offset = max(0, int(request.query_params.get("offset", 0) or 0))
            limit = min(200, max(1, int(request.query_params.get("limit", 50) or 50)))
        except (TypeError, ValueError):
            offset, limit = 0, 50

        rows = []
        for r in qs[offset:offset + limit]:
            attempt = r.attempt
            try:
                size_mb = round(r.file.size / (1024 * 1024), 1) if r.file else None
            except (OSError, ValueError):
                # Fayl diskdan qo'lda o'chirilgan bo'lishi mumkin — bu ro'yxatni buzmasin.
                size_mb = None
            rows.append({
                "id": r.id,
                "created": timezone.localtime(r.created).strftime("%d.%m.%Y %H:%M"),
                "kind": r.kind,
                "kind_label": r.get_kind_display(),
                # Avval yozuvning o'zidagi nusxa, so'ng seans orqali — eski
                # yozuvlarda nusxa bo'lmasligi mumkin, seansi bor bo'lsa
                # ismni o'sha yerdan olamiz.
                "employee": (r.employee_name
                             or (attempt.employee.full_name if attempt and attempt.employee else "")
                             or "—"),
                "test_name": (r.test_name
                              or (attempt.test.name if attempt and attempt.test else "")
                              or "—"),
                # Filtr aynan shu ikki ustun bo'yicha ishlaydi, shuning uchun
                # ular jadvalda ham ko'rinadi: aks holda administrator "nega
                # bu qator chiqdi/chiqmadi?" degan savolga javob topa olmasdi.
                "tabel_number": _recording_row_tabel(r) or "—",
                "tsex": _recording_row_tsex(r) or "—",
                "result_id": r.result_id,
                "pct": r.result.pct if r.result else None,
                "size_mb": size_mb,
                # Token qo'shilgan manzil — video fayllar endi faqat
                # administrator tokeni bilan ochiladi (MediaRecordingView).
                "url": recording_media_url(r, request),
            })

        data = {"total": total, "offset": offset, "limit": limit, "rows": rows}
        if request.query_params.get("with_options"):
            # Faqat arxivda HAQIQATAN uchraydigan sexlar. BnpzId katalogidagi
            # barcha sexni ko'rsatish "tanladim — hech narsa chiqmadi" holatiga
            # olib borardi. Bo'sh qiymat ro'yxatga tushmaydi: bog'lanishi
            # uzilgan eski yozuvning sexi noma'lum, uni tanlash imkoni yo'q.
            data["tsex_options"] = sorted(
                Recording.objects.exclude(tsex="")
                .values_list("tsex", flat=True).distinct()
            )
        return Response(data)


# =========================================================================
# Filtrlangan yozuvlarni BITTA .zip arxivida yuklab olish
#
# Chegaralar ATAYLAB qo'yilgan. Fayllar katta (o'rtacha ~10 MB, ba'zan 100+)
# va arxiv oqim bilan beriladi — ya'ni bitta so'rov bir necha daqiqa davom
# etishi mumkin. Chegarasiz "hammasini yukla" bir bosishda o'nlab gigabaytni
# tortib, shu payt test topshirayotgan xodimlarning video bo'laklari
# yuklanishini sekinlashtirardi.
#
# Chegaraga urilganda administrator xato emas, TUSHUNARLI YO'RIQNOMA oladi:
# filtrni toraytirish (odatda sana oralig'ini qisqartirish). Panel bu
# holatga yetib ham bormaydi — yuklashdan oldin `probe=1` bilan so'rab,
# hajmni va sonini ko'rsatib tasdiq oladi.
# =========================================================================

ARCHIVE_MAX_FILES = 200
ARCHIVE_MAX_BYTES = 5 * 1024 ** 3  # 5 GB
_ARCHIVE_READ_CHUNK = 512 * 1024

# Windows fayl nomida ishlatib bo'lmaydigan belgilar (va boshqaruv belgilari).
_ARCHIVE_BAD_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


class _ZipSink:
    """`zipfile` yozadigan "fayl" — baytlarni ushlab turadi, generator esa
    ularni olib chiqib mijozga uzatadi.

    `tell()` ATAYLAB e'lon qilinmagan: shunda `zipfile` oqimni "seek qilib
    bo'lmaydigan" deb tanib, har bir yozuv uchun data descriptor ishlatadi —
    ya'ni arxiv to'liq yig'ilishini kutmasdan, bo'lak-bo'lak uzatiladi. Aks
    holda 5 GB arxiv avval butunlay xotiraga (yoki vaqtinchalik faylga)
    yig'ilishi kerak bo'lardi."""

    def __init__(self):
        self._chunks = []

    def write(self, data):
        self._chunks.append(bytes(data))
        return len(data)

    def flush(self):
        pass

    def take(self):
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def _archive_entry_name(rec, used):
    """Arxiv ichidagi fayl nomi — o'qib tushunarli va Windows qabul qiladigan.

    Takrorlanmaslik SHART: bir xil nomli ikkinchi yozuv arxivda birinchisini
    yashirib qo'yardi (ba'zi dasturlar ogohlantirmasdan ustiga ochadi).
    Takror uchraganda nomga yozuv raqami qo'shiladi — u yagona, ya'ni natija
    har doim takrorlanmas bo'ladi."""
    parts = [timezone.localtime(rec.created).strftime("%Y-%m-%d_%H-%M")]
    tabel = _recording_row_tabel(rec)
    if tabel:
        parts.append(tabel)
    parts.append(rec.employee_name or "xodim")
    if rec.test_name:
        parts.append(rec.test_name)
    parts.append(rec.kind)
    stem = _ARCHIVE_BAD_CHARS.sub("-", "_".join(parts)).strip(". ")[:120]
    stem = stem or f"yozuv-{rec.id}"

    ext = os.path.splitext(rec.file.name)[1].lower() or ".webm"
    name = f"{stem}{ext}"
    if name.lower() in used:
        name = f"{stem}_{rec.id}{ext}"
    used.add(name.lower())
    return name


def _archive_manifest(rows):
    """Arxiv ichiga qo'shiladigan ro'yxat (CSV).

    Fayl nomi qanchalik tushunarli bo'lmasin, unga hamma narsa sig'maydi
    (sex, natija, hajm). Bundan tashqari bu ro'yxat arxiv NIMA ASOSDA
    yig'ilganini hujjatlashtiradi — keyin "bu videolar qayerdan kelgan?"
    degan savolga javob bo'ladi."""
    out = io.StringIO()
    out.write("\ufeff")  # Excelda kirill/lotin harflar to'g'ri ko'rinishi uchun BOM
    writer = csv.writer(out)
    writer.writerow(["Fayl", "Sana", "Tabel", "Xodim", "Sex", "Test", "Turi",
                     "Natija (%)", "Hajm (MB)"])
    for name, rec, size in rows:
        writer.writerow([
            name,
            timezone.localtime(rec.created).strftime("%d.%m.%Y %H:%M"),
            _recording_row_tabel(rec) or "—",
            rec.employee_name or "—",
            _recording_row_tsex(rec) or "—",
            rec.test_name or "—",
            rec.get_kind_display(),
            rec.result.pct if rec.result_id else "—",
            round(size / (1024 * 1024), 1),
        ])
    return out.getvalue().encode("utf-8")


def _archive_stream(entries, manifest):
    """(nom, yo'l) juftliklarini bitta ZIP oqimiga aylantiradi.

    ZIP_STORED (siqishsiz) ATAYLAB: WebM allaqachon siqilgan videodan
    iborat, deflate unga protsessor vaqtini sarflab amalda hech narsa
    yutmaydi — katta arxivda bu bir necha daqiqalik bekor kutish bo'lardi."""
    sink = _ZipSink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.writestr("ROYXAT.csv", manifest)
        chunk = sink.take()
        if chunk:
            yield chunk

        for name, path in entries:
            try:
                src = open(path, "rb")
            except OSError as exc:
                # Fayl ro'yxat tuzilgandan keyin yo'qolgan — butun arxivni
                # yiqitmaymiz; u ROYXAT.csv da baribir qayd etilgan.
                logger.warning("Arxivga qo'shib bo'lmadi: %s — %s", path, exc)
                continue
            with src, zf.open(name, "w") as dst:
                while True:
                    block = src.read(_ARCHIVE_READ_CHUNK)
                    if not block:
                        break
                    dst.write(block)
                    out = sink.take()
                    if out:
                        yield out
            out = sink.take()
            if out:
                yield out

    tail = sink.take()  # markaziy katalog
    if tail:
        yield tail


class AdminRecordingsArchiveView(APIView):
    """GET /api/admin/recordings/archive/ — filtrlangan yozuvlar bitta .zip da.

    Filtr ro'yxatdagi bilan AYNAN bir xil (`_recordings_queryset`), shuning
    uchun administrator ekranda ko'rgan narsasini yuklab oladi. Ro'yxat
    sahifalarga bo'linadi, arxiv esa BO'LINMAYDI: butun filtr natijasi
    (chegaragacha) tushadi — "faqat shu sahifadagi 50 tasi" degan yashirin
    cheklov kutilmagan bo'lardi.

    `probe=1` — hech narsa yubormasdan, faqat "nechta fayl, necha MB va
    chegaraga sig'adimi" degan javob. Panel yuklashdan oldin shuni so'rab,
    hajmni ko'rsatib tasdiq oladi; usiz administrator bir bosishda bir necha
    gigabaytni bilmasdan tortib yuborardi.

    Ruxsat — ro'yxat bilan bir xil ("recordings"). Bu yangi huquq BERMAYDI:
    shu ruxsatga ega administrator har bir faylni allaqachon bittalab ocha
    va yuklab olishi mumkin (qarang: `media_recordings_view`), bu yerda
    faqat o'sha ish qulayroq bajariladi."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "recordings"

    def get(self, request):
        # Chegaradan bittasini ortiqcha olamiz — "aynan chegaracha" bilan
        # "chegaradan oshdi" ni ajratish uchun.
        records = list(_recordings_queryset(request.query_params)[:ARCHIVE_MAX_FILES + 1])
        too_many = len(records) > ARCHIVE_MAX_FILES
        records = records[:ARCHIVE_MAX_FILES]

        entries, rows, used = [], [], set()
        total_bytes = 0
        missing = 0
        for rec in records:
            try:
                path = rec.file.path if rec.file else None
                size = os.path.getsize(path) if path and os.path.isfile(path) else None
            except (OSError, ValueError, NotImplementedError):
                path, size = None, None
            if path is None or size is None:
                # Diskda yo'q fayl (qo'lda o'chirilgan) — arxivga qo'shilmaydi,
                # lekin bu butun yuklashni to'xtatmaydi; soni javobda aytiladi.
                missing += 1
                continue
            name = _archive_entry_name(rec, used)
            entries.append((name, path))
            rows.append((name, rec, size))
            total_bytes += size

        too_big = total_bytes > ARCHIVE_MAX_BYTES
        size_mb = round(total_bytes / (1024 * 1024), 1)

        if request.query_params.get("probe"):
            return Response({
                "count": len(entries),
                "size_mb": size_mb,
                "missing": missing,
                "too_many": too_many,
                "too_big": too_big,
                "max_files": ARCHIVE_MAX_FILES,
                "max_mb": ARCHIVE_MAX_BYTES // (1024 * 1024),
            })

        # Quyidagi uchta rad javobi — ikkinchi to'siq. Panel bu holatlarga
        # `probe` orqali yo'l qo'ymaydi, lekin havola qo'lda ham ochilishi
        # mumkin. Javob ODDIY MATN: brauzer uni o'sha zahoti o'qiladigan
        # holda ko'rsatadi (JSON esa yuklab olinadigan fayl bo'lib tushardi).
        if not entries:
            return HttpResponse(
                "Filtrga mos video yozuv topilmadi — yuklab oladigan narsa yo'q.",
                content_type="text/plain; charset=utf-8", status=404,
            )
        if too_many:
            return HttpResponse(
                f"Filtrga {ARCHIVE_MAX_FILES} tadan ko'p yozuv mos keldi. "
                f"Filtrni toraytiring (masalan sana oralig'ini qisqartiring).",
                content_type="text/plain; charset=utf-8", status=400,
            )
        if too_big:
            return HttpResponse(
                f"Arxiv hajmi {size_mb} MB — chegara {ARCHIVE_MAX_BYTES // (1024 * 1024)} MB. "
                f"Filtrni toraytiring (masalan sana oralig'ini qisqartiring).",
                content_type="text/plain; charset=utf-8", status=400,
            )

        stamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d_%H%M")
        response = StreamingHttpResponse(
            _archive_stream(entries, _archive_manifest(rows)),
            content_type="application/zip",
        )
        # Nom ataylab ASCII: `filename*` (RFC 5987) ba'zi eski yuklovchilarda
        # noto'g'ri o'qiladi, sana esa har qanday tilda bir xil tushuniladi.
        response["Content-Disposition"] = f'attachment; filename="video-yozuvlar_{stamp}.zip"'
        # Umumiy uzunlik oldindan noma'lum (oqim) — brauzer foizni
        # ko'rsatmaydi, lekin hajm `probe` orqali allaqachon aytilgan.
        log_activity("admin", request.user.username, "recordings_archived",
                     f"{len(entries)} ta video yozuv ZIP arxivida yuklab olindi ({size_mb} MB)",
                     {"count": len(entries), "size_mb": size_mb,
                      "filters": {k: v for k, v in request.query_params.items()
                                  if k not in ("token", "probe")}})
        return response


REC_SIZE_CACHE_KEY = "sysstatus_recordings_total_bytes"
# Hajm shuncha vaqtda bir qayta hisoblanadi — "Tizim holati" uchun yetarli aniqlik.
REC_SIZE_CACHE_TTL = 10 * 60


def _recordings_total_bytes():
    """Barcha video yozuvlarning umumiy hajmi (bayt). KESHLANADI.

    Hisoblash qimmat: har bir yozuv fayli uchun diskka alohida `os.stat`
    ketadi, disk esa Docker Desktop orqali ulangan Windows papkasi (har
    murojaat sekin). Yuzlab fayl bilan bu soniyalar oladi.

    Ilgari kesh har yozuvda — HAR BIR VIDEO BO'LAGIDA ham — tozalanardi. Test
    paytida bo'lak har xodimdan 10 soniyada bir keladi, ya'ni 10 xodimda kesh
    sekundiga bir marta o'chardi va "Tizim holati" (har 15 soniyada so'raydi)
    amalda HAR SAFAR butun arxivni qaytadan o'lchardi — aynan eng band paytda.
    Endi yuklash keshga tegmaydi: qiymat ko'pi bilan `REC_SIZE_CACHE_TTL`
    eskiradi. O'chirishda esa (kamdan-kam amal) darhol yangilanadi."""
    cached = cache.get(REC_SIZE_CACHE_KEY)
    if cached is not None:
        return cached
    total = 0
    for r in Recording.objects.only("file"):
        try:
            total += r.file.size if r.file else 0
        except (OSError, ValueError):
            pass  # diskda yo'q fayl — hisobga olinmaydi
    cache.set(REC_SIZE_CACHE_KEY, total, REC_SIZE_CACHE_TTL)
    return total


def _maybe_live_attempts():
    """Hali davom etayotgan BO'LISHI MUMKIN bo'lgan seanslar — SQL darajasida.

    Yakunlanmagan seanslar jadvalda abadiy qoladi (brauzer yopilgan, boshlanmay
    qolgan va h.k.) va vaqt o'tgan sari ko'payadi. Ilgari "Faol seanslar" (har
    5 soniyada) va "Tizim holati" (har 15 soniyada) ularning HAMMASINI, katta
    JSON maydonlari bilan birga bazadan olib, tashlab ketilganlarini Python'da
    ajratardi.

    Tashlab ketilmagan seans `_is_stale_attempt` ga ko'ra eng ko'pi bilan
    max(STALE_ATTEMPT_SECONDS, eng uzun vaqt chegarasi) oldin boshlangan
    bo'ladi — shundan eskisi bazadan umuman olinmaydi. Aniq tekshiruv
    (`_is_stale_attempt`) chaqiruvchida o'zgarishsiz qoladi."""
    longest_minutes = Test.objects.aggregate(m=Max("time_limit"))["m"] or 0
    window = max(STALE_ATTEMPT_SECONDS, longest_minutes * 60)
    return Attempt.objects.filter(
        completed=False, created__gte=timezone.now() - timedelta(seconds=window),
    )


class AdminSystemStatusView(APIView):
    """Tizim holati: umumiy sonlar, sinxronizatsiya va disk hajmi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "sysstatus"

    def get(self, request):
        now = timezone.now()
        today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)

        total_bytes = _recordings_total_bytes()

        active = [a for a in _maybe_live_attempts().select_related("test")
                  .only("created", "test", "test__time_limit", "test__time_limit_scope")
                  if not _is_stale_attempt(a)]

        synced = SyncedEmployee.objects.all()

        return Response({
            "tests": Test.objects.count(),
            "questions": Question.objects.count(),
            "employees": Employee.objects.count(),
            "results_total": Result.objects.count(),
            "results_today": Result.objects.filter(created__gte=today).count(),
            "attempts_active": len(active),
            "attempts_unfinished": Attempt.objects.filter(completed=False).count(),
            "checkins_waiting": CheckIn.objects.filter(status="waiting").count(),
            "expected_today": ExpectedEmployee.objects.count(),
            # DIQQAT — bu ikkisi MAHALLIY nusxaning sonlari, BnpzId'dagi
            # haqiqiy son emas. Davriy sinxron bor paytda ikkisi deyarli bir xil
            # bo'lardi; endi mahalliy nusxa faqat qidiruv tekkan xodimlar bilan
            # yangilanadi, ya'ni u BnpzId'dan orqada qolishi mumkin. Shuning
            # uchun paneldagi yozuvlar ham aynan shunday nomlangan.
            "synced_employees": synced.count(),
            "synced_with_face": synced.exclude(face_embedding=None).count(),
            # `last_sync` OLIB TASHLANDI. U `synced_at` (auto_now) ning eng
            # kattasi edi, ya'ni davriy sinxron yo'qolgach "oxirgi sinxron"
            # emas, "qidiruv oxirgi marta qaysi qatorga tekkani" ni ko'rsatib
            # qolgandi — hech kimga kerak bo'lmagan, chalg'ituvchi sana.
            "recordings": Recording.objects.count(),
            "recordings_size_mb": round(total_bytes / (1024 * 1024), 1),
            "admins_total": User.objects.filter(is_staff=True, is_active=True).count(),
            "admins_system": User.objects.filter(is_superuser=True, is_active=True).count(),
            "server_time": timezone.localtime(now).strftime("%d.%m.%Y %H:%M:%S"),
        })


def _admin_user_from_request(request):
    """So'rovdagi administrator tokenidan (sarlavha yoki ?token=) foydalanuvchini
    qaytaradi. Token yo'q/buzuq yoki hisob o'chirilgan bo'lsa None.

    Oddiy Django view uchun — DRF `Request` emas, xom `HttpRequest` keladi."""
    header = request.headers.get("Authorization", "")
    token = header[len("Token "):].strip() if header.startswith("Token ") else request.GET.get("token", "")
    if not token:
        return None
    try:
        payload = signing.loads(token, salt=ADMIN_TOKEN_SALT, max_age=ADMIN_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return (User.objects
            .filter(username=payload.get("username", ""), is_active=True, is_staff=True)
            .select_related("admin_profile__role").first())


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def _stream_range(fh, length, chunk_size=64 * 1024):
    """Fayldan aynan `length` baytni bo'lak-bo'lak o'qib beradi (generator),
    oxirida faylni yopadi. `fh` chaqiruvchi tomonidan kerakli o'rniga
    (`seek`) qo'yilgan bo'lishi kerak."""
    remaining = length
    try:
        while remaining > 0:
            chunk = fh.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        fh.close()


def _serve_video_range(request, file_path):
    """Video faylni HTTP Range (RFC 7233) qo'llab-quvvatlagan holda uzatadi.

    `django.views.static.serve` (demak, ilgari shu yerda ishlatilgan
    `_media_serve`) Range sarlavhasini UMUMAN tushunmaydi — so'rovda qanday
    bo'lmasin, har doim faylning HAMMASINI 200 bilan qaytaradi (Django buni
    ataylab shunday qilgan: bu funksiya faqat DEV rejimi uchun mo'ljallangan,
    production uchun emas — qarang: uning o'z docstring'i).

    Buning oqibati: brauzer videoni "xohlagan soniyaga" sakratmoqchi bo'lsa,
    aynan shu — faylning oxiridan kichik bir bo'lakni Range so'rovi bilan
    so'rab, haqiqiy uzunlikni va sakrash nuqtasini shundan bilib olishi kerak.
    Javob har doim to'liq fayl bo'lgach, bu so'rov ma'nosiz bo'lib qoladi va
    pleyer sakray olmaydi — video "bir joyda muzlaganday" ko'rinadi.

    `Accept-Ranges: bytes` — Range so'ralmagan (masalan, "Yuklab olish")
    holatda ham qo'yiladi: shu sarlavhaning o'ziyoq brauzerga "keyinroq
    Range so'rasa bo'ladi" deb bildiradi."""
    size = os.path.getsize(file_path)
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"

    range_header = request.headers.get("Range", "")
    match = _RANGE_RE.match(range_header)
    if not match:
        response = StreamingHttpResponse(
            _stream_range(open(file_path, "rb"), size), content_type=content_type,
        )
        response.headers["Content-Length"] = str(size)
        response.headers["Accept-Ranges"] = "bytes"
        return response

    start_s, end_s = match.groups()
    if start_s == "":
        # "bytes=-500" — RFC 7233 §2.1'da BOSHQA ma'noga ega: "oxirgi 500 bayt",
        # "0-dan 500-gacha" emas. Aynan shu shakl brauzerlarning "davomiylikni
        # oxirdan bilib olish" (Cues/SeekHead qidirish) urinishida ishlatiladi —
        # noto'g'ri tushunilsa, davomiylik hech qachon aniqlanmaydi.
        if not end_s or int(end_s) <= 0:
            response = HttpResponse(status=416)
            response.headers["Content-Range"] = f"bytes */{size}"
            return response
        start = max(0, size - int(end_s))
        end = size - 1
    else:
        start = int(start_s)
        end = int(end_s) if end_s else size - 1
        end = min(end, size - 1)
    if start > end or start >= size:
        response = HttpResponse(status=416)
        response.headers["Content-Range"] = f"bytes */{size}"
        return response

    length = end - start + 1
    fh = open(file_path, "rb")
    fh.seek(start)
    response = StreamingHttpResponse(
        _stream_range(fh, length), content_type=content_type, status=206,
    )
    response.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    response.headers["Content-Length"] = str(length)
    response.headers["Accept-Ranges"] = "bytes"
    return response


# --- WebM sarlavhasiga davomiylik yozish (sof Python, tashqi vositasiz) ------
#
# `RecordingUploadView` faylni bo'lak-bo'lak xom holda yozadi (qarang:
# proctoring.js) — MediaRecorder yozuv boshida umumiy davomiylikni bilmaydi,
# shuning uchun uni sarlavhaga yozmaydi. `_serve_video_range` bilan Range
# so'rovi ishlay boshlagach brauzer sakray oladi, LEKIN davomiylik hamon
# noma'lum: uni bilish uchun brauzer faylning katta qismini "termash" (skan
# qilish) orqali qidiradi — kichik faylda sezilmaydi, 100+ MB'da esa "juda
# uzoq ochiladi" bo'lib ko'rinadi.
#
# Yechim ffmpeg emas: xodim brauzeri yozuv necha soniya davom etganini
# ALLAQACHON aniq biladi (qarang: RecordingDurationView) — shuni faylning
# Matroska/EBML sarlavhasidagi tegishli joyga to'g'ridan-to'g'ri yozib
# qo'yamiz. Qayta kodlash yo'q, tashqi dastur yo'q — video/audio oqimining
# o'ziga BUTUNLAY tegilmaydi, faqat "Segment Information" elementiga bitta
# kichik (11 baytlik) "Duration" yozuvi qo'shiladi.
_WEBM_SEGMENT_INFO_ID = bytes.fromhex("1549a966")
_WEBM_TIMECODE_SCALE_ID = bytes.fromhex("2ad7b1")
_WEBM_DURATION_ID = bytes.fromhex("4489")


def _ebml_vint_length(first_byte):
    """EBML VINT (o'zgaruvchan uzunlikdagi butun son) necha baytdan iborat —
    birinchi baytdagi "marker" bit qaysi o'rinda turganidan aniqlanadi."""
    mask = 0x80
    length = 1
    while not (first_byte & mask):
        mask >>= 1
        length += 1
    return length


def _ebml_read_vint(data, offset):
    """(qiymat, uzunlik) — "marker" bit olib tashlanib o'qiladi (hajm/qiymat
    turidagi VINT uchun; ID turidagi VINT'da marker bit saqlanadi, lekin bu
    yerda ID'lar doim so'zma-so'z, tayyor baytlar sifatida qidiriladi)."""
    first = data[offset]
    length = _ebml_vint_length(first)
    value = first & (0xFF >> length)
    for i in range(1, length):
        value = (value << 8) | data[offset + i]
    return value, length


def _ebml_encode_vint(value, min_length=1):
    """Butun sonni EBML hajm-VINT'iga kodlaydi. `min_length` — imkon qadar
    ESKI uzunlikni saqlab qolish uchun (shunda faylning boshqa joylarini
    siljitmasdan, faqat shu bitta baytni almashtirish yetarli bo'ladi)."""
    length = min_length
    while value > (1 << (7 * length)) - 2:  # -2: hammasi 1 -> "noma'lum" degani
        length += 1
    return (value | (1 << (7 * length))).to_bytes(length, "big")


def _webm_find_segment_info(head):
    """Faylning boshidagi namunadan Segment Information elementini topadi.
    (info_id_offset, content_start, old_content_len, size_vint_len) yoki
    topilmasa None."""
    idx = head.find(_WEBM_SEGMENT_INFO_ID)
    if idx < 0:
        return None
    size_offset = idx + len(_WEBM_SEGMENT_INFO_ID)
    content_len, vint_len = _ebml_read_vint(head, size_offset)
    return idx, size_offset + vint_len, content_len, vint_len


def _webm_timecode_scale(info_content):
    """Segment Information tarkibidan TimecodeScale'ni (nanosekundda)
    o'qiydi. Topilmasa Matroska standart qiymati (1 000 000 ns = 1 ms)."""
    idx = info_content.find(_WEBM_TIMECODE_SCALE_ID)
    if idx < 0:
        return 1_000_000
    value_len, vint_len = _ebml_read_vint(info_content, idx + 3)
    start = idx + 3 + vint_len
    return int.from_bytes(info_content[start:start + value_len], "big")


def _webm_write_duration(path, duration_ms):
    """WebM faylining Segment Information elementiga Duration yozuvini
    QO'SHADI (video/audio baytlariga tegmasdan). `duration_ms` — xodim
    brauzeri o'lchagan haqiqiy yozuv davomiyligi.

    Segment "noma'lum hajm"da yozilgani uchun (MediaRecorder oqim sifatida
    yozadi) uni qayta o'lchashning hojati yo'q — faqat Segment Information
    o'zining hajm-VINT'ini yangilash kifoya. Fayl vaqtinchalik nusxaga
    ko'chiriladi (asl fayl faqat MUVAFFAQIYATLI yakunlangandagina almashadi),
    shuning uchun jarayon o'rtasida uzilib qolsa ham asl fayl saqlanib qoladi.

    (ok, xato_matni) qaytaradi."""
    try:
        with open(path, "rb") as f:
            head = f.read(65536)
    except OSError as exc:
        return False, str(exc)

    found = _webm_find_segment_info(head)
    if not found:
        return False, "Segment Information elementi topilmadi"
    info_id_offset, content_start, old_content_len, old_vint_len = found
    old_content = head[content_start:content_start + old_content_len]
    if _WEBM_DURATION_ID in old_content:
        return False, "Duration allaqachon mavjud"

    timecode_scale = _webm_timecode_scale(old_content)
    # Matroska Duration — "Segment Ticks" (TimecodeScale bo'laklarida) da
    # yoziladi: soniyalar emas. `duration_ms * 1e6` — nanosekundlarga
    # aylantiradi, shuni TimecodeScale'ga bo'lish esa "necha bo'lak" beradi.
    ticks = duration_ms * 1_000_000.0 / timecode_scale
    duration_payload = struct.pack(">d", ticks)  # Matroska Duration — float64
    duration_elem = _WEBM_DURATION_ID + _ebml_encode_vint(len(duration_payload)) + duration_payload

    new_content_len = old_content_len + len(duration_elem)
    new_size_vint = _ebml_encode_vint(new_content_len, min_length=old_vint_len)

    tmp_path = f"{path}.durfix.tmp"
    try:
        with open(path, "rb") as src, open(tmp_path, "wb") as dst:
            dst.write(src.read(info_id_offset + len(_WEBM_SEGMENT_INFO_ID)))
            src.read(old_vint_len)  # eski hajm-VINT — o'qib tashlab yuboriladi
            dst.write(new_size_vint)
            dst.write(src.read(old_content_len))  # eski tarkib — o'zgarishsiz
            dst.write(duration_elem)
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        os.replace(tmp_path, path)
        return True, ""
    except OSError as exc:
        return False, str(exc)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _ensure_recording_duration_fixed(recording, file_path):
    """Uzatishdan OLDIN chaqiriladi: kerak bo'lsa `_webm_write_duration`ni
    ishga tushiradi, keyin bir daqiqa ham qayta urinmaydi (`duration_fixed`).

    `duration_ms` hali kelmagan bo'lishi mumkin — bu funksiyani so'raydigan
    yo'l (`RecordingDurationView`) va videoni ochish deyarli bir vaqtda
    bo'ladi (test tugashi bilan), ba'zan admin biroz oldinroq ulguradi. Bu
    holatda bayroq QO'YILMAYDI — keyingi safar qiymat kelgan bo'lsa, o'shanda
    tuzatiladi."""
    if recording.duration_fixed or recording.duration_ms is None:
        return
    ok, err = _webm_write_duration(file_path, recording.duration_ms)
    if not ok:
        logger.warning("WebM davomiyligini yozib bo'lmadi (%s): %s", file_path, err)
    else:
        cache.delete(REC_SIZE_CACHE_KEY)  # fayl hajmi bir necha baytga o'zgardi
    Recording.objects.filter(pk=recording.pk).update(duration_fixed=True)


def _can_view_recordings(user):
    """Video yozuvlarni ko'rish huquqi — superuser yoki "Video yozuvlar" (recordings)
    ruxsati berilgan rol. Ro'yxatni ko'ra oladigan admingina faylni ham ocha oladi."""
    return bool(user and user.is_active and user.is_staff
                and (user.is_superuser or "recordings" in permissions_for(user)))


def media_recordings_view(request, path):
    """`/media/recordings/...` — video nazorat yozuvlari FAQAT "Video yozuvlar"
    ruxsati bor administratorga (yoki superuserga).

    Ilgari bu fayllar boshqa media (savol rasmlari) kabi hammaga ochiq edi,
    keyin esa istalgan admin tokeni bilan ochilardi — lekin ro'yxat "recordings"
    ruxsatini talab qilardi. Bu nomuvofiqlik edi: ruxsati yo'q admin ro'yxatni
    ko'rmasa ham, manzilni bilsa faylni ocha olardi. Endi fayl ham, ro'yxat ham
    bir xil "recordings" ruxsatini talab qiladi.

    Ikki yo'l bilan kelinadi: panel tokeni (`?token=` — <video> teg Authorization
    sarlavha qo'sha olmaydi) yoki /it-center sessiyasi."""
    session_user = getattr(request, "user", None)
    allowed = (
        (session_user is not None and session_user.is_authenticated
         and _can_view_recordings(session_user))
        or _can_view_recordings(_admin_user_from_request(request))
    )
    if allowed:
        # `safe_join` — `django.views.static.serve` bilan bir xil himoya:
        # `path` manzildan keladi, ya'ni "../.." kabi qatorlar bilan
        # `MEDIA_ROOT`dan tashqariga chiqishga urinish bo'lishi mumkin.
        try:
            full_path = safe_join(django_settings.MEDIA_ROOT / "recordings", path)
        except SuspiciousFileOperation:
            return HttpResponse(status=404)
        if not os.path.isfile(full_path):
            return HttpResponse(status=404)
        # `Recording.file` — "recordings/" prefiksi bilan (upload_to), `path`
        # esa shundan keyingi qism (qarang: bnpztest_api/urls.py).
        recording = Recording.objects.filter(file=f"recordings/{path}").first()
        if recording:
            _ensure_recording_duration_fixed(recording, full_path)
        return _serve_video_range(request, full_path)
    return HttpResponse("Video yozuvlar faqat ruxsati bor administratorlar uchun.", status=403)


def public_media_view(request, path):
    """Ochiq media — savol/variant rasmlari, oferta videosi (qarang: urls.py).

    Yo'l avval `django.views.static.serve` ning o'zi kabi normallashtiriladi;
    natija video yozuvlar papkasiga tushsa, so'rov ruxsat tekshiruvi bor
    `media_recordings_view` ga yuboriladi. Harflar katta-kichikligi hisobga
    olinmaydi: serverdagi disk — Windows papkasi, u harflarni farqlamaydi,
    `media/recordings/` marshruti esa farqlaydi. Usiz yozuvlar papkasiga shu
    ochiq marshrut orqali ham yetib borish mumkin edi."""
    normalized = posixpath.normpath(path).lstrip("/")
    top, _sep, rest = normalized.partition("/")
    if top.lower() == "recordings":
        return media_recordings_view(request, rest)
    return media_serve(request, path, document_root=django_settings.MEDIA_ROOT)


class AdminRecordingDeleteView(APIView):
    """Bitta video yozuvni o'chiradi — FAQAT superuser.

    Ataylab bittalab: "N kundan eskisini o'chirish" kabi ommaviy amal yo'q
    (`AdminRecordingsCleanupView` ga qarang) — bir bosishda butun arxivni yo'q
    qilish imkoniyati qoldirilmagan. Bu yerda superuser aynan qaysi yozuvni
    o'chirayotganini ko'rib turadi.

    Rolga berib bo'lmaydi: `IsSuperUser` — ya'ni oddiy administratorda bu
    imkoniyat "Video yozuvlar" bo'limi ochiq bo'lsa ham paydo bo'lmaydi."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]

    def delete(self, request, pk):
        rec = Recording.objects.filter(pk=pk).first()
        if not rec:
            return Response({"error": "Video yozuv topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        who = rec.employee_name or "—"
        what = rec.test_name or "—"
        when = timezone.localtime(rec.created).strftime("%d.%m.%Y %H:%M")
        name = rec.file.name
        # Fayl ham diskdan o'chadi — aks holda yozuv arxivdan yo'qolib, fayl
        # joyni egallab yotaveradi (aynan shu holat ilgari 78 ta "yetim" fayl
        # to'planishiga olib kelgan edi).
        rec.file.delete(save=False)
        rec.delete()
        cache.delete(REC_SIZE_CACHE_KEY)  # keshlangan disk hajmi yangilansin
        log_activity("admin", request.user.username, "recording_deleted",
                     f"Video yozuv o'chirildi: {who} — \"{what}\" ({when})",
                     {"file": name})
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminRecordingsBulkDeleteView(APIView):
    """Tanlangan video yozuvlarni o'chiradi — FAQAT superuser.

    Muhim farqi: bu yerda "shartga mos hammasini" emas, aynan MIJOZ TANLAGAN
    id'lar o'chadi. Ya'ni superuser ro'yxatda har bir yozuvni ko'rib, belgilab
    chiqadi — "N kundan eskisining hammasi" degan ko'r-ko'rona amal emas.
    Shu sabab bir bosishda kutilmaganda butun arxiv yo'qolib qolmaydi.

    Rolga berib bo'lmaydi (`IsSuperUser`)."""

    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]

    # Bir so'rovda o'chiriladigan yozuvlar chegarasi — tasodifan "hammasini"
    # yuborib qo'yishning oldini oladi va so'rov juda uzoq ketmaydi.
    MAX_PER_REQUEST = 200

    def post(self, request):
        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            return Response({"error": "O'chiriladigan yozuvlar tanlanmagan."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            ids = [int(x) for x in ids]
        except (TypeError, ValueError):
            return Response({"error": "Yozuv raqamlari noto'g'ri."}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > self.MAX_PER_REQUEST:
            return Response(
                {"error": f"Bir vaqtda ko'pi bilan {self.MAX_PER_REQUEST} ta yozuv o'chiriladi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = Recording.objects.filter(pk__in=ids)
        found = list(qs)
        if not found:
            return Response({"error": "Tanlangan yozuvlar topilmadi."}, status=status.HTTP_404_NOT_FOUND)

        # Tarixga nima o'chganini yozib qo'yamiz — keyin "qaysi video qani?"
        # degan savolga aniq javob bo'lishi uchun.
        details = [
            f"{r.employee_name or '—'} — \"{r.test_name or '—'}\" "
            f"({timezone.localtime(r.created):%d.%m.%Y %H:%M})"
            for r in found
        ]
        files = [r.file.name for r in found]
        for rec in found:
            # Fayl ham diskdan ketadi, aks holda yozuv arxivdan yo'qolib fayl
            # joyni egallab yotaveradi (ilgari 78 ta "yetim" fayl shunday paydo bo'lgan).
            rec.file.delete(save=False)
        count = len(found)
        qs.delete()
        cache.delete(REC_SIZE_CACHE_KEY)  # keshlangan disk hajmi yangilansin

        log_activity("admin", request.user.username, "recordings_deleted",
                     f"{count} ta video yozuv o'chirildi: " + "; ".join(details[:20])
                     + (" …" if count > 20 else ""),
                     {"count": count, "files": files})
        return Response({"deleted": count})


class AdminRecordingsCleanupView(APIView):
    """O'CHIRILDI: video yozuvlarni ommaviy o'chirish taqiqlangan.

    Ilgari bu endpoint N kundan eski yozuvlarni baza VA diskdan butunlay
    o'chirardi. Video nazorat yozuvi — qaytarib bo'lmaydigan dalil, shuning
    uchun uni panel orqali o'chirish umuman mumkin emas.

    Endpoint saqlab qolindi (o'chirilmadi), chunki eski panel ochiq turgan
    brauzerdan so'rov kelishi mumkin — bunday so'rov jimgina "bajarildi" deb
    emas, ochiq rad javobi bilan qaytarilishi kerak.

    Disk to'lib qolsa: fayllar `MEDIA_ROOT/recordings/YYYY/MM/DD/` da yotadi,
    ularni serverdan qo'lda (masalan tashqi diskka ko'chirib) arxivlash mumkin."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "recordings"

    def post(self, request):
        log_activity("admin", request.user.username, "recordings_cleanup_denied",
                     "Video yozuvlarni ommaviy o'chirishga urinish rad etildi")
        return Response(
            {"error": "Video yozuvlarni o'chirish taqiqlangan. Ular arxivda doimiy saqlanadi."},
            status=status.HTTP_403_FORBIDDEN,
        )


class AdminResultsCsvView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "results"

    def get(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="natijalar.csv"'
        response.write("﻿")  # Excelda kirill/lotin harflar to'g'ri ko'rinishi uchun BOM
        writer = csv.writer(response)
        writer.writerow(["Ism-familiya", "Lavozim (test)", "To'g'ri", "Jami", "Foiz", "Baho", "Natija", "Sana"])
        for r in Result.objects.defer("answers"):
            writer.writerow([
                r.full_name, r.test_name, r.correct, r.total, r.pct, r.grade,
                "O'tdi" if r.passed else "O'tmadi", r.created.strftime("%Y-%m-%d %H:%M"),
            ])
        return response

    def delete(self, request):
        """O'CHIRILDI: barcha natijalarni tozalash taqiqlangan.

        Natija — xodim topshirgan test dalili; uni bir tugma bilan yo'q qilish
        mumkin bo'lmasligi kerak. Endpoint saqlab qolindi, chunki eski panel
        ochiq turgan brauzerdan so'rov kelishi mumkin — u jimgina bajarilgandek
        emas, ochiq rad javobi bilan qaytarilishi kerak."""
        log_activity("admin", request.user.username, "results_clear_denied",
                     "Barcha natijalarni o'chirishga urinish rad etildi")
        return Response(
            {"error": "Natijalarni o'chirish taqiqlangan. Ular arxivda doimiy saqlanadi."},
            status=status.HTTP_403_FORBIDDEN,
        )


class AdminSettingsView(APIView):
    """Admin login/parolini faqat Django admin (dasturchi paneli, /it-center)
    orqali o'zgartirish mumkin — shu sabab bu yerda ommaviy oferta matni va
    videosi boshqariladi.

    Dastur nomi (`app_title`) BU YERDAN o'zgartirilmaydi: u o'zgarmas qiymat.
    Javobda qaytariladi (ilova uni o'qishi mumkin), lekin yozib bo'lmaydi —
    kerak bo'lsa dasturchi Django admin orqali o'zgartiradi."""

    def get(self, request):
        setting = Setting.load()
        return Response({
            "app_title": setting.app_title,
            "offer_text": setting.offer_text,
            "offer_video_url": request.build_absolute_uri(setting.offer_video.url) if setting.offer_video else None,
        })

    def patch(self, request):
        auth_result = AdminTokenAuthentication().authenticate(request)
        if not auth_result:
            return Response({"error": "Avtorizatsiya talab qilinadi."}, status=status.HTTP_401_UNAUTHORIZED)
        # GET hammaga ochiq (oferta matnini xodim ham o'qiydi), lekin YOZISH —
        # faqat "Sozlamalar" bo'limi ochiq administratorga. Ilgari bu tekshiruv
        # yo'q edi: istalgan roldagi administrator oferta matnini o'zgartira olardi.
        if not auth_result[0].has_perm_key("settings"):
            return Response({"error": "Bu bo'limga ruxsatingiz yo'q."}, status=status.HTTP_403_FORBIDDEN)

        setting = Setting.load()
        offer_text = request.data.get("offer_text")
        if offer_text is not None:
            setting.offer_text = offer_text.strip()
            setting.save()
            log_activity("admin", auth_result[0].username, "settings_updated",
                         "Ommaviy oferta matni o'zgartirildi")

        return Response({
            "app_title": setting.app_title,
            "offer_text": setting.offer_text,
            "offer_video_url": request.build_absolute_uri(setting.offer_video.url) if setting.offer_video else None,
        })


class AdminOfferVideoView(APIView):
    """Ommaviy oferta video instruksiyasini yuklash/o'chirish."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "settings"
    parser_classes = [MultiPartParser]

    def post(self, request):
        video = request.FILES.get("video")
        if not video:
            return Response({"error": "Video fayl yuborilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        setting = Setting.load()
        setting.offer_video = video
        setting.save(update_fields=["offer_video"])
        log_activity("admin", request.user.username, "settings_updated", "Ommaviy oferta videosi yuklandi")
        return Response({"offer_video_url": request.build_absolute_uri(setting.offer_video.url)})

    def delete(self, request):
        setting = Setting.load()
        setting.offer_video.delete(save=True)
        log_activity("admin", request.user.username, "settings_updated", "Ommaviy oferta videosi o'chirildi")
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminSeedDemoView(APIView):
    """Namuna (demo) ma'lumotlarni yuklash — FAQAT superuser.

    Bu ishchi bazaga test/savol/xodim yozuvlarini qo'shadi. Oddiy rol uchun
    bunday tugma xato bosilganda ishchi ro'yxatlarni namuna ma'lumot bilan
    ifloslantirardi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsSuperUser]

    def post(self, request):
        from django.core.management import call_command
        call_command("seed_demo")
        log_activity("admin", request.user.username, "demo_seeded", "Namuna ma'lumotlar yuklandi")
        return Response({"ok": True})


class AdminClearDataView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "settings"

    def post(self, request):
        """O'CHIRILDI: "barcha ma'lumotlarni tozalash" taqiqlangan.

        Bu endpoint bir so'rov bilan BARCHA natija, xodim va testlarni
        o'chirardi. Bir marta shu tugma tufayli haqiqiy testlar zaxirasiz
        yo'qolgan. Bunday ommaviy o'chirish uchun panelda o'rin yo'q —
        kerak bo'lsa har bir yozuv alohida, ko'rib chiqib o'chiriladi."""
        log_activity("admin", request.user.username, "data_clear_denied",
                     "Barcha ma'lumotlarni tozalashga urinish rad etildi")
        return Response(
            {"error": "Barcha ma'lumotlarni tozalash taqiqlangan."},
            status=status.HTTP_403_FORBIDDEN,
        )


# ---------------------------------------------------------------------------
# WebRTC signaling — jonli ekran ko'rish uchun (in-memory, seans ichida)
# ---------------------------------------------------------------------------

_live_lock = _threading.Lock()
_live_sessions = {}  # str(attempt_id) -> {offer, answer, emp_cands, adm_cands}

# "Admin ko'rmoqchi" belgisi shuncha soniyadan keyin o'z-o'zidan so'nadi.
#
# Ilgari bu oddiy True/False bayroq edi va uni O'CHIRADIGAN yagona yo'l —
# xodim brauzerining WebRTC taklifini yuborishi edi. Brauzer javob bermasa
# (kamera ruxsati yo'q, WebRTC ulanmadi, xodim allaqachon testni tugatgan),
# bayroq test oxirigacha YOQIQ qolardi.
#
# Buning narxi butun tizimga tushardi: `EmployeeLiveStatusView` "umuman
# kimdir kutilyaptimi?" deb tekshiradi, va BITTA osilib qolgan bayroq bu
# savolga doim "ha" deb javob berardi — natijada HAMMA xodimning so'rovi
# yana bazaga borardi. 20 kishilik sinovda aynan shu bo'ldi: 180-soniyada
# yoqilgan bayroq oxirigacha so'nmadi va 920 ta so'rovning hammasi bazaga
# ketdi (1.1 ms o'rniga 56 ms).
#
# Endi belgi "kimdir QACHONDIR so'ragan" emas, "OXIRGI 15 SONIYADA so'ragan"
# degan ma'noni bildiradi.
#
# 15 soniya tasodifiy tanlanmagan — u ikki tomondan chegaralangan:
#   • Admin oynasi ochiq turganda HAR 1 SONIYADA so'raydi (LiveViewModal.jsx),
#     ya'ni haqiqiy tomoshabin belgini doim yangilab turadi — bu tomondan
#     muddat qisqa bo'lsa ham xavf yo'q.
#   • Xodim brauzeri esa har 5 soniyada so'raydi (App.jsx, LIVE_STATUS_POLL_MS).
#     Muddat SHUNDAN katta bo'lishi SHART, aks holda xodim belgini umuman
#     ko'rmay qolib, jonli ekran ochilmasdi. 15 soniya — uch barobar zaxira.
_LIVE_WANT_TTL = 15


def _live_wants_view(sess, now=None):
    """Admin shu seansni HOZIR ko'rmoqchimi (muddati o'tmaganmi)?"""
    at = (sess or {}).get("admin_wants_view_at")
    if not at:
        return False
    return (now or time.monotonic()) - at < _LIVE_WANT_TTL


def _live_blank(wants_view=False):
    """Bo'sh signaling seansi."""
    return {
        "offer": None, "answer": None,
        "emp_cands": [], "adm_cands": [],
        "admin_wants_view_at": time.monotonic() if wants_view else None,
    }


def _int_param(value, default=0):
    """So'rov parametridagi butun son — buzuq qiymat ("abc") 500 emas,
    standart qiymatga tushadi."""
    try:
        return max(0, int(value or default))
    except (TypeError, ValueError):
        return default


def _live_finished(attempt_id):
    """Seans yakunlanganmi (yoki umuman mavjud emasmi)?

    Jonli ko'rish faqat DAVOM ETAYOTGAN test uchun ma'noga ega, shuning uchun
    yakunlangan seansning xotiradagi yozuvi ham shu yerda darhol tozalanadi.

    Bu savol kerak bo'lib qoldi, chunki "tugagan" holatni signaling ma'lumotining
    o'zidan ajratib bo'lmaydi: xodim yakunlaganda `_grade_and_store` xotiradagi
    seansni o'chiradi va admin tomoni uchun bu "xodim hali offer yubormagan"
    bilan bir xil ko'rinardi. Admin esa muzlab qolgan videoni va "Ulanish
    uzildi, qayta urinmoqda…" yozuvini ko'rardi — holbuki hech narsa uzilmagan,
    test oddiy tugagan edi.

    Bazaga so'rov ketishi bu yerda muammo emas: bu yo'lni faqat ochiq turgan
    admin oynasi so'raydi. Xodimlar tomonidagi ko'p chaqiriladigan yo'l —
    `EmployeeLiveStatusView` — bazaga tegmasligicha qolyapti."""
    attempt = Attempt.objects.filter(pk=attempt_id).only("id", "completed").first()
    if attempt is not None and not attempt.completed:
        return False
    with _live_lock:
        _live_sessions.pop(str(attempt_id), None)
    return True


def _live_get(attempt_id):
    return _live_sessions.get(str(attempt_id))


def _live_init(attempt_id):
    key = str(attempt_id)
    with _live_lock:
        _live_sessions[key] = _live_blank()
        return _live_sessions[key]


class EmployeeLiveOfferView(APIView):
    """Xodim RTCPeerConnection offer'ini yuboradi (test boshlanganida)."""

    def post(self, request):
        token = request.data.get("token")
        offer = request.data.get("offer")
        attempt = _attempt_by_token(token, completed=False)
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        sess = _live_get(attempt.id) or _live_init(attempt.id)
        with _live_lock:
            # Yangi offer — yangi RTCPeerConnection (yangi ICE ufrag/pwd) degani,
            # shu sabab eski javob/kandidatlar endi mos kelmaydi va butunlay
            # tozalanishi kerak (aks holda admin eski, endi noto'g'ri kandidatlarni
            # qo'shishga urinib, ICE hech qachon ulanmay qolishi mumkin).
            sess["offer"] = offer
            sess["answer"] = None
            sess["emp_cands"] = []
            sess["adm_cands"] = []
            sess["admin_wants_view_at"] = None  # Xodim javob berdi — kutish tugadi
        return Response({"ok": True})


class EmployeeLiveSignalView(APIView):
    """Xodim ICE candidate yuboradi (POST) yoki admin javob/candidate'larini oladi (GET)."""

    def post(self, request):
        token = request.data.get("token")
        candidate = request.data.get("candidate")
        attempt = _attempt_by_token(token, completed=False)
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        sess = _live_get(attempt.id) or _live_init(attempt.id)
        with _live_lock:
            if candidate:
                sess["emp_cands"].append(candidate)
        return Response({"ok": True})

    def get(self, request):
        token = request.query_params.get("token")
        after = _int_param(request.query_params.get("after"))
        attempt = _attempt_by_token(token, completed=False)
        if not attempt:
            return Response({"error": "Seans topilmadi."}, status=status.HTTP_400_BAD_REQUEST)
        sess = _live_get(attempt.id)
        if not sess:
            return Response({"answer": None, "candidates": [], "total": 0})
        with _live_lock:
            return Response({
                "answer": sess["answer"],
                "candidates": sess["adm_cands"][after:],
                "total": len(sess["adm_cands"]),
            })


class EmployeeLiveStatusView(APIView):
    """Xodim admin ko'rish so'rovini tekshiradi (polling).

    Bu — butun tizimdagi ENG KO'P chaqiriladigan endpoint: test topshirayotgan
    har bir xodimning brauzeri uni muntazam so'rab turadi. Shu sababli u
    iloji boricha arzon bo'lishi kerak.

    Ilgari har chaqiruvda bazadan seans qidirilardi. O'lchangan: baza bilan
    51.6 ms, bazasiz 1.0 ms — ya'ni so'rovning DEYARLI HAMMASI baza ulanishiga
    ketardi (tashqi Postgres'ga yangi ulanish ochish ~50 ms turadi va
    `runserver` uni qayta ishlata olmaydi, qarang: settings.py CONN_MAX_AGE).
    20 xodimda bu sekundiga ~7 ta keraksiz ulanish degani edi, va javob
    deyarli har doim "yo'q" bo'lardi.

    Endi savol teskari qo'yiladi. Mijoz TOKEN yuboradi, xotiradagi jadval esa
    seans raqami bo'yicha tuzilgan — tokendan raqamni topish uchun baza kerak.
    Lekin agar UMUMAN hech kim tomosha qilmayotgan bo'lsa, kimligini
    aniqlashning ham hojati yo'q: javob baribir "yo'q". Shu tekshiruv
    xotirada, bazaga tegmasdan bajariladi va odatdagi holatni qamrab oladi.

    Bazaga faqat admin haqiqatan kimnidir ko'rmoqchi bo'lganda boriladi — bu
    esa kamdan-kam va qisqa muddatli holat."""

    def get(self, request):
        # Hech kim kutilmayotgan bo'lsa — bazaga tegmaymiz.
        with _live_lock:
            now = time.monotonic()
            anyone_wanted = any(_live_wants_view(s, now) for s in _live_sessions.values())
        if not anyone_wanted:
            return Response({"admin_wants_view": False})

        token = request.query_params.get("token")
        attempt = _attempt_by_token(token, completed=False)
        if not attempt:
            return Response({"admin_wants_view": False})
        sess = _live_get(attempt.id)
        return Response({"admin_wants_view": _live_wants_view(sess)})


class AdminLiveOfferView(APIView):
    """Admin xodimning SDP offer'ini oladi; so'rovning o'zi xodimga signal beradi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "active"

    def get(self, request, attempt_id):
        key = str(attempt_id)

        # Yakunlangan seansga ulanishning ma'nosi yo'q — quyidagi shoxlarga
        # umuman tushmaymiz. Tekshiruv aynan BIRINCHI turadi: pastdagi kod
        # `_live_sessions` ga yangi yozuv qo'shadi, `attempt_id` esa manzildan
        # keladi va hech qayerda tasdiqlanmagan.
        if _live_finished(attempt_id):
            return Response({"offer": None, "finished": True})

        with _live_lock:
            sess = _live_sessions.get(key)
            if sess and sess.get("answer"):
                # Oldingi sessiya tugagan — yangi ulanish uchun tozalaymiz
                _live_sessions[key] = _live_blank(wants_view=True)
                return Response({"offer": None, "finished": False})
            elif sess is None:
                _live_sessions[key] = _live_blank(wants_view=True)
                return Response({"offer": None, "finished": False})
            elif sess.get("offer"):
                # Offer allaqachon tayyor — shuni qaytaramiz. "admin_wants_view"ni
                # qayta True qilib qo'ymaymiz: aks holda xodim tomonidagi polling
                # buni "admin yana ko'rishni xohlayapti" deb tushunib, hali ICE
                # tugallanmagan ulanishni har necha soniyada qayta-qayta buzib,
                # qaytadan boshlab yuboraverardi — natijada ulanish hech qachon
                # "connected" holatiga yetib bormasdi.
                return Response({"offer": sess["offer"], "finished": False})
            else:
                # Xodim hali offer yubormagan — kutayotganimizni bildiramiz.
                # Vaqt YANGILANADI: admin oynasi ochiq turganda bu har soniyada
                # takrorlanadi, ya'ni belgi tirik qoladi. Oyna yopilishi bilan
                # yangilanish to'xtaydi va belgi 15 soniyada o'z-o'zidan so'nadi.
                sess["admin_wants_view_at"] = time.monotonic()
                return Response({"offer": None, "finished": False})


class AdminLiveStatusView(APIView):
    """Seans hali davom etyaptimi? `{"finished": true/false}`.

    Admin oynasi ulangandan KEYIN shu endpointni so'rab turadi va `finished`
    kelishi bilan jonli ko'rishni to'xtatadi.

    Nega alohida endpoint kerak — `AdminLiveOfferView` ni takroran so'rab
    bo'lmaydi: admin javob (`answer`) yuborganidan keyin u birinchi shoxga
    tushadi va "oldingi ulanish tugagan" deb seansni TOZALAB, `admin_wants_view`
    ni qayta yoqadi. Xodim tomonidagi polling buni "admin yana ko'rmoqchi" deb
    tushunib, ishlab turgan ulanishni uzib, qaytadan boshlab yuborardi.

    Shu sababli bu yerda hech qanday yon ta'sir yo'q: faqat o'qiydi (yakunlangan
    seansning xotiradagi qoldig'ini tozalashdan tashqari)."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "active"

    def get(self, request, attempt_id):
        return Response({"finished": _live_finished(attempt_id)})


class AdminLiveAnswerView(APIView):
    """Admin SDP answer'ini yuboradi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "active"

    def post(self, request, attempt_id):
        answer = request.data.get("answer")
        sess = _live_get(attempt_id) or _live_init(attempt_id)
        with _live_lock:
            sess["answer"] = answer
        return Response({"ok": True})


class AdminLiveSignalView(APIView):
    """Admin ICE candidate yuboradi (POST) yoki xodim candidate'larini oladi (GET)."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdmin]
    required_permission = "active"

    def post(self, request, attempt_id):
        candidate = request.data.get("candidate")
        sess = _live_get(attempt_id) or _live_init(attempt_id)
        with _live_lock:
            if candidate:
                sess["adm_cands"].append(candidate)
        return Response({"ok": True})

    def get(self, request, attempt_id):
        after = _int_param(request.query_params.get("after"))
        sess = _live_get(attempt_id)
        if not sess:
            return Response({"candidates": [], "total": 0})
        with _live_lock:
            return Response({
                "candidates": sess["emp_cands"][after:],
                "total": len(sess["emp_cands"]),
            })
