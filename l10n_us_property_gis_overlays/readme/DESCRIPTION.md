Adds two **free US government** property data sources that contribute
construction/regulatory **constraints** to a `property.record`:

- **FEMA Flood Zone** — queries the FEMA National Flood Hazard Layer at the
  parcel point and flags Special Flood Hazard Areas (zones A*/V*), which carry
  elevation and permitting requirements for home-improvement work.
- **NRHP Historic District** — queries the National Park Service National
  Register service and flags properties inside a listed historic district,
  where exterior work is typically design-reviewed.

Both hit free public ArcGIS REST endpoints (no key, no cost) via the shared
`property.data.source._arcgis_point_query` helper. The service URLs are
configurable through the system parameters `property_data.fema_flood.url` and
`property_data.nrhp.url`, so a deployer can pin a state mirror or a refreshed
endpoint. Together with the EPA pre-1978 lead derivation, these answer the
"can we do this job, and what compliance attaches?" question for a lead.
