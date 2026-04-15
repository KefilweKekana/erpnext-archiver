__version__ = "1.0.0"

def _apply_patches():
    """Apply monkey-patches to ERPNext report functions at import time."""
    try:
        from erpnext_archiver.overrides.financial_reports import patch_financial_reports
        patch_financial_reports()
    except Exception:
        # App may not be fully installed yet, or ERPNext is not available.
        pass

_apply_patches()
