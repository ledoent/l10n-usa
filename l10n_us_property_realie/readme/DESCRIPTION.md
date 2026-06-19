Adds [Realie](https://realie.ai) as a `property.data.source` for
[property_data_base](https://github.com/OCA/l10n-usa).

Realie is a self-serve US property API that returns **parcel boundary geometry,
ownership, tax/assessment and zoning in a single call** across 3,100+ counties.
It is the cheapest self-serve source that bundles parcel geometry *and* owner,
which makes it the practical default for filling a `property.record` end to end.

Set the API key in **Settings > Property Data > Realie** (or the system
parameter `property_data.realie.api_key`). The source is seeded at a lower
priority than free geocoders, so the free Census geocoder still provides the
point and Realie supplies the parcel and ownership data.

To point at a sandbox or proxy endpoint, override the base URL with the system
parameter `property_data.realie.api_url` (default
`https://app.realie.ai/api/public/property/`).
