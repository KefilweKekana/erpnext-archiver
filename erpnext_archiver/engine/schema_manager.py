# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Schema manager — creates and synchronises archive tables so they always
mirror the live table schema.  Works on MariaDB 10.x+ (v14-v16).
"""

import re

import frappe


def _run_ddl(statement):
    """Execute a DDL statement.  Uses ``sql_ddl`` on Frappe v15+ and falls
    back to plain ``sql`` on v14."""
    if hasattr(frappe.db, "sql_ddl"):
        frappe.db.sql_ddl(statement)
    else:
        frappe.db.sql(statement)


# ---------------------------------------------------------------------------
#  Public helpers
# ---------------------------------------------------------------------------

def get_archive_table_name(doctype):
    """Return the archive table name for a DocType.

    e.g. "GL Entry" -> "tabGL Entry Archive"
    """
    return f"tab{doctype} Archive"


def archive_table_exists(doctype):
    """Check whether the archive table for *doctype* already exists."""
    table = get_archive_table_name(doctype)
    return bool(
        frappe.db.sql(
            "SELECT 1 FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s LIMIT 1",
            (table,),
        )
    )


def ensure_archive_table(doctype):
    """Create the archive table if it does not exist, then sync schema.

    Uses ``CREATE TABLE ... LIKE`` so indexes, column types and defaults
    are identical to the live table.
    """
    _validate_doctype(doctype)

    live_table = f"tab{doctype}"
    arch_table = get_archive_table_name(doctype)

    if not archive_table_exists(doctype):
        _run_ddl(
            "CREATE TABLE IF NOT EXISTS `{archive}` LIKE `{live}`".format(
                archive=_esc(arch_table), live=_esc(live_table)
            )
        )
    else:
        sync_archive_schema(doctype)


def sync_archive_schema(doctype):
    """Add any columns present in the live table but missing from the
    archive table.  Existing columns are never dropped or altered so
    archived data is never at risk.
    """
    live_table = f"tab{doctype}"
    arch_table = get_archive_table_name(doctype)

    live_cols = _get_columns(live_table)
    arch_cols = _get_columns(arch_table)

    arch_col_names = {c["COLUMN_NAME"] for c in arch_cols}

    for col in live_cols:
        if col["COLUMN_NAME"] not in arch_col_names:
            col_def = _build_column_definition(col)
            _run_ddl(
                "ALTER TABLE `{table}` ADD COLUMN {col_def}".format(
                    table=_esc(arch_table), col_def=col_def
                )
            )


def get_child_doctypes(parent_doctype):
    """Return a list of child-table DocType names linked to *parent_doctype*."""
    _validate_doctype(parent_doctype)
    return frappe.get_all(
        "DocField",
        filters={"parent": parent_doctype, "fieldtype": "Table"},
        pluck="options",
    )


# ---------------------------------------------------------------------------
#  Internal helpers
# ---------------------------------------------------------------------------

def _validate_doctype(doctype):
    """Guard: only allow known DocType names to prevent SQL injection via
    table-name interpolation."""
    if not frappe.db.exists("DocType", doctype):
        frappe.throw(frappe._("DocType {0} does not exist").format(doctype))


def _esc(name):
    """Minimal escaping for identifiers that will be wrapped in backticks.

    Strips backticks to prevent breakout; only allows alphanumeric, space
    and underscore.
    """
    sanitised = re.sub(r"[^a-zA-Z0-9_ ]", "", name)
    if sanitised != name:
        frappe.throw(frappe._("Invalid table name: {0}").format(name))
    return sanitised


def _get_columns(table_name):
    """Return column metadata from information_schema for *table_name*."""
    return frappe.db.sql(
        "SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, EXTRA "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION",
        (table_name,),
        as_dict=True,
    )


def _build_column_definition(col):
    """Build an ``ADD COLUMN`` fragment from an information_schema row."""
    parts = ["`{}`".format(_esc(col["COLUMN_NAME"])), col["COLUMN_TYPE"]]

    if col["IS_NULLABLE"] == "NO":
        parts.append("NOT NULL")

    if col["COLUMN_DEFAULT"] is not None:
        # Wrap string defaults in quotes; numeric/NULL pass through
        default = col["COLUMN_DEFAULT"]
        if default in ("CURRENT_TIMESTAMP",):
            parts.append(f"DEFAULT {default}")
        else:
            parts.append("DEFAULT %s" % frappe.db.escape(default))

    if col.get("EXTRA"):
        parts.append(col["EXTRA"])

    return " ".join(parts)
