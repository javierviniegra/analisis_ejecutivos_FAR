-- ============================================================
-- Read-only database user for Central de Reportes
-- ============================================================
-- Central de Reportes only READS its report sources. Until now it used the
-- Wansoft pipeline's own account (wansoftuser, ALL PRIVILEGES on `wansoft`),
-- which after the 2026-10-01 cutover is the pipeline's WRITE user. This file
-- creates a dedicated account with SELECT only, as the data access guide asks
-- of every consumer (Wansoft repo: docs/data-access-guide/).
--
--   central_reportes -> SELECT on the documented tables of `wansoft`
--                       SELECT on the 5 tables of `presupuestos_ap` it reads
--
-- Run as root on the database machine (phpMyAdmin > SQL), at the 2026-10-01
-- cutover AFTER the migration has created the analytics/dimension tables in
-- `wansoft` (MariaDB refuses a table-level GRANT on a table that does not
-- exist yet). This project never runs it by itself: production changes are
-- run by the owner.
--
-- BEFORE RUNNING:
--   * Replace CHANGE_ME with a long random password. Never commit it: put it
--     only in config/.env (WANSOFT_DB_USER / WANSOFT_DB_PASSWORD and
--     PRESUPUESTOS_DB_USER / PRESUPUESTOS_DB_PASSWORD, see .env.example).
--   * '%' accepts any address. When the production app machine is fixed,
--     replace it with that machine's IP (and the dev PC's, if needed).
--
-- Limits (protect the production database used by the pipeline, Power BI and
-- ControlPresupuestos_AP):
--   MAX_USER_CONNECTIONS 4   at most 4 simultaneous sessions
--   MAX_STATEMENT_TIME 300   any query is killed after 5 minutes (the app
--                            already cuts each statement at 120 s on its side)
-- ============================================================

CREATE USER IF NOT EXISTS 'central_reportes'@'%' IDENTIFIED BY 'CHANGE_ME'
    WITH MAX_USER_CONNECTIONS 4 MAX_STATEMENT_TIME 300;

-- ---------------- wansoft: sales and cash closing (commercial report) ----------------
GRANT SELECT ON `wansoft`.`getallordenesbyday_new_venta`        TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`getallordenesbyday_new_detalleventa` TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`getallordenesbyday_new_pago`         TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`getallordenesbyday_new_modificador`  TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`getglobalcashclosing`                TO 'central_reportes'@'%';

-- ---------------- wansoft: costs (monthly executive report, next) ----------------
GRANT SELECT ON `wansoft`.`costeomensual`                       TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`costeomensual_semanapyq`             TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`gettotalcostbydate`                  TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`getexpenses_factura`                 TO 'central_reportes'@'%';
-- cost routing per branch (which days are on Odoo cost): the pipeline's published
-- table, and the two tables of the fallback rules used while it did not exist
GRANT SELECT ON `wansoft`.`costs_source_by_company`             TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`odoo_company_migration_policy`       TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`costs_odoo_switch`                   TO 'central_reportes'@'%';

-- ---------------- wansoft: unified purchases/inventory and dimensions (after the migration) ----------------
GRANT SELECT ON `wansoft`.`analytics_purchase_order_lines`               TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`analytics_purchase_orders`                    TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`analytics_purchase_daily_company_product`     TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`analytics_inventory_current_product_location` TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`analytics_inventory_balance`                  TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`analytics_company_domain_coverage`            TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`dim_company_analytical`                       TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`dim_product`                                  TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`dim_vendor`                                   TO 'central_reportes'@'%';
GRANT SELECT ON `wansoft`.`dim_time`                                     TO 'central_reportes'@'%';

-- ---------------- presupuestos_ap: Costo de Ventas budget vs real ----------------
GRANT SELECT ON `presupuestos_ap`.`presupuestos_sucursal`   TO 'central_reportes'@'%';
GRANT SELECT ON `presupuestos_ap`.`presupuestos_categoria`  TO 'central_reportes'@'%';
GRANT SELECT ON `presupuestos_ap`.`presupuestos_tipogasto`  TO 'central_reportes'@'%';
GRANT SELECT ON `presupuestos_ap`.`presupuestos_presupuesto` TO 'central_reportes'@'%';
GRANT SELECT ON `presupuestos_ap`.`presupuestos_gastoreal`  TO 'central_reportes'@'%';

-- ---------------- VERIFY ----------------
SHOW GRANTS FOR 'central_reportes'@'%';

-- Then, from the app (dev PC or app machine), with the new user in config/.env:
--   python manage.py verificar_fuentes
-- must end with every line PASS.

-- ---------------- REVOKE (if ever needed) ----------------
-- DROP USER 'central_reportes'@'%';
