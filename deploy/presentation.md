# ارائه بیرونی پروژه

## تونل موقت از سیستم توسعه

برای یک جلسه کوتاه، سرویس را روی سیستم خودتان اجرا کنید و پورت 8000 را با یک تونل HTTPS منتشر کنید:

```powershell
docker compose up --build -d
cloudflared tunnel --url http://localhost:8000
```

آدرس HTTPS چاپ‌شده را برای ارائه‌کننده بفرستید. برای دمو از داده نمایشی استفاده کنید و رمز اولیه چاپ‌شده در لاگ را بعد از ورود تغییر دهید.

## VPS و دامنه

1. روی VPS لینوکس Docker نصب کنید و پروژه را با Git دریافت کنید.
2. `.env` را از `.env.example` بسازید و `CSRF_SECRET_HEX` و `ALLOWED_HOSTS` را تنظیم کنید.
3. گواهی TLS را در `deploy/certs/` قرار دهید و نام دامنه را در `deploy/nginx.conf` عوض کنید.
4. اجرا کنید:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

5. پورت 443 را باز کنید و `/health` را بررسی کنید.

## سناریوی ارائه

- `Dockerfile` و Compose توسعه/تولید
- `pytest -q` و CI در `.github/workflows/ci.yml`
- FastAPI، SQLAlchemy، migration و ساختار تست
- ورود، ثبت تیکت، تغییر وضعیت، داشبورد، دارایی و Excel

هیچ رمز، فایل `.env`، دیتابیس واقعی یا داده سازمانی را در Git یا لینک عمومی قرار ندهید.
