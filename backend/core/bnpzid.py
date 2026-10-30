"""BnpzId (employee_service) bilan ishlashning YAGONA yo'li.

Ilgari BnpzId'ga uch joydan mustaqil murojaat qilinardi: `sync_employees`
komandasi, admin qidiruvi (`_bnpz_fetch`) va ro'yxatga qo'shishdagi rasm
yuklash (`_fetch_face_embedding`). Har biri manzilni, sarlavhani, `verify`
bayrog'ini va timeout'ni qaytadan yasardi. Oqibatlari:

* timeout'lar mos kelmasdi — 12 / 15 / 20 / 30 soniya, hech qanday sababsiz;
* hech qayerda qayta urinish yo'q edi, ya'ni bir soniyalik tarmoq uzilishi
  butun ommaviy sinxronizatsiyani to'xtatardi;
* javob shakli ikki joyda ikki xil qayta ishlanardi — komanda ham massiv,
  ham `{"results": [...]}` konvertini tushunardi, qidiruv esa massiv kelsa
  `AttributeError` bilan yiqilib, admin panelga 500 qaytarardi;
* API kaliti rasm manziliga ham yuborilardi (rasm kalitsiz ham ochilsa-da).

Endi bularning hammasi shu yerda, bitta joyda.

DIQQAT — bu modulda faqat `requests.get` bor va shundayligicha qolishi kerak.
BnpzTest BnpzId ma'lumotining iste'molchisi, manbasi emas; sababi
`AdminSyncedEmployeePhotoUploadView` izohida batafsil yozilgan.
"""

import logging
import time
from urllib.parse import urlsplit

import requests
import urllib3
from django.conf import settings

logger = logging.getLogger(__name__)

# Self-signed sertifikat bilan ishlaganda `requests` har so'rovda ogohlantirish
# chiqaradi. Uni o'chirish BIR MARTA, modul yuklanganda bo'ladi — ilgari bu
# eskirgan `requests.packages.urllib3` yo'li orqali, har so'rovdan oldin uch
# joyda chaqirilardi. Faqat AYNAN shu ogohlantirish o'chiriladi: qolgan TLS
# ogohlantirishlari kelajakda ham ko'rinib tursin.
if not settings.EMPLOYEE_SERVICE_VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Timeout'lar. Uchta qiymat ataylab: ular BAJARILADIGAN ISHGA qarab farq qiladi,
# oldingidek — kim qaysi joyda yozgan bo'lsa, shunga qarab emas.
TIMEOUT = 15          # oddiy JSON so'rovi (qidiruv, bitta xodim, katalog)
TIMEOUT_IMAGE = 20    # rasm — o'rtacha 1.6 MB, sekinroq keladi
TIMEOUT_BULK = 30     # 200 tadan sahifa — faqat `sync_employees` uchun

# Qayta urinishlar orasidagi kutish. Uzunroq pauza foyda bermaydi: bu yerda
# gap qayta ko'tarilayotgan servisni kutishda emas, bir lahzalik uzilishda.
RETRY_PAUSE = 0.3


class BnpzIdError(Exception):
    """BnpzId javob bermadi yoki tushunarsiz javob qaytardi.

    Faqat ommaviy (`sync_employees`) yo'lida ko'tariladi — u yerda yarim
    yangilangan holatni jimgina qoldirgandan ko'ra, ochiq to'xtagan ma'qul.
    Admin paneliga xizmat qiladigan funksiyalar esa hech qachon istisno
    ko'tarmaydi: ular `(natija, ok)` juftligini qaytaradi, chunki u yerda
    "topilmadi" bilan "hozir qidirib bo'lmayapti" bir-biridan farq qilishi
    va ikkalasi ham 500'siz ko'rsatilishi kerak.
    """


def base_url():
    return settings.EMPLOYEE_SERVICE_BASE_URL.rstrip("/")


def _headers():
    return {"X-Employee-Service-Key": settings.EMPLOYEE_SERVICE_API_KEY}


def _is_bnpzid_host(url):
    """Manzil BnpzId'ning O'ZInikimi?

    API kalitini begona hostga yubormaslik uchun kerak. Bugun rasmlar
    BnpzId'ning o'zida yotibdi, lekin `base_image_url` javobdan keladi —
    ya'ni manzilni BnpzId hal qiladi, biz emas. Rasmlar CDN'ga yoki alohida
    fayl serveriga ko'chirilsa, kalit o'sha yoqqa ketib qolmasligi kerak.
    """
    try:
        target = urlsplit(url or "")
        own = urlsplit(settings.EMPLOYEE_SERVICE_BASE_URL)
    except ValueError:
        return False
    if not target.hostname:
        return False
    return (target.hostname, target.port) == (own.hostname, own.port)


def _get(url, params=None, headers=None, timeout=TIMEOUT, retries=1):
    """Bitta GET so'rov. Javob obyekti yoki None (so'rov umuman bormadi).

    Qayta urinish FAQAT ulanish xatosida bo'ladi. Sabab vaqtga bog'liq:
    ulanish xatosi darhol qaytadi, shuning uchun ikkinchi urinish tekin;
    o'qish yoki ulanish timeout'i esa butun `timeout`ni yeb bo'lgan bo'ladi,
    va uni takrorlash admin panelida kutish vaqtini ikki barobar qilardi.
    HTTP xato kodlari (403, 404, 500) ham takrorlanmaydi — ular tarmoq
    uzilishi emas, javobning o'zi.
    """
    attempt = 0
    while True:
        try:
            return requests.get(
                url,
                params=params,
                headers=_headers() if headers is None else headers,
                verify=settings.EMPLOYEE_SERVICE_VERIFY_SSL,
                timeout=timeout,
            )
        except requests.Timeout as exc:
            logger.warning("BnpzId javob bermadi (timeout %ss): %s — %s", timeout, url, exc)
            return None
        except requests.ConnectionError as exc:
            if attempt >= retries:
                logger.warning("BnpzId'ga ulanib bo'lmadi: %s — %s", url, exc)
                return None
            attempt += 1
            time.sleep(RETRY_PAUSE)
        except requests.RequestException as exc:
            logger.warning("BnpzId so'rovi bajarilmadi: %s — %s", url, exc)
            return None


def get_json(path, params=None, timeout=TIMEOUT, retries=1):
    """(data, ok). `path` to'liq manzil ham bo'lishi mumkin (`next` havolasi)."""
    url = path if path.startswith("http") else f"{base_url()}/{path.lstrip('/')}"
    resp = _get(url, params=params, timeout=timeout, retries=retries)
    if resp is None:
        return None, False
    if resp.status_code != 200:
        logger.warning("BnpzId %s → HTTP %s", url, resp.status_code)
        return None, False
    try:
        return resp.json(), True
    except ValueError:
        logger.warning("BnpzId %s tushunarsiz (JSON bo'lmagan) javob qaytardi", url)
        return None, False


def results_of(data):
    """Javobdan yozuvlar ro'yxatini ajratadi.

    BnpzId ikki xil shaklda javob berishi mumkin: sahifalangan
    `{"count", "next", "previous", "results"}` konverti va (`no_pagination=true`
    bilan) oddiy massiv. Ilgari qidiruv yo'li faqat birinchisini bilar va
    massiv kelganda `AttributeError` bilan 500 qaytarardi.
    """
    if isinstance(data, dict):
        results = data.get("results")
        return results if isinstance(results, list) else []
    if isinstance(data, list):
        return data
    return []


def image_url_of(item):
    """Yozuvdagi rasm manzili — BnpzId ikki xil maydon nomi ishlatishi mumkin."""
    if not isinstance(item, dict):
        return ""
    return item.get("base_image_url") or item.get("base_image") or ""


def count_of(data, items):
    """BnpzId topgan yozuvlarning UMUMIY soni — sahifada nechtasi kelganidan
    qat'i nazar. Sahifalanmagan javobda `count` bo'lmaydi, o'shanda kelgan
    yozuvlar soni umumiy son bilan bir xil bo'ladi."""
    if isinstance(data, dict):
        count = data.get("count")
        if isinstance(count, int):
            return count
    return len(items)


def search_employees(params, timeout=TIMEOUT, retries=1):
    """Xodimlarni filtr bo'yicha qidiradi. (items, total, ok) qaytaradi.

    `total` — BnpzId topgan UMUMIY son; u `len(items)` dan katta bo'lsa, javob
    sahifa chegarasida kesilgan. Chaqiruvchi buni foydalanuvchiga aytishi
    kerak: jimgina kesilgan ro'yxat "bunday xodim yo'q" bo'lib ko'rinadi.

    ok=False bo'lsa BnpzId javob bermadi (yoki javobi tushunarsiz)."""
    data, ok = get_json("employees/", params=params, timeout=timeout, retries=retries)
    if not ok:
        return [], 0, False
    items = results_of(data)
    return items, count_of(data, items), True


def list_departments(timeout=TIMEOUT, retries=1):
    """Sexlar (bo'limlar) katalogi. (items, ok) qaytaradi.

    Bu endpoint sahifalanmagan — oddiy massiv, 34 ta yozuv, ~4.7 KB."""
    data, ok = get_json("departments/", timeout=timeout, retries=retries)
    if not ok:
        return [], False
    return results_of(data), True


def department_names(items):
    """Katalogdan sex nomlari — BnpzId belgilagan TARTIBDA (`sort_order`).

    Tartib manbadan olinadi: sexlar alifbo bo'yicha emas, ishlab chiqarish
    ketma-ketligi bo'yicha nomerlangan, va admin ularni aynan shu tartibda
    ko'rishni kutadi. `sort_order` yo'q yozuv oxiriga tushadi."""
    rows = [i for i in items
            if isinstance(i, dict) and (i.get("name") or "").strip()]
    rows.sort(key=lambda i: (
        i["sort_order"] if isinstance(i.get("sort_order"), int) else 10 ** 6,
        i.get("name") or "",
    ))
    seen, out = set(), []
    for i in rows:
        name = i["name"].strip()
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def get_employee(slug, timeout=TIMEOUT, retries=1):
    """Bitta xodimning JORIY ma'lumoti. (item, ok) qaytaradi."""
    data, ok = get_json(f"employees/{slug}/", timeout=timeout, retries=retries)
    if not ok or not isinstance(data, dict):
        return None, False
    return data, True


def iter_employees(page_size=200, timeout=TIMEOUT_BULK):
    """BARCHA xodimlarni sahifama-sahifa qaytaradi (generator).

    Faqat `sync_employees` uchun. Sahifa kelmasa `BnpzIdError` ko'tariladi:
    yarim ro'yxatni "hammasi shu" deb qabul qilish — mahalliy nusxani
    jimgina eskirtirib qo'yish demakdir.
    """
    url = f"{base_url()}/employees/"
    params = {"page_size": page_size}
    while url:
        data, ok = get_json(url, params=params, timeout=timeout)
        if not ok:
            raise BnpzIdError(f"BnpzId sahifani bermadi: {url}")
        for item in results_of(data):
            yield item
        # `next` — allaqachon to'liq manzil (page_size ham ichida), shuning
        # uchun keyingi so'rovda `params` qayta yuborilmaydi.
        url = data.get("next") if isinstance(data, dict) else None
        params = None


def fetch_image(url, timeout=TIMEOUT_IMAGE, retries=1):
    """Rasmni yuklab, baytlarini qaytaradi. Topilmasa/kelmasa — None.

    API kaliti FAQAT rasm BnpzId'ning o'z manzilida bo'lganda qo'shiladi
    (qarang: `_is_bnpzid_host`). O'lchandi: rasm kalitsiz ham ochiladi, ya'ni
    kalit u yerda aslida kerak ham emas.
    """
    if not url:
        return None
    headers = _headers() if _is_bnpzid_host(url) else {}
    resp = _get(url, headers=headers, timeout=timeout, retries=retries)
    if resp is None:
        return None
    if resp.status_code != 200:
        logger.warning("BnpzId rasmni bermadi: %s → HTTP %s", url, resp.status_code)
        return None
    return resp.content
