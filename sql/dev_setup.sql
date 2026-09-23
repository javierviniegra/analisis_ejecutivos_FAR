-- Analisis Ejecutivos -- DEV database setup (local XAMPP MariaDB).
--
-- Creates this app's OWN database and a dedicated user that can only touch it.
-- Run once as a privileged user (root). Idempotent: safe to re-run.
--
--   C:\xampp\mysql\bin\mysql.exe -u root -p < sql\dev_setup.sql
--
-- BEFORE running: change the password below (and use the same one in
-- config/.env as EJECUTIVOS_DB_PASSWORD_DEV). Do not commit a real password
-- back into this file.

CREATE DATABASE IF NOT EXISTS analisis_ejecutivos_dev
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'ejecutivos_dev'@'localhost' IDENTIFIED BY 'CAMBIA_ESTA_CLAVE';

-- Django needs to create/alter tables in its own database (migrations) and
-- create a test database (`test_analisis_ejecutivos_dev`) when running tests.
GRANT ALL PRIVILEGES ON analisis_ejecutivos_dev.* TO 'ejecutivos_dev'@'localhost';
GRANT ALL PRIVILEGES ON `test\_analisis_ejecutivos_dev`.* TO 'ejecutivos_dev'@'localhost';

FLUSH PRIVILEGES;

SELECT 'OK: analisis_ejecutivos_dev listo' AS resultado;
