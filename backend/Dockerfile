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

# HTTP server — `serve.py` (waitress, bitta jarayon, cheklangan oqimlar havzasi).
# Nega runserver emasligi va eski serverga qanday qaytish — o'sha faylda.
# `exec`: server PID 1 bo'ladi va `docker stop` signalini o'zi oladi (ilgari
# `sh` uni e'tiborsiz qoldirar, to'xtatish har safar 10 soniya kutardi).
CMD ["sh", "-c", "python manage.py migrate && exec python serve.py"]
