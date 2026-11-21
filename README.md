# IT Desk

سامانه داخلی تیکتینگ و مدیریت دارایی IT با FastAPI، SQLAlchemy، Jinja2/HTMX و SQLite.

## اجرای سریع

```powershell
docker compose up --build
```

سپس `http://localhost:8000/health` را بررسی کنید. برنامه در اولین اجرا یک کاربر مدیر می‌سازد و رمز اولیه را در لاگ کانتینر چاپ می‌کند؛ بعد از ورود آن را تغییر دهید.

## تست و کیفیت

```powershell
python -m compileall -q app tests
pytest -q
```

CI در `.github/workflows/ci.yml` همین بررسی‌ها و ساخت Docker image را روی push و pull request اجرا می‌کند.

## ارائه بیرونی

راهنمای تونل موقت، VPS، دامنه و TLS در [deploy/presentation.md](deploy/presentation.md) است. برای تولید از Compose و Nginx موجود در `docker-compose.prod.yml` استفاده کنید.

## Development

Run the development stack with:

```powershell
docker compose up --build
```

## Production behind Nginx

Copy `.env.example` to `.env`, set `CSRF_SECRET_HEX` and `ALLOWED_HOSTS`, place TLS certificates in `deploy/certs`, and update `deploy/nginx.conf` with the real `.ir` domain.

Then run:

```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

Before schema changes or deployments, create a database backup:

```powershell
.\deploy\backup.ps1
```

The production compose file disables reload, keeps only `data` as a writable application volume, and enables secure cookies.
