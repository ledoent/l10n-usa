This module provides a **provider-agnostic layer for US property and parcel
data**. Every property-anchored service business — real estate, yard care,
construction, fencing, roofing, solar — quotes jobs from the same four facts
about a property: where it is, its parcel boundary, what is built on it, and who
owns and values it. Rather than locking a vertical to one paid vendor, this
module abstracts those facts behind a small capability interface so connectors
plug in by budget tier.

It defines:

- **`property.data.source`** — a registry of configured providers. Each declares
  the capabilities it serves (`geocode`, `parcel_geometry`, `attributes`,
  `owner`, `footprint`, `valuation`, `constraints`) and is tried in priority
  order, so free sources can run ahead of paid fallbacks.
- **`property.record`** — a normalized, cached property record (address,
  centroid, parcel geometry as GeoJSON, lot area, building attributes,
  ownership and valuation). Its `_resolve()` method walks the sources, fills
  empty fields, records per-provider provenance, and honours a cache TTL so a
  fresh record makes no network calls (and incurs no re-billing).
- **`property.constraint`** — construction/regulatory flags on a property
  (historic district, EPA pre-1978 lead, FEMA flood zone): the "can we do this
  job, and what compliance attaches?" check for a lead. Aggregated from every
  source advertising `constraints`, plus rules derived in-base from resolved
  fields via the `_derive_constraints()` hook.
- A **Fetch Property Data** action on contacts.

The `footprint` and `valuation` capabilities are wired extension points
reserved for upcoming connectors (building footprints via Overture/Microsoft,
valuation via ATTOM); no connector ships them yet.

This module ships no connector by itself. Install a connector such as
*US Census Geocoder* (free) or *Realie* (parcel geometry + owner) to make it
fetch live data.
