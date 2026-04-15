from frappe import _


def get_data():
    return [
        {
            "module_name": "ERPNext Archiver",
            "type": "module",
            "label": _("ERPNext Archiver"),
            "color": "#5e64ff",
            "icon": "octicon octicon-archive",
            "description": "Long-term data archiving for ERPNext.",
        }
    ]
