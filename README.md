# Jheliz

Plataforma de venta de **streaming y licencias** para Perú — dominio `jhelizservicestv.es`.

Construida con Django 5, Tailwind (CDN) y PostgreSQL (SQLite en local).

## Stack

- Python 3.12 + Django 5
- Custom User con roles `cliente` / `distribuidor` / `admin`
- Tailwind oscuro estilo KiosTeam
- Mercado Pago Perú (pendiente PR #2)
- WhiteNoise + gunicorn para producción

## Setup rápido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_catalog
python manage.py createsuperuser
python manage.py runserver
```

Luego abre http://127.0.0.1:8000/ y el admin en http://127.0.0.1:8000/jheliz-admin/

## Roadmap

- **PR #1 (este)** — Semana 1: foundation, modelos, admin con carga de stock, catálogo público, auth.
- **PR #2** — Semana 2: checkout con Mercado Pago Perú, entrega manual con datos del cliente, emails, recordatorio de vencimiento.
- **PR #3** — Semana 3: tickets, Telegram + WhatsApp, deploy a producción con dominio.
