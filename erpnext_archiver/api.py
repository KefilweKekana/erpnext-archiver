# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Whitelisted API methods exposed to the browser.

All endpoints enforce **System Manager** role.
"""

import re

import frappe
from frappe import _


# ---------------------------------------------------------------------------
#  Archive / Restore
# ---------------------------------------------------------------------------

@frappe.whitelist()
def archive_fiscal_year(fiscal_year, company):
    """Archive all configured DocTypes for a fiscal year.

    Called from the Archive Settings page or a toolbar button.
    """
    frappe.only_for("System Manager")
    from erpnext_archiver.engine.archiver import archive_fiscal_year as _archive
    return _archive(fiscal_year, company)


@frappe.whitelist()
def restore_fiscal_year(fiscal_year, company):
    """Restore archived data back into live tables."""
    frappe.only_for("System Manager")
    from erpnext_archiver.engine.restore import restore_fiscal_year as _restore
    return _restore(fiscal_year, company)


# ---------------------------------------------------------------------------
#  Retrieve archived data (read-only, on-demand)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_archived_data(doctype, fiscal_year, company, fields=None, limit_page_length=100):
    """Return rows from the archive table for a specific fiscal year.

    This is the backend for the "Retrieve Archived Data" dialog.  Returns
    a read-only dataset; nothing is moved back into the live tables.
    """
    frappe.only_for("System Manager")

    # Validate inputs
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("DocType {0} does not exist").format(doctype))

    fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
    from_date = fy_doc.year_start_date
    to_date = fy_doc.year_end_date

    from erpnext_archiver.engine.schema_manager import archive_table_exists, get_archive_table_name
    if not archive_table_exists(doctype):
        return []

    arch_table = get_archive_table_name(doctype)

    # Determine date field from settings
    date_field = _get_date_field(doctype)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", date_field):
        frappe.throw(_("Invalid date field"))

    # Determine select columns
    if fields:
        if isinstance(fields, str):
            fields = frappe.parse_json(fields)
        # Validate field names
        for f in fields:
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_.]*$", f):
                frappe.throw(_("Invalid field name: {0}").format(f))
        select_cols = ", ".join(["`{}`".format(f) for f in fields])
    else:
        select_cols = "*"

    # Build query
    meta = frappe.get_meta(doctype)
    has_company = meta.has_field("company")

    conditions = ["`{df}` BETWEEN %s AND %s".format(df=date_field)]
    params = [from_date, to_date]

    if has_company:
        conditions.append("`company` = %s")
        params.append(company)

    where = " AND ".join(conditions)

    limit = min(int(limit_page_length), 5000)

    rows = frappe.db.sql(
        "SELECT {cols} FROM `{table}` WHERE {where} ORDER BY `{df}` DESC LIMIT %s".format(
            cols=select_cols,
            table=_e(arch_table),
            where=where,
            df=date_field,
        ),
        tuple(params) + (limit,),
        as_dict=True,
    )

    return rows


@frappe.whitelist()
def get_archived_fiscal_years(company):
    """Return a list of fiscal years that have completed archive logs for
    *company*.  Used to populate the "Retrieve Archived Data" dialog.
    """
    frappe.only_for("System Manager")

    return frappe.get_all(
        "Archive Log",
        filters={"company": company, "status": "Completed"},
        fields=["distinct fiscal_year as fiscal_year"],
        order_by="fiscal_year desc",
    )


@frappe.whitelist()
def get_archive_row_count(doctype, fiscal_year, company):
    """Return the number of archived rows for a given doctype/FY/company."""
    frappe.only_for("System Manager")

    if not frappe.db.exists("DocType", doctype):
        frappe.throw(_("DocType {0} does not exist").format(doctype))

    from erpnext_archiver.engine.schema_manager import archive_table_exists, get_archive_table_name

    if not archive_table_exists(doctype):
        return 0

    fy_doc = frappe.get_doc("Fiscal Year", fiscal_year)
    date_field = _get_date_field(doctype)

    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", date_field):
        frappe.throw(_("Invalid date field"))

    arch_table = get_archive_table_name(doctype)
    meta = frappe.get_meta(doctype)
    has_company = meta.has_field("company")

    conditions = ["`{df}` BETWEEN %s AND %s".format(df=date_field)]
    params = [fy_doc.year_start_date, fy_doc.year_end_date]

    if has_company:
        conditions.append("`company` = %s")
        params.append(company)

    where = " AND ".join(conditions)

    return frappe.db.sql(
        "SELECT COUNT(*) FROM `{table}` WHERE {where}".format(
            table=_e(arch_table), where=where
        ),
        tuple(params),
    )[0][0]


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _get_date_field(doctype):
    """Look up the configured date field for *doctype* from Archive Settings."""
    settings = frappe.get_single("Archive Settings")
    for row in settings.doctypes_to_archive:
        if row.doctype_name == doctype:
            return row.date_field
    return "posting_date"


def _e(name):
    sanitised = re.sub(r"[^a-zA-Z0-9_ ]", "", name)
    if sanitised != name:
        frappe.throw(_("Invalid identifier: {0}").format(name))
    return sanitised
