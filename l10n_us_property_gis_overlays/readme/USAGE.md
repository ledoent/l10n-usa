Install the module, then ensure your records are geocoded (e.g. via
*US Property Data - Census Geocoder*) so the overlay sources have a point to
query. The two sources are seeded automatically; on the next **Fetch Property
Data** they add `FEMA Flood Zone` and `Historic district: …` rows to the
record's **Constraints** tab.

## Pinning a different endpoint

Both services default to the national US-government ArcGIS endpoints. To point
at a state/regional mirror or a refreshed URL, set the matching system
parameter (Settings → Technical → Parameters → System Parameters):

| Key | Default |
| --- | --- |
| `property_data.fema_flood.url` | `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query` |
| `property_data.nrhp.url` | `https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/nrhp_locations/MapServer/1/query` |

Any Esri ArcGIS REST `…/query` endpoint that accepts an `esriGeometryPoint`
intersect query works. The NRHP URL must point at a **polygon** layer (historic
*districts*), not the points layer.
