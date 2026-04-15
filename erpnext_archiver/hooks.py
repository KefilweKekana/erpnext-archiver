app_name = "erpnext_archiver"
app_title = "ERPNext Archiver"
app_publisher = "Your Company"
app_description = "Long-term data archiving for ERPNext — current FY stays live, older years archived."
app_email = "info@example.com"
app_license = "MIT"
app_icon = "octicon octicon-archive"
app_color = "#5e64ff"

# ---------- Frontend assets ----------
# Global JS (archive retrieval dialog, available on all pages)
app_include_js = "/assets/erpnext_archiver/js/archive_button.js"

# Per-doctype list view JS (adds default FY filter + retrieve button)
doctype_list_js = {
    "Sales Invoice": "public/js/listview_defaults.js",
    "Purchase Invoice": "public/js/listview_defaults.js",
    "Payment Entry": "public/js/listview_defaults.js",
    "Journal Entry": "public/js/listview_defaults.js",
    "Delivery Note": "public/js/listview_defaults.js",
    "Purchase Receipt": "public/js/listview_defaults.js",
    "Sales Order": "public/js/listview_defaults.js",
    "Purchase Order": "public/js/listview_defaults.js",
}

# ---------- Fixtures ----------
fixtures = []

# ---------- Permissions ----------
has_permission = {}

# ---------- Document Events ----------
doc_events = {}

# ---------- Scheduled Tasks ----------
# Intentionally empty — archiving is manual-only by default.
# Uncomment to enable yearly auto-archive:
# scheduler_events = {
#     "yearly": [
#         "erpnext_archiver.engine.archiver.auto_archive_previous_fy"
#     ]
# }
