// Copyright (c) 2024, Your Company and contributors
// For license information, please see license.txt

frappe.ui.form.on("Archive Settings", {
    refresh: function (frm) {
        if (!frm.doc.doctypes_to_archive || frm.doc.doctypes_to_archive.length === 0) {
            // Pre-populate with default doctypes
            var defaults = [
                { doctype_name: "GL Entry", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Stock Ledger Entry", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Sales Invoice", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Purchase Invoice", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Payment Entry", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Journal Entry", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Delivery Note", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Purchase Receipt", date_field: "posting_date", is_active: 1 },
                { doctype_name: "Sales Order", date_field: "transaction_date", is_active: 1 },
                { doctype_name: "Purchase Order", date_field: "transaction_date", is_active: 1 },
            ];
            defaults.forEach(function (d) {
                var row = frm.add_child("doctypes_to_archive");
                $.extend(row, d);
            });
            frm.refresh_field("doctypes_to_archive");
        }
    },
});
