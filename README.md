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
DEBUG=
ALLOWED_HOSTS=

REDIS_URL=
JWT_ACCESS_MINUTES=
JWT_REFRESH_DAYS=

BASE_URL=

# Google Maps API Key (for distance matrix API - optional)
GOOGLE_MAPS_API_KEY=""

STRIPE_SECRET_KEY=sk_test_xxxxxxxxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxxxxxx
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
daphne -b 0.0.0.0 -p 8070 config.asgi:application #Start Server

```

---

## License

Private — all rights reserved.


