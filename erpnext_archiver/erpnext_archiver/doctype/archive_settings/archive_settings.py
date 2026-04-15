# Copyright (c) 2024, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ArchiveSettings(Document):
    def validate(self):
        seen = set()
        for row in self.doctypes_to_archive:
            if row.doctype_name in seen:
                frappe.throw(
                    frappe._("Duplicate entry: {0}").format(row.doctype_name)
                )
            seen.add(row.doctype_name)

            if not frappe.db.exists("DocType", row.doctype_name):
                frappe.throw(
                    frappe._("DocType {0} does not exist.").format(row.doctype_name)
                )

            meta = frappe.get_meta(row.doctype_name)
            if not meta.has_field(row.date_field):
                frappe.throw(
                    frappe._("Field {0} does not exist on {1}.").format(
                        row.date_field, row.doctype_name
                    )
                )
