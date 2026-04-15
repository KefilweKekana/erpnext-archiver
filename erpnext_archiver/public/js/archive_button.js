/**
 * archive_button.js
 *
 * Included globally via hooks.app_include_js.
 * Adds the "Archive Fiscal Year" and "Restore Fiscal Year" actions
 * to the Archive Settings page.
 *
 * Compatible with Frappe v14, v15, v16.
 */

/* global frappe */

frappe.ui.form.on("Archive Settings", {
    refresh: function (frm) {
        if (!frappe.user.has_role("System Manager")) return;

        frm.add_custom_button(
            __("Archive a Fiscal Year"),
            function () {
                _show_archive_dialog(frm);
            },
            __("Actions")
        );

        frm.add_custom_button(
            __("Restore a Fiscal Year"),
            function () {
                _show_restore_dialog(frm);
            },
            __("Actions")
        );

        frm.add_custom_button(
            __("View Archive Logs"),
            function () {
                frappe.set_route("List", "Archive Log");
            },
            __("Actions")
        );
    },
});

/* ------------------------------------------------------------------ */
/*  Archive dialog                                                    */
/* ------------------------------------------------------------------ */

function _show_archive_dialog(frm) {
    var d = new frappe.ui.Dialog({
        title: __("Archive a Fiscal Year"),
        fields: [
            {
                fieldname: "company",
                fieldtype: "Link",
                options: "Company",
                label: __("Company"),
                reqd: 1,
                default: frappe.defaults.get_user_default("Company"),
            },
            {
                fieldname: "fiscal_year",
                fieldtype: "Link",
                options: "Fiscal Year",
                label: __("Fiscal Year to Archive"),
                reqd: 1,
                get_query: function () {
                    return { filters: { disabled: 0 } };
                },
            },
            {
                fieldname: "warning",
                fieldtype: "HTML",
                options:
                    '<div class="alert alert-warning" style="margin-top:10px;">' +
                    "<strong>" + __("Warning") + ":</strong> " +
                    __("This will move all transaction data for the selected fiscal year into archive tables. " +
                    "A Period Closing Voucher must be submitted first. " +
                    "This operation may take several minutes for large datasets.") +
                    "</div>",
            },
        ],
        primary_action_label: __("Start Archive"),
        primary_action: function (values) {
            d.hide();
            frappe.confirm(
                __(
                    "Are you sure you want to archive {0} for {1}? This cannot be easily undone.",
                    [values.fiscal_year, values.company]
                ),
                function () {
                    frappe.call({
                        method: "erpnext_archiver.api.archive_fiscal_year",
                        args: {
                            fiscal_year: values.fiscal_year,
                            company: values.company,
                        },
                        freeze: true,
                        freeze_message: __("Archiving data — please wait…"),
                        callback: function (r) {
                            if (r.message) {
                                _show_summary("Archive", r.message);
                            }
                        },
                    });
                }
            );
        },
    });
    d.show();
}

/* ------------------------------------------------------------------ */
/*  Restore dialog                                                    */
/* ------------------------------------------------------------------ */

function _show_restore_dialog(frm) {
    var d = new frappe.ui.Dialog({
        title: __("Restore a Fiscal Year"),
        fields: [
            {
                fieldname: "company",
                fieldtype: "Link",
                options: "Company",
                label: __("Company"),
                reqd: 1,
                default: frappe.defaults.get_user_default("Company"),
            },
            {
                fieldname: "fiscal_year",
                fieldtype: "Link",
                options: "Fiscal Year",
                label: __("Fiscal Year to Restore"),
                reqd: 1,
            },
        ],
        primary_action_label: __("Restore"),
        primary_action: function (values) {
            d.hide();
            frappe.confirm(
                __(
                    "Are you sure you want to restore archived data for {0} / {1} back to the live database?",
                    [values.fiscal_year, values.company]
                ),
                function () {
                    frappe.call({
                        method: "erpnext_archiver.api.restore_fiscal_year",
                        args: {
                            fiscal_year: values.fiscal_year,
                            company: values.company,
                        },
                        freeze: true,
                        freeze_message: __("Restoring data — please wait…"),
                        callback: function (r) {
                            if (r.message) {
                                _show_summary("Restore", r.message);
                            }
                        },
                    });
                }
            );
        },
    });
    d.show();
}

/* ------------------------------------------------------------------ */
/*  Summary display                                                   */
/* ------------------------------------------------------------------ */

function _show_summary(action, results) {
    var html = '<table class="table table-bordered" style="font-size: 13px;">';
    html += "<thead><tr><th>" + __("DocType") + "</th><th>" + __("Status") + "</th><th>" + __("Rows") + "</th></tr></thead><tbody>";

    results.forEach(function (r) {
        var badge_class = r.status === "Completed" || r.status === "Restored" ? "green" : "red";
        var count = r.rows_archived || r.rows_restored || 0;
        html +=
            "<tr>" +
            "<td>" + (r.doctype || "") + "</td>" +
            '<td><span class="indicator-pill ' + badge_class + '">' + (r.status || "") + "</span></td>" +
            "<td>" + count + "</td>" +
            "</tr>";
    });

    html += "</tbody></table>";

    frappe.msgprint({
        title: __(action + " Summary"),
        indicator: "blue",
        message: html,
    });
}
