# ERPNext Archiver

Long-term data archiving for ERPNext — keeps only the current fiscal year in the live database while older years are moved to archive tables.

## Features

- Archive completed fiscal years with one click
- Restore archived data on demand
- Automatic inclusion of archived GL entries in financial reports (Balance Sheet, Profit & Loss, Trial Balance)
- Default fiscal-year filters on list views to keep UI fast
- Compatible with ERPNext v14, v15, and v16

## Installation

```bash
bench get-app https://github.com/KefilweKekana/erpnext-archiver.git
bench --site your-site install-app erpnext_archiver
```

## Configuration

1. Go to **Archive Settings** in the desk
2. Add the DocTypes you want to archive (e.g. GL Entry, Sales Invoice, etc.)
3. Use the **Archive a Fiscal Year** button to archive a completed year

## License

MIT
