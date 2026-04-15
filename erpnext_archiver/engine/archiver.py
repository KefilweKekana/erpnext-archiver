# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Core archiver engine.

Moves rows from live ERPNext tables into ``tab<DocType> Archive`` tables
for a given fiscal year and company.  Designed for v14, v15, and v16.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from erpnext_archiver.engine.schema_manager import (
    ensure_archive_table,
    get_archive_table_name,
    get_child_doctypes,
)

# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def archive_fiscal_year(fiscal_year, company):
    """Archive all configured DocTypes for *fiscal_year* / *company*.

    Returns a summary dict with per-doctype results.
    """
    _check_permission()
    settings = frappe.get_single("Archive Settings")

    if not settings.enabled:
        frappe.throw(_("Archiving is disabled in Archive Settings."))

    fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
    from_date = fy_doc.year_start_date
    to_date = fy_doc.year_end_date

    # --- Safety checks ---
    if settings.require_period_closing_voucher:
        _assert_period_closed(fiscal_year, company)

    if settings.backup_before_archive:
        _take_backup()

    # --- Phase 1: ensure all archive tables exist (DDL — auto-committed) ---
    active_rows = [r for r in settings.doctypes_to_archive if r.is_active]
    for row in active_rows:
        ensure_archive_table(row.doctype_name)
        for child_dt in get_child_doctypes(row.doctype_name):
            ensure_archive_table(child_dt)

    # --- Phase 2: archive each doctype (DML — per-doctype transactions) ---
    results = []
    for row in active_rows:
        result = _archive_single_doctype(
            row.doctype_name,
            row.date_field,
            from_date,
            to_date,
            company,
            fiscal_year,
        )
        results.append(result)

    # --- Phase 3: optimise live tables (DDL) ---
    for row in active_rows:
        _optimise_table(row.doctype_name)
        for child_dt in get_child_doctypes(row.doctype_name):
            _optimise_table(child_dt)

    return results


# ---------------------------------------------------------------------------
#  Single DocType archive
# ---------------------------------------------------------------------------

def _archive_single_doctype(doctype, date_field, from_date, to_date, company, fiscal_year):
    """Archive one doctype plus its child tables.  Each doctype is its own
    transaction — a failure here does not roll back other doctypes."""

    log = frappe.new_doc("Archive Log")
    log.fiscal_year = fiscal_year
    log.company = company
    log.doctype_name = doctype
    log.date_field = date_field
    log.from_date = from_date
    log.to_date = to_date
    log.archive_table_name = get_archive_table_name(doctype)
    log.status = "In Progress"
    log.rows_archived = 0
    log.rows_child_archived = 0
    log.error_message = ""

    try:
        child_count = _archive_children(doctype, date_field, from_date, to_date, company)
        parent_count = _copy_and_delete(doctype, date_field, from_date, to_date, company)

        log.rows_archived = parent_count
        log.rows_child_archived = child_count
        log.status = "Completed"
        log.archived_on = now_datetime()

        frappe.db.commit()

    except Exception as exc:
        frappe.db.rollback()
        log.status = "Failed"
        log.error_message = str(exc)[:1400]

    # Save log in its own mini-transaction so failures are always recorded.
    try:
        log.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()

    return {
        "doctype": doctype,
        "status": log.status,
        "rows_archived": log.rows_archived,
        "rows_child_archived": log.rows_child_archived,
        "error": log.error_message,
    }


# ---------------------------------------------------------------------------
#  Copy + delete helpers
# ---------------------------------------------------------------------------

def _copy_and_delete(doctype, date_field, from_date, to_date, company):
    """INSERT into archive, verify count, DELETE from live.

    The caller is responsible for COMMIT / ROLLBACK.
    """
    live = f"tab{doctype}"
    arch = get_archive_table_name(doctype)
    meta = frappe.get_meta(doctype)
    has_company = meta.has_field("company")

    where, params = _build_date_where(date_field, from_date, to_date, company, has_company)

    # Count
    count = frappe.db.sql(
        "SELECT COUNT(*) FROM `{live}` {where}".format(live=_e(live), where=where),
        params,
    )[0][0]

    if count == 0:
        return 0

    # Copy
    frappe.db.sql(
        "INSERT INTO `{arch}` SELECT * FROM `{live}` {where}".format(
            arch=_e(arch), live=_e(live), where=where
        ),
        params,
    )

    # Verify
    arch_count = frappe.db.sql(
        "SELECT COUNT(*) FROM `{arch}` {where}".format(arch=_e(arch), where=where),
        params,
    )[0][0]

    if arch_count < count:
        frappe.throw(
            _("Row count mismatch for {0}: expected >= {1}, got {2}").format(
                doctype, count, arch_count
            )
        )

    # Delete
    frappe.db.sql(
        "DELETE FROM `{live}` {where}".format(live=_e(live), where=where),
        params,
    )

    return count


def _archive_children(parent_doctype, date_field, from_date, to_date, company):
    """Archive every child table linked to *parent_doctype*.

    Uses a sub-query against the **live** parent table (which still has the
    rows at this point — children are archived first).
    """
    meta = frappe.get_meta(parent_doctype)
    has_company = meta.has_field("company")
    parent_live = f"tab{parent_doctype}"
    total = 0

    for child_dt in get_child_doctypes(parent_doctype):
        child_live = f"tab{child_dt}"
        child_arch = get_archive_table_name(child_dt)

        # Build the sub-select for parent names
        parent_where, parent_params = _build_date_where(
            date_field, from_date, to_date, company, has_company
        )

        # Count
        count_sql = (
            "SELECT COUNT(*) FROM `{child}` "
            "WHERE `parent` IN (SELECT `name` FROM `{parent}` {parent_where}) "
            "AND `parenttype` = %s"
        ).format(
            child=_e(child_live),
            parent=_e(parent_live),
            parent_where=parent_where,
        )
        count_params = list(parent_params) + [parent_doctype]
        count = frappe.db.sql(count_sql, count_params)[0][0]

        if count == 0:
            continue

        # Copy children to archive
        insert_sql = (
            "INSERT INTO `{arch}` "
            "SELECT c.* FROM `{child}` c "
            "WHERE c.`parent` IN (SELECT `name` FROM `{parent}` {parent_where}) "
            "AND c.`parenttype` = %s"
        ).format(
            arch=_e(child_arch),
            child=_e(child_live),
            parent=_e(parent_live),
            parent_where=parent_where,
        )
        frappe.db.sql(insert_sql, count_params)

        # Delete children from live
        delete_sql = (
            "DELETE c FROM `{child}` c "
            "WHERE c.`parent` IN (SELECT `name` FROM `{parent}` {parent_where}) "
            "AND c.`parenttype` = %s"
        ).format(
            child=_e(child_live),
            parent=_e(parent_live),
            parent_where=parent_where,
        )
        frappe.db.sql(delete_sql, count_params)

        total += count

    return total


# ---------------------------------------------------------------------------
#  Shared utilities
# ---------------------------------------------------------------------------

def _build_date_where(date_field, from_date, to_date, company, has_company):
    """Return ``(where_clause, params_tuple)`` for the date-range + company filter."""
    import re

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", date_field):
        frappe.throw(_("Invalid date field name: {0}").format(date_field))

    parts = ["`{df}` BETWEEN %s AND %s".format(df=date_field)]
    params = [from_date, to_date]

    if has_company:
        parts.append("`company` = %s")
        params.append(company)

    return "WHERE " + " AND ".join(parts), tuple(params)


def _e(name):
    """Sanitise SQL identifier (same as schema_manager._esc)."""
    import re

    sanitised = re.sub(r"[^a-zA-Z0-9_ ]", "", name)
    if sanitised != name:
        frappe.throw(_("Invalid identifier: {0}").format(name))
    return sanitised


def _check_permission():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Manager can perform archive operations."))


def _assert_period_closed(fiscal_year, company):
    """Ensure a submitted Period Closing Voucher exists for the fiscal year."""
    pcv = frappe.db.exists(
        "Period Closing Voucher",
        {"fiscal_year": fiscal_year, "company": company, "docstatus": 1},
    )
    if not pcv:
        frappe.throw(
            _(
                "Period Closing Voucher has not been submitted for {0} / {1}. "
                "Please close the fiscal year first."
            ).format(fiscal_year, company)
        )


def _take_backup():
    """Trigger a Frappe site backup.  Best-effort — does not block archiving."""
    try:
        from frappe.utils.backups import BackupGenerator

        # Frappe convention: db_name is used as both the database name and
        # the MariaDB user.  Positional order: (db_name, user, password).
        backup = BackupGenerator(
            db_name=frappe.conf.db_name,
            user=frappe.conf.db_name,
            password=frappe.conf.db_password,
            db_host=frappe.conf.db_host or "localhost",
            db_port=frappe.conf.db_port,
            db_type=getattr(frappe.conf, "db_type", "mariadb"),
        )
        backup.get_backup()
    except Exception:
        frappe.log_error(title="Archive backup failed")
        frappe.msgprint(
            _("Warning: automatic backup failed. Check Error Log. Proceeding with archive."),
            alert=True,
        )


def _optimise_table(doctype):
    """Run OPTIMIZE TABLE to reclaim space.  Silently ignored on failure."""
    table = f"tab{doctype}"
    try:
        sql = "OPTIMIZE TABLE `{}`".format(_e(table))
        if hasattr(frappe.db, "sql_ddl"):
            frappe.db.sql_ddl(sql)
        else:
            frappe.db.sql(sql)
    except Exception:
        pass
