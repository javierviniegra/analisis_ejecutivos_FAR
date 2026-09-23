"""Create this app's DEV database and restricted user, reading EVERYTHING from config/.env.

No credentials live in this file or anywhere else in git. Needed in config/.env
(see config/.env.example):

  EJECUTIVOS_DB_HOST_DEV / _PORT_DEV      where MySQL runs
  EJECUTIVOS_DB_NAME_DEV                  database to create
  EJECUTIVOS_DB_USER_DEV / _PASSWORD_DEV  the app's restricted user to create
  EJECUTIVOS_DB_ADMIN_USER_DEV / _ADMIN_PASSWORD_DEV
                                          privileged account, used ONLY here

Idempotent: safe to re-run (the app user's password is re-applied, so changing
it in .env and re-running rotates it).

Run from the project root:  .venv\\Scripts\\python.exe scripts\\setup_dev_db.py
"""

import os
import re
import sys
from pathlib import Path

import MySQLdb
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "config" / ".env")

REQUIRED = [
    "EJECUTIVOS_DB_HOST_DEV",
    "EJECUTIVOS_DB_NAME_DEV",
    "EJECUTIVOS_DB_USER_DEV",
    "EJECUTIVOS_DB_PASSWORD_DEV",
    "EJECUTIVOS_DB_ADMIN_USER_DEV",
    "EJECUTIVOS_DB_ADMIN_PASSWORD_DEV",
]
IDENT = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def main():
    if os.getenv("ENV", "prod").lower() != "dev":
        sys.exit("Refusing to run: ENV is not 'dev' in config/.env.")
    missing = [k for k in REQUIRED if not os.getenv(k)]
    if missing:
        sys.exit("Missing in config/.env: " + ", ".join(missing))

    host = os.environ["EJECUTIVOS_DB_HOST_DEV"]
    port = int(os.getenv("EJECUTIVOS_DB_PORT_DEV", "3306"))
    db = os.environ["EJECUTIVOS_DB_NAME_DEV"]
    user = os.environ["EJECUTIVOS_DB_USER_DEV"]
    password = os.environ["EJECUTIVOS_DB_PASSWORD_DEV"]
    for label, value in (("database name", db), ("user name", user)):
        if not IDENT.match(value):
            sys.exit(f"Invalid {label}: only letters, digits and _ are allowed.")
    if host not in ("localhost", "127.0.0.1"):
        sys.exit("Refusing to run: this script only prepares a LOCAL dev database.")

    conn = MySQLdb.connect(
        host=host,
        port=port,
        user=os.environ["EJECUTIVOS_DB_ADMIN_USER_DEV"],
        passwd=os.environ["EJECUTIVOS_DB_ADMIN_PASSWORD_DEV"],
    )
    cur = conn.cursor()
    cur.execute(
        f"CREATE DATABASE IF NOT EXISTS `{db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    # Identifiers are validated above; the password goes through parameter binding.
    cur.execute(f"CREATE USER IF NOT EXISTS '{user}'@'localhost' IDENTIFIED BY %s", (password,))
    cur.execute(f"ALTER USER '{user}'@'localhost' IDENTIFIED BY %s", (password,))
    cur.execute(f"GRANT ALL PRIVILEGES ON `{db}`.* TO '{user}'@'localhost'")
    # Django creates `test_<db>` when running tests.
    cur.execute(f"GRANT ALL PRIVILEGES ON `test\\_{db}`.* TO '{user}'@'localhost'")
    cur.execute("FLUSH PRIVILEGES")
    conn.close()
    print(f"OK: database `{db}` and user `{user}` ready on {host}:{port}.")


if __name__ == "__main__":
    main()
