"""One-off e-mail previews ("Enviar por correo"): the generated files and the
e-mail data are kept on disk (logs/previas/) until the user sends them, so
what is sent is exactly what was previewed -- nothing is generated twice.
A preview belongs to the user who made it and expires after VIGENCIA."""

import pickle
import secrets
import time
from pathlib import Path

from django.conf import settings

VIGENCIA = 2 * 3600  # seconds


def _carpeta() -> Path:
    carpeta = Path(settings.LOGS_DIR) / "previas"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _limpiar():
    limite = time.time() - VIGENCIA
    for ruta in _carpeta().glob("*.previa"):
        if ruta.stat().st_mtime < limite:
            ruta.unlink(missing_ok=True)


def guardar(usuario_id: int, datos: dict) -> str:
    _limpiar()
    token = secrets.token_urlsafe(16)
    (_carpeta() / f"{token}.previa").write_bytes(pickle.dumps({"usuario_id": usuario_id, **datos}))
    return token


def _ruta(token: str) -> Path | None:
    if not token.replace("-", "").replace("_", "").isalnum():
        return None
    return _carpeta() / f"{token}.previa"


def cargar(token: str, usuario_id: int) -> dict | None:
    """The preview, or None when it does not exist, expired or is someone else's."""
    ruta = _ruta(token)
    if ruta is None or not ruta.exists() or ruta.stat().st_mtime < time.time() - VIGENCIA:
        return None
    datos = pickle.loads(ruta.read_bytes())  # written by this app only (guardar)
    return datos if datos.get("usuario_id") == usuario_id else None


def borrar(token: str):
    ruta = _ruta(token)
    if ruta is not None:
        ruta.unlink(missing_ok=True)
