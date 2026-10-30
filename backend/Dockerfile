FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# `--insecure`: DEBUG=0 bo'lsa ham /static (Django admin, /it-center) fayllarini
# uzatishda davom etadi. Bu bayroq faqat statika uchun — DEBUG holatiga ta'sir qilmaydi.
CMD ["sh", "-c", "python manage.py migrate && python manage.py runserver 0.0.0.0:8000 --insecure"]
