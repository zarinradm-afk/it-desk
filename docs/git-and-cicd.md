# ساختار Git و CI/CD

## Root Repository

Root فقط هماهنگی پروژه، مستندات، Overmind، Deploy و نسخهٔ Submoduleها را نگه می‌دارد.

## Submodules

```bash
git submodule add <frontend-repository> frontend
git submodule add <backend-repository> backend
git submodule update --init --recursive
```

## شاخه‌ها و محیط‌ها

- `develop`: توسعه و CI پایه
- `staging`: استقرار آزمایشی
- `main`: نسخهٔ production با تأیید دستی

مقادیر محیطی و کلیدهای دسترسی باید در تنظیمات امن GitHub نگهداری شوند و هرگز در Git یا خروجی Workflow چاپ نشوند.
