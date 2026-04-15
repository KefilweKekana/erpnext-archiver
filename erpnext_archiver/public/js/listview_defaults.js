/**
 * listview_defaults.js
 *
 * Loaded via hooks.doctype_list_js for every archivable DocType.
 * - Sets a default fiscal-year filter so only the current FY rows load.
 * - Adds a "Retrieve Archived Data" button to the list toolbar.
 *
 * Compatible with Frappe / ERPNext v14, v15, v16.
 */

/* global frappe, cur_list */

(function () {
    "use strict";

    /** Name of the current DocType is injected by Frappe when this file is loaded. */
    var ARCHIVE_DOCTYPES = [
        "Sales Invoice",
        "Purchase Invoice",
        "Payment Entry",
        "Journal Entry",
        "Delivery Note",
        "Purchase Receipt",
        "Sales Order",
        "Purchase Order",
    ];

    var DATE_FIELD_MAP = {
        "Sales Invoice": "posting_date",
        "Purchase Invoice": "posting_date",
        "Payment Entry": "posting_date",
        "Journal Entry": "posting_date",
        "Delivery Note": "posting_date",
        "Purchase Receipt": "posting_date",
        "Sales Order": "transaction_date",
        "Purchase Order": "transaction_date",
    };

    /**
     * Attach behaviour when a list view loads for any of the archivable DocTypes.
     */
    ARCHIVE_DOCTYPES.forEach(function (dt) {
        if (!frappe.listview_settings[dt]) {
            frappe.listview_settings[dt] = {};
        }

        var _existing_onload = frappe.listview_settings[dt].onload;

        frappe.listview_settings[dt].onload = function (listview) {
            // Call any previously registered onload
            if (_existing_onload) {
                _existing_onload(listview);
            }

            _apply_default_fy_filter(listview, dt);
            _add_retrieve_button(listview, dt);
        };
    });

    /* ------------------------------------------------------------------ */
    /*  Default fiscal year filter                                        */
    /* ------------------------------------------------------------------ */

    function _apply_default_fy_filter(listview, dt) {
        var fy = frappe.defaults.get_user_default("fiscal_year")
            || frappe.defaults.get_default("fiscal_year");

        if (!fy) return;

        // Only set once (don't overwrite user-applied filters)
        try {
            var already_filtered = false;

            // v15/v16 API
            if (listview.filter_area && listview.filter_area.filter_list) {
                already_filtered = listview.filter_area.filter_list.some(function (f) {
                    var fn = f.fieldname || (f.filter && f.filter[1]);
                    return fn === "fiscal_year";
                });
            }

            // v14 fallback
            if (!already_filtered && listview.filters) {
                already_filtered = listview.filters.some(function (f) {
                    return (Array.isArray(f) ? f[1] : f) === "fiscal_year";
                });
            }

            if (already_filtered) return;

            // Apply the fiscal year filter
            var meta = frappe.get_meta(dt);
            var has_fiscal_year = meta && meta.fields.some(function (f) {
                return f.fieldname === "fiscal_year";
            });

            if (has_fiscal_year && listview.filter_area) {
                listview.filter_area.add(dt, "fiscal_year", "=", fy);
            }
        } catch (e) {
            // Silently ignore if filter API has changed
            console.warn("ERPNext Archiver: could not apply default FY filter", e);
        }
    }

    /* ------------------------------------------------------------------ */
    /*  "Retrieve Archived Data" button                                   */
    /* ------------------------------------------------------------------ */

    function _add_retrieve_button(listview, dt) {
        if (listview._archive_button_added) return;
        listview._archive_button_added = true;

        listview.page.add_inner_button(
            __("Retrieve Archived Data"),
            function () {
                _show_retrieve_dialog(dt);
            }
        );
    }

    function _show_retrieve_dialog(dt) {
        var company =
            frappe.defaults.get_user_default("Company")
            || frappe.defaults.get_default("company");

        var d = new frappe.ui.Dialog({
            title: __("Retrieve Archived Data"),
            fields: [
                {
                    fieldname: "company",
                    fieldtype: "Link",
                    options: "Company",
                    label: __("Company"),
                    default: company,
                    reqd: 1,
                },
                {
                    fieldname: "fiscal_year",
                    fieldtype: "Link",
                    options: "Fiscal Year",
                    label: __("Fiscal Year"),
                    reqd: 1,
                    get_query: function () {
                        return { filters: { disabled: 0 } };
                    },
                },
                {
                    fieldname: "limit",
                    fieldtype: "Int",
                    label: __("Max Rows"),
                    default: 500,
                    description: __("Maximum 5 000 rows"),
                },
            ],
            primary_action_label: __("Retrieve"),
            primary_action: function (values) {
                d.hide();
                _fetch_archive(dt, values.fiscal_year, values.company, values.limit);
            },
        });
        d.show();
    }

    function _fetch_archive(dt, fiscal_year, company, limit) {
        frappe.call({
            method: "erpnext_archiver.api.get_archived_data",
            args: {
                doctype: dt,
                fiscal_year: fiscal_year,
                company: company,
                limit_page_length: Math.min(limit || 500, 5000),
            },
            freeze: true,
            freeze_message: __("Loading archived data…"),
            callback: function (r) {
                if (!r.message || r.message.length === 0) {
                    frappe.msgprint(__("No archived data found for the selected period."));
                    return;
                }
                _show_results(dt, fiscal_year, r.message);
            },
        });
    }

    function _show_results(dt, fiscal_year, rows) {
        var cols = Object.keys(rows[0]).filter(function (k) {
            return k !== "_user_tags" && k !== "_liked_by" && k !== "_comments" && k !== "_assign";
        });

        // Build simple HTML table
        var html = '<div style="max-height:500px;overflow:auto;">';
        html += '<table class="table table-bordered table-striped" style="font-size:12px;">';
        html += "<thead><tr>";
        cols.slice(0, 10).forEach(function (c) {
            html += "<th>" + frappe.model.unscrub(c) + "</th>";
        });
        html += "</tr></thead><tbody>";

        rows.forEach(function (row) {
            html += "<tr>";
            cols.slice(0, 10).forEach(function (c) {
                var val = row[c] !== null && row[c] !== undefined ? row[c] : "";
                html += "<td>" + frappe.utils.escape_html(String(val)) + "</td>";
            });
            html += "</tr>";
        });

        html += "</tbody></table></div>";

        var d = new frappe.ui.Dialog({
            title: __("Archived {0} — {1} ({2} rows)", [dt, fiscal_year, rows.length]),
            size: "extra-large",
        });
        d.$body.html(html);
        d.show();
    }
})();
