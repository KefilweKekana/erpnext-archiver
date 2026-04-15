# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Restore engine — moves rows from archive tables back into live tables.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from erpnext_archiver.engine.schema_manager import (
    archive_table_exists,
    get_archive_table_name,
    get_child_doctypes,
)

# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------

def restore_fiscal_year(fiscal_year, company):
    """Restore all archived data for *fiscal_year* / *company* back to live tables.

    Returns a summary list of per-doctype results.
    """
    _check_permission()

    settings = frappe.get_single("Archive Settings")
    fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
    from_date = fy_doc.year_start_date
    to_date = fy_doc.year_end_date

    active_rows = [r for r in settings.doctypes_to_archive if r.is_active]
    results = []

    for row in active_rows:
        result = _restore_single_doctype(
            row.doctype_name, row.date_field, from_date, to_date, company, fiscal_year
        )
        results.append(result)

    return results


# ---------------------------------------------------------------------------
#  Single DocType restore
# ---------------------------------------------------------------------------

def _restore_single_doctype(doctype, date_field, from_date, to_date, company, fiscal_year):
    """Move rows from the archive table back into the live table."""
    if not archive_table_exists(doctype):
        return {"doctype": doctype, "status": "Skipped", "rows_restored": 0, "error": ""}

    try:
        # Restore children FIRST (parent names are still in the archive table
        # at this point, so the sub-query can find them).  Then restore parent.
        child_count = _restore_children(doctype, date_field, from_date, to_date, company)
        parent_count = _copy_back(doctype, date_field, from_date, to_date, company)

        # Update Archive Log status
        _update_archive_log(fiscal_year, company, doctype, "Restored")

        frappe.db.commit()

        return {
            "doctype": doctype,
            "status": "Restored",
            "rows_restored": parent_count,
            "child_rows_restored": child_count,
            "error": "",
        }
    except Exception as exc:
        frappe.db.rollback()
        return {"doctype": doctype, "status": "Failed", "rows_restored": 0, "error": str(exc)[:500]}


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _copy_back(doctype, date_field, from_date, to_date, company):
    """INSERT from archive back into live, then DELETE from archive."""
    import re

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", date_field):
        frappe.throw(_("Invalid date field name"))

    live = f"tab{doctype}"
    arch = get_archive_table_name(doctype)
    meta = frappe.get_meta(doctype)
    has_company = meta.has_field("company")

    where, params = _build_where(date_field, from_date, to_date, company, has_company)

    count = frappe.db.sql(
        "SELECT COUNT(*) FROM `{arch}` {where}".format(arch=_e(arch), where=where),
        params,
    )[0][0]

    if count == 0:
        return 0

    frappe.db.sql(
        "INSERT INTO `{live}` SELECT * FROM `{arch}` {where}".format(
            live=_e(live), arch=_e(arch), where=where
        ),
        params,
    )

    frappe.db.sql(
        "DELETE FROM `{arch}` {where}".format(arch=_e(arch), where=where),
        params,
    )

    return count


def _restore_children(parent_doctype, date_field, from_date, to_date, company):
    """Restore child table rows whose parent is in the restore date range."""
    import re

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", date_field):
        frappe.throw(_("Invalid date field name"))

    meta = frappe.get_meta(parent_doctype)
    has_company = meta.has_field("company")
    parent_arch = get_archive_table_name(parent_doctype)
    total = 0

    parent_where, parent_params = _build_where(
        date_field, from_date, to_date, company, has_company
    )

    for child_dt in get_child_doctypes(parent_doctype):
        if not archive_table_exists(child_dt):
            continue

        child_live = f"tab{child_dt}"
        child_arch = get_archive_table_name(child_dt)
        full_params = list(parent_params) + [parent_doctype]

        count = frappe.db.sql(
            "SELECT COUNT(*) FROM `{ca}` "
            "WHERE `parent` IN (SELECT `name` FROM `{pa}` {pw}) "
            "AND `parenttype` = %s".format(
                ca=_e(child_arch), pa=_e(parent_arch), pw=parent_where
            ),
            full_params,
        )[0][0]

        if count == 0:
            continue

        frappe.db.sql(
            "INSERT INTO `{cl}` SELECT c.* FROM `{ca}` c "
            "WHERE c.`parent` IN (SELECT `name` FROM `{pa}` {pw}) "
            "AND c.`parenttype` = %s".format(
                cl=_e(child_live), ca=_e(child_arch), pa=_e(parent_arch), pw=parent_where
            ),
            full_params,
        )

        frappe.db.sql(
            "DELETE c FROM `{ca}` c "
            "WHERE c.`parent` IN (SELECT `name` FROM `{pa}` {pw}) "
            "AND c.`parenttype` = %s".format(
                ca=_e(child_arch), pa=_e(parent_arch), pw=parent_where
            ),
            full_params,
        )

        total += count

    return total


def _build_where(date_field, from_date, to_date, company, has_company):
    parts = ["`{df}` BETWEEN %s AND %s".format(df=date_field)]
    params = [from_date, to_date]
    if has_company:
        parts.append("`company` = %s")
        params.append(company)
    return "WHERE " + " AND ".join(parts), tuple(params)


def _e(name):
    import re
    sanitised = re.sub(r"[^a-zA-Z0-9_ ]", "", name)
    if sanitised != name:
        frappe.throw(_("Invalid identifier: {0}").format(name))
    return sanitised


def _check_permission():
    if "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only System Manager can perform restore operations."))


def _update_archive_log(fiscal_year, company, doctype, status):
    logs = frappe.get_all(
        "Archive Log",
        filters={
            "fiscal_year": fiscal_year,
            "company": company,
            "doctype_name": doctype,
            "status": "Completed",
        },
        pluck="name",
    )
    for name in logs:
        frappe.db.set_value("Archive Log", name, "status", status)
