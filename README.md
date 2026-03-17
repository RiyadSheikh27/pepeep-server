# 🚗 Pepeep — Backend API

Django REST Framework + PostgreSQL backend for the Pepeep car-based restaurant pickup platform.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?style=flat&logo=django&logoColor=white)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat&logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat&logo=redis&logoColor=white)](https://redis.io)

---

## Stack

| | |
|---|---|
| API | Django 4.2 + DRF 3.15 |
| Database | PostgreSQL 15 + PostGIS |
| Cache & Queue | Redis 7 + Celery |
| Real-time | Django Channels (WebSocket) |
| Storage | AWS S3 |
| Payments | Tiller + Apple Pay |

---

## Quick Start

```bash
git clone https://github.com/RiyadSheikh27/pepeep-server.git
cd pepeep-server
cp .env.example .env
docker-compose up --build
```

API runs at `http://localhost:8000` — docs at `/api/docs/`.

---

## Environment Variables

```env
SECRET_KEY=
DB_NAME=pepeep_db
DB_USER=postgres
DB_PASSWORD=
REDIS_URL=redis://localhost:6379/0
AWS_STORAGE_BUCKET_NAME=
TILLER_API_KEY=
FIREBASE_CREDENTIALS_PATH=firebase-service-account.json
DEFAULT_COMMISSION_RATE=0.15
```

---

## Key Features

- Phone + OTP authentication with JWT
- Restaurant discovery by GPS radius (PostGIS)
- Order lifecycle with scheduled pickups
- QR-based dual-verification delivery
- Real-time WebSocket alerts for staff
- Automated commission & payout management

---

## Commands

```bash
python manage.py migrate          # apply migrations
python manage.py createsuperuser  # create admin user
python manage.py test             # run tests
celery -A config worker -l info   # start task worker
```

---

## License

Private — all rights reserved.
