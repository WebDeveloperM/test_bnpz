FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Tizim paketlari (apt) ATAYLAB o'rnatilmaydi. Ilgari bu yerda `fonts-dejavu-core`
# bor edi, lekin uni ishlatadigan kod yo'q (protokol HTML, PDF'ni brauzer
# chop etadi). Shu keraksiz qadam serverda build'ni yiqitgan: tarmoqdagi
# proksi Debian paketlar ro'yxatining eski nusxasini berib, apt "Hash Sum
# mismatch" bilan to'xtagan. Endi build faqat Docker Hub va PyPI'ga (HTTPS)
# bog'liq. Kelajakda apt kerak bo'lsa — manbalarni https:// ga o'tkazing.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# HTTP server — `serve.py` (waitress, bitta jarayon, cheklangan oqimlar havzasi).
# Nega runserver emasligi va eski serverga qanday qaytish — o'sha faylda.
# `exec`: server PID 1 bo'ladi va `docker stop` signalini o'zi oladi (ilgari
# `sh` uni e'tiborsiz qoldirar, to'xtatish har safar 10 soniya kutardi).
CMD ["sh", "-c", "python manage.py migrate && exec python serve.py"]
