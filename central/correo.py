"""Development e-mail backend: every message is saved as an .eml file (opens
in Outlook with its attachments) under settings.EMAIL_FILE_PATH, and nothing
is sent. Chosen with CORREO_MODO=archivo (the default in dev)."""

import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class EmlBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        carpeta = Path(settings.EMAIL_FILE_PATH)
        carpeta.mkdir(parents=True, exist_ok=True)
        for i, mensaje in enumerate(email_messages):
            para = re.sub(r"[^\w.@-]", "_", ",".join(mensaje.to))[:80]
            ruta = carpeta / f"{datetime.now():%Y%m%d_%H%M%S}_{i:02d}_{para}.eml"
            ruta.write_bytes(mensaje.message().as_bytes())
        return len(email_messages)
