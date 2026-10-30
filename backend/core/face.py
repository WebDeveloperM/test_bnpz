"""Yuzni aniqlash va taqqoslash — OpenCV'ning tayyor YuNet (aniqlash) va
SFace (identifikatsiya uchun 128-o'lchamli "embedding" chiqaradigan) modellari
asosida. Ikkalasi ham to'liq mahalliy (internetga ulanmasdan) ishlaydi —
model fayllari core/face_models/ papkasida loyihaga qo'shib qo'yilgan.

Xodim identifikatsiyasi 1:N qidiruv talab qiladi (kamera oldida turgan
noma'lum xodimni 3000+ xodim orasidan topish), employee_service esa faqat
1:1 tekshirish (allaqachon ma'lum xodimga nisbatan) taqdim etadi va bizning
"faqat o'qish" kalitimiz bilan bu ham yopiq — shu sabab taqqoslashni o'zimiz,
mahalliy ravishda amalga oshiramiz: har bir xodim rasmidan oldindan
"embedding" hisoblab bazada saqlaymiz (SyncedEmployee.face_embedding),
keyin kameradan olingan suratni shular bilan taqqoslaymiz.
"""

import threading

import numpy as np
import cv2
from pathlib import Path
from django.conf import settings

_MODELS_DIR = Path(__file__).resolve().parent / "face_models"
_DETECTOR_PATH = str(_MODELS_DIR / "yunet.onnx")
_RECOGNIZER_PATH = str(_MODELS_DIR / "sface.onnx")

_detector = None
_recognizer = None

# OpenCV'ning YuNet va SFace obyektlari ichida `cv::dnn::Net` yotadi va u OQIM
# UCHUN XAVFSIZ EMAS: bitta Net'da bir vaqtda ikkita hisob-kitob ishga tushirilsa,
# natija buziladi. Bu yerdagi `_detector`/`_recognizer` esa butun jarayon uchun
# BITTA umumiy obyekt — ya'ni ular hech qachon parallel ishlatilmasligi kerak.
#
# Django'ning runserver'i har bir so'rovni alohida oqimda bajaradi, shu sabab
# ikki xodim bir vaqtda kirsa ikkala oqim shu obyektlarga birga tegardi. Amalda
# bu shunday ko'rinardi (o'lchangan, 6 oqim): 3 ta so'rov
# "(-215:Assertion failed) buf.shape() == m.shape()" bilan yiqilardi, yana 3 tasi
# esa BOSHQA oqimning rasmidan hisoblangan, ya'ni butunlay noto'g'ri embedding
# qaytarardi — xodim jimgina noto'g'ri tanilardi.
#
# Shuning uchun barcha hisob-kitob shu qulf ostida, navbat bilan bajariladi.
# Qulf `_get_detector()`/`_get_recognizer()` ni ham qamrab oladi — aks holda
# birinchi so'rovlar 38 MB'lik modelni bir vaqtda bir necha marta yuklardi.
_lock = threading.Lock()

# Detektorga beriladigan rasmning eng katta tomoni. BnpzId'dagi xodim rasmlari
# 3000x4000 (12 MP) bo'lib, YuNet bunday o'lchamda yuzni UMUMAN topa olmaydi va
# har bir rasmga ~1.8 soniya sarflaydi; kichraytirilgach esa 0.12 soniyada topadi.
# Kameradan kelgan surat allaqachon bundan kichik, ya'ni kirish oqimiga ta'sir yo'q.
#
# Bu kichraytirish qulf bilan birga ishlaydi: qulf so'rovlarni navbatga qo'yadi,
# kichraytirish esa navbatni tez o'tkazadi (20 xodim uchun ~36 soniya emas, ~3 soniya).
_MAX_DETECT_SIDE = 1280


def _downscale(img):
    """Rasmni detektor uchun qulay o'lchamga keltiradi (nisbati saqlanadi)."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= _MAX_DETECT_SIDE:
        return img
    scale = _MAX_DETECT_SIDE / longest
    return cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)


def _get_detector():
    global _detector
    if _detector is None:
        _detector = cv2.FaceDetectorYN.create(_DETECTOR_PATH, "", (320, 320), score_threshold=0.7)
    return _detector


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        _recognizer = cv2.FaceRecognizerSF.create(_RECOGNIZER_PATH, "")
    return _recognizer


def _decode(image_bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def extract_embedding(image_bytes):
    """Rasm baytlaridan eng katta (asosiy) yuzning 128-o'lchamli embedding'ini
    qaytaradi. Yuz topilmasa None qaytaradi."""
    img = _decode(image_bytes)
    if img is None:
        return None
    img = _downscale(img)

    # HAMMASI bitta qulf ostida: `setInputSize` va `detect` ikki alohida amal
    # bo'lgani uchun ular orasida boshqa oqim o'z o'lchamini yozib qo'ysa,
    # detektor boshqa rasmning o'lchami bilan ishlab ketardi. `alignCrop` va
    # `feature` ham o'sha umumiy recognizer'ni ishlatadi, shuning uchun ular
    # ham shu blok ichida turadi.
    with _lock:
        detector = _get_detector()
        h, w = img.shape[:2]
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        if faces is None or len(faces) == 0:
            return None

        # Eng katta (yaqin turgan) yuzni tanlaymiz.
        faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
        face = faces[0]

        recognizer = _get_recognizer()
        aligned = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned)

    return feature.flatten().astype(np.float32).tolist()


def compare(embedding_a, embedding_b):
    """Ikki embedding orasidagi cosine o'xshashlikni qaytaradi (0..1, katta = o'xshash).

    `match()` ham o'sha umumiy recognizer obyektini ishlatadi, shuning uchun u
    ham qulf ostida bajariladi. `find_best_match` esa alohida qulf olmaydi —
    u shu funksiyani chaqiradi va qulf har chaqiruvda qisqa vaqtga olinadi,
    ya'ni uzoq ro'yxat boshqa xodimlarning kirishini to'sib qo'ymaydi."""
    with _lock:
        recognizer = _get_recognizer()
        a = np.array(embedding_a, dtype=np.float32).reshape(1, -1)
        b = np.array(embedding_b, dtype=np.float32).reshape(1, -1)
        return float(recognizer.match(a, b, cv2.FaceRecognizerSF_FR_COSINE))


def find_best_match(embedding, candidates):
    """candidates: [(key, embedding), ...] ro'yxati orasidan eng mos kelganini topadi.
    Qaytaradi: (key, score) yoki hech narsa topilmasa (None, 0.0)."""
    best_key, best_score = None, 0.0
    for key, cand_embedding in candidates:
        if not cand_embedding:
            continue
        score = compare(embedding, cand_embedding)
        if score > best_score:
            best_key, best_score = key, score
    return best_key, best_score


def is_match(score):
    return score >= settings.FACE_MATCH_THRESHOLD
