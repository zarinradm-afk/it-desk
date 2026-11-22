# معماری هدف IT Desk

این سند ساختار استاندارد پیشنهادی تیم را ثبت می‌کند.

## وضعیت فعلی

- Backend: FastAPI و SQLAlchemy داخل Root Repository
- Frontend: Jinja و CSS/JavaScript داخل `app/templates` و `app/static`
- اجرای محلی: Docker Compose
- CI: GitHub Actions برای تست Python و ساخت Docker image

## معماری هدف

```text
it-desk/
├── docs/                 # معرفی، اهداف، نیازمندی‌ها و تصمیم‌های معماری
├── overmind/             # اجرای محلی با Overmind و Docker
├── deploy/               # استقرار و عملیات سرور
├── frontend/             # Git Submodule: React + shadcn/ui
└── backend/              # Git Submodule: Django + Django REST Framework
```

Root Repository فقط مالک هماهنگی پروژه، مستندات، اجرای محلی، استقرار و نسخهٔ Submoduleها است.

## اختلاف‌های لازم برای مهاجرت

1. انتقال API و مدل‌های فعلی از FastAPI/SQLAlchemy به Django/DRF.
2. انتقال صفحات Jinja به React و جایگزینی رابط با shadcn/ui.
3. ایجاد دو Repository مستقل و اتصال آن‌ها به‌عنوان Submodule.
4. تعریف Workflowهای جدا برای backend و frontend.
5. تعریف محیط‌های development، staging و production در GitHub.
6. افزودن Workflow دستی Deploy با تأیید محیط production.

تا پایان مهاجرت، نسخهٔ فعلی قابل اجرا به‌عنوان مرجع حفظ می‌شود.
