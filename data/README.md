# Seed data (USAspending)

These CSVs are a **point-in-time snapshot** of public data from
[USAspending.gov](https://www.usaspending.gov/). They are bundled so Reasonbook
comes up with a working agency/recipient catalog out of the box, and they are
loaded by [`scripts/import_usaspending.py`](../scripts/import_usaspending.py).

| File | Loaded into |
|---|---|
| `entities_agencies.csv` | the agency catalog (`agency_catalog`) |
| `entities_recipients.csv` | recipient organizations (`participant_orgs`) |
| `entities.csv`, `entities_subrecipients.csv` | reference pulls (kept for completeness) |

All of this is **public, organization-level data — not personal PII.**

## Refresh with current data

The bundled snapshot ages. Before relying on the catalog in a real deployment,
refresh it:

1. Download current exports from <https://www.usaspending.gov/> (the "Award Data
   Archive" / Custom Award Data downloads).
2. Replace the files in this directory, keeping the **same filenames**.
3. Re-run the importer (it is idempotent — safe to run repeatedly):

   ```bash
   python -m scripts.import_usaspending --all
   # or individually: --agencies / --recipients / --states
   ```

On a container deployment the CSVs are baked into the image, so refreshing means
rebuilding the image with the new files (or running the importer against the
live database with the new CSVs mounted in).
