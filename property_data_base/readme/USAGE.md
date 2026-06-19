1. Install at least one connector module (e.g. `l10n_us_property_census`,
   `l10n_us_property_realie`).
2. Go to **Property Data > Configuration > Data Sources** and add a row per
   provider. Order them by priority — put free providers above paid ones.
3. For providers that need a key, set it in **Settings** (the connector adds its
   own field) or as the system parameter `property_data.<provider>.api_key`.
4. On any contact with a US address, click **Fetch Property Data**. A
   `property.record` is created (or refreshed) with the parcel geometry,
   attributes and ownership the configured sources can supply.

Programmatic use:

```python
record = env["property.record"].create({"partner_id": partner.id})
record._resolve(force=True)
record.geometry  # GeoJSON parcel boundary
```

`_resolve()` fills only empty fields and never re-fetches a record that is still
within its cache TTL unless you pass `force=True`.
