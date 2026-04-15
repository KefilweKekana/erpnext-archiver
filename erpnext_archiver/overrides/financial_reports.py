# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

"""
Monkey-patch for ``set_gl_entries_by_account`` in
``erpnext.accounts.report.financial_statements`` so that Balance Sheet,
Profit & Loss, Trial Balance, and all balance-forward reports
automatically include archived GL Entry rows.

**Works with ERPNext v14, v15, and v16.**

The patch uses ``inspect.signature`` to discover the parameter positions
at import time, making it immune to the parameter-order changes between
v14 (positional ``root_lft, root_rgt`` before ``filters``) and
v15/v16 (keyword-only ``root_lft, root_rgt``).
"""

import inspect
import re

import frappe
from frappe.utils import cint, cstr

from erpnext_archiver.engine.schema_manager import archive_table_exists

# ---------------------------------------------------------------------------
#  Module-level state
# ---------------------------------------------------------------------------

_original_fn = None
_param_names = None
_patched = False


# ---------------------------------------------------------------------------
#  Patch entry-point (called from erpnext_archiver/__init__.py)
# ---------------------------------------------------------------------------

def patch_financial_reports():
    """Apply the monkey-patch to ``set_gl_entries_by_account``.  Safe to call
    multiple times — the patch is only applied once.
    """
    global _original_fn, _param_names, _patched

    if _patched:
        return

    try:
        from erpnext.accounts.report import financial_statements as fs
    except ImportError:
        return  # ERPNext not installed

    fn = getattr(fs, "set_gl_entries_by_account", None)
    if fn is None:
        return

    _original_fn = fn
    _param_names = list(inspect.signature(fn).parameters.keys())
    fs.set_gl_entries_by_account = _patched_set_gl_entries
    _patched = True


# ---------------------------------------------------------------------------
#  Patched function
# ---------------------------------------------------------------------------

def _patched_set_gl_entries(*args, **kwargs):
    """Drop-in replacement for ``set_gl_entries_by_account``.

    1. Calls the original function (which reads live ``tabGL Entry``).
    2. If an archive table exists, queries it with the same filters.
    3. Merges the archive entries into ``gl_entries_by_account``.
    """
    # === Call original ===
    result = _original_fn(*args, **kwargs)

    # === Quick exit if no archive table ===
    if not archive_table_exists("GL Entry"):
        return result

    # === Extract parameters using discovered positions ===
    company = _arg("company", args, kwargs)
    from_date = _arg("from_date", args, kwargs)
    to_date = _arg("to_date", args, kwargs)
    gl_entries_by_account = _arg("gl_entries_by_account", args, kwargs)
    root_lft = _arg("root_lft", args, kwargs)
    root_rgt = _arg("root_rgt", args, kwargs)
    root_type = _arg("root_type", args, kwargs)
    filters = _arg("filters", args, kwargs)
    ignore_closing_entries = _arg("ignore_closing_entries", args, kwargs)

    if gl_entries_by_account is None or not to_date:
        return result

    # In v14 filters might be passed positionally; ensure we have company
    filter_company = company
    if filters and hasattr(filters, "company"):
        filter_company = filters.company or company

    # === Query archive GL entries ===
    archive_entries = _get_archive_gl_entries(
        filter_company, from_date, to_date,
        root_lft, root_rgt, root_type,
        filters, ignore_closing_entries,
    )

    for entry in archive_entries:
        gl_entries_by_account.setdefault(entry.account, []).append(entry)

    return result


# ---------------------------------------------------------------------------
#  Archive GL query
# ---------------------------------------------------------------------------

def _get_archive_gl_entries(
    company, from_date, to_date,
    root_lft, root_rgt, root_type,
    filters, ignore_closing_entries,
):
    """Run a raw SQL query against ``tabGL Entry Archive`` with the same
    core filters that the original function applies.
    """
    conditions = ["`ge`.`is_cancelled` = 0"]
    params = []

    # --- Company ---
    conditions.append("`ge`.`company` = %s")
    params.append(company)

    # --- Date range ---
    conditions.append("`ge`.`posting_date` <= %s")
    params.append(to_date)
    if from_date:
        conditions.append("`ge`.`posting_date` >= %s")
        params.append(from_date)

    # --- Account hierarchy ---
    if root_lft and root_rgt:
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM `tabAccount` `a`"
            "  WHERE `a`.`name` = `ge`.`account`"
            "    AND `a`.`lft` >= %s AND `a`.`rgt` <= %s"
            "    AND `a`.`is_group` = 0"
            ")"
        )
        params.extend([root_lft, root_rgt])
    elif root_type:
        conditions.append(
            "EXISTS ("
            "  SELECT 1 FROM `tabAccount` `a`"
            "  WHERE `a`.`name` = `ge`.`account`"
            "    AND `a`.`root_type` = %s AND `a`.`is_group` = 0"
            ")"
        )
        params.append(root_type)

    # --- Closing entries ---
    if ignore_closing_entries:
        conditions.append("`ge`.`voucher_type` != 'Period Closing Voucher'")

    # --- Finance book (if specified) ---
    if filters:
        fb = cstr(getattr(filters, "finance_book", "") or "")
        include_default = getattr(filters, "include_default_book_entries", False)

        if fb or include_default:
            company_fb = ""
            if include_default:
                company_fb = cstr(
                    frappe.get_cached_value("Company", company, "default_finance_book") or ""
                )

            books = list({fb, company_fb, ""}) if include_default else [fb, ""]
            placeholders = ", ".join(["%s"] * len(books))
            conditions.append(
                "(`ge`.`finance_book` IN ({ph}) OR `ge`.`finance_book` IS NULL)".format(
                    ph=placeholders
                )
            )
            params.extend(books)
        else:
            conditions.append(
                "(`ge`.`finance_book` IN (%s, '') OR `ge`.`finance_book` IS NULL)"
            )
            params.append(fb)

        # --- Cost center ---
        cc = getattr(filters, "cost_center", None)
        if cc:
            if isinstance(cc, str):
                cc = [cc]
            if cc:
                placeholders = ", ".join(["%s"] * len(cc))
                conditions.append(
                    "`ge`.`cost_center` IN ({ph})".format(ph=placeholders)
                )
                params.extend(cc)

        # --- Project ---
        proj = getattr(filters, "project", None)
        if proj:
            if isinstance(proj, str):
                proj = [proj]
            if proj:
                placeholders = ", ".join(["%s"] * len(proj))
                conditions.append(
                    "`ge`.`project` IN ({ph})".format(ph=placeholders)
                )
                params.extend(proj)

    where = " AND ".join(conditions)

    return frappe.db.sql(
        "SELECT `ge`.`account`, `ge`.`debit`, `ge`.`credit`,"
        " `ge`.`posting_date`, `ge`.`is_opening`, `ge`.`fiscal_year`,"
        " `ge`.`debit_in_account_currency`, `ge`.`credit_in_account_currency`,"
        " `ge`.`account_currency`"
        " FROM `tabGL Entry Archive` `ge`"
        " WHERE {where}".format(where=where),
        tuple(params),
        as_dict=True,
    )


# ---------------------------------------------------------------------------
#  Version-compatible argument extraction
# ---------------------------------------------------------------------------

def _arg(name, args, kwargs):
    """Return the value of parameter *name* from positional *args* or
    *kwargs*, using the parameter order discovered at patch time.
    """
    if name in kwargs:
        return kwargs[name]
    if _param_names:
        try:
            idx = _param_names.index(name)
            if idx < len(args):
                return args[idx]
        except ValueError:
            pass
    return None
