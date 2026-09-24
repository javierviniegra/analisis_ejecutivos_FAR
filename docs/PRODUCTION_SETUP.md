# Production setup

Same topology as ControlPresupuestos_AP (see that repo's `deploy/PRODUCTION_SETUP.md`), three machines:

- **App machine** (the VM that also hosts ControlPresupuestos_AP): runs this app with **Waitress** on port **8040**; **WhiteNoise** serves static files.
- **Database server**: hosts this app's own MySQL database (a new, separate database and a dedicated MySQL user with rights only on it).
- **Proxy server** (Apache, port `8088`): maps the URL prefix `/central_reportes/` to the app machine.

> Status: written ahead of deployment (Phase 7). The values marked TODO must be confirmed against the real machines before the first deploy. Nothing here has been executed yet.

## 1. Database (on the database server)

Create an empty database (utf8mb4) and a dedicated user restricted to it. Never reuse the credentials of another app.

## 2. `.env` on the app machine

Copy `config/.env.example` to `config/.env` and set at least:

```
ENV=prod
DJANGO_SECRET_KEY=<generate a new one, never reuse dev's>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=<app machine address>,<proxy address>
DJANGO_FORCE_SCRIPT_NAME=/central_reportes
DJANGO_CSRF_TRUSTED_ORIGINS=http://<proxy address>:8088
EJECUTIVOS_DB_HOST=<database server>
EJECUTIVOS_DB_USER=...
EJECUTIVOS_DB_PASSWORD=...
EJECUTIVOS_DB_NAME=...
```

`DJANGO_SECURE_COOKIES=true` only once HTTPS is in front of the proxy (with plain http the browser would drop secure cookies and login would stop working).

## 3. Reverse proxy (Apache on the proxy server)

Inside the existing `<VirtualHost *:8088>`, next to the other apps:

```
ProxyPass /central_reportes/ http://<app machine>:8040/
ProxyPassReverse /central_reportes/ http://<app machine>:8040/
```

Also add the redirect for the no-trailing-slash form (`/central_reportes` -> `/central_reportes/`) exactly as done for `/presupuestos_ap`. Restart Apache. `DJANGO_FORCE_SCRIPT_NAME` is required: Apache strips the prefix before forwarding, so without it every link Django generates would come out unprefixed and 404 through the proxy.

## 4. Run

```
python manage.py migrate
python manage.py crear_perfiles
python manage.py collectstatic --noinput
waitress-serve --port=8040 config.wsgi:application
```

A deploy/update script (like ControlPresupuestos_AP's `update.ps1`) will be added in Phase 7.
