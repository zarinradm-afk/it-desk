# اجرای محلی با Overmind و Docker

پیش‌نیازها: Docker Desktop، Overmind و Git.

اجرای معماری هدف:

```bash
overmind start
```

تا زمان پایان مهاجرت، سرویس فعلی با Docker Compose اجرا می‌شود:

```bash
docker compose up --build
```

تنظیمات محیطی باید از فایل `.env` خوانده شوند و در Git Commit نشوند.
