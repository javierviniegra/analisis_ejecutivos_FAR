"""Read-only connections to the report data sources.

Reports only READ from these systems. Every connection is opened with
`SET SESSION TRANSACTION READ ONLY`, so even a coding mistake cannot write.
Credentials come from config/.env (see config/.env.example); the `_DEV`
variables are used when ENV=dev. In production the configured accounts must
also be SELECT-only at the database level (defence in depth).
"""

import os
from contextlib import contextmanager

import MySQLdb
from django.conf import settings


def _variable(prefijo: str, nombre: str, defecto: str | None = None) -> str | None:
    sufijo = "_DEV" if settings.ENV == "dev" else ""
    return os.getenv(f"{prefijo}_{nombre}{sufijo}", defecto)


@contextmanager
def _abrir(prefijo: str):
    host = _variable(prefijo, "HOST")
    base = _variable(prefijo, "NAME")
    if not host or not base:
        raise RuntimeError(f"{prefijo}_HOST/{prefijo}_NAME are not configured in config/.env")
    conexion = MySQLdb.connect(
        host=host,
        port=int(_variable(prefijo, "PORT", "3306") or 3306),
        user=_variable(prefijo, "USER"),
        passwd=_variable(prefijo, "PASSWORD") or "",
        db=base,
        charset="utf8mb4",
        connect_timeout=15,
    )
    try:
        cursor = conexion.cursor()
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        yield cursor
    finally:
        conexion.close()


def abrir_wansoft():
    """Cursor on the Wansoft warehouse (sales, cash closing, order detail)."""
    return _abrir("WANSOFT_DB")


def abrir_presupuestos():
    """Cursor on the ControlPresupuestos_AP database (budgets, real spend)."""
    return _abrir("PRESUPUESTOS_DB")
