# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/geographies/address"
BENCHMARK = "Public_AR_Current"
VINTAGE = "Current_Current"


class PropertyDataSource(models.Model):
    _inherit = "property.data.source"

    provider = fields.Selection(
        selection_add=[("census", "US Census Geocoder")],
        ondelete={"census": "set default"},
    )

    def _census_capabilities(self):
        # The Census geocoder resolves an address to a point and the county
        # FIPS, but has no address-from-point service, so geocode only.
        return ["geocode"]

    def _census_geocode(self, address_vals):
        params = {
            "street": address_vals.get("street"),
            "city": address_vals.get("city"),
            "state": address_vals.get("state_code"),
            "zip": address_vals.get("zip"),
            "benchmark": BENCHMARK,
            "vintage": VINTAGE,
            "format": "json",
        }
        params = {k: v for k, v in params.items() if v}
        payload = self._http_get_json(CENSUS_URL, params=params)
        matches = (payload.get("result") or {}).get("addressMatches") or []
        if not matches:
            return {}
        match = matches[0]
        coords = match.get("coordinates") or {}
        vals = {
            "lat": coords.get("y"),
            "lon": coords.get("x"),
            "formatted": match.get("matchedAddress"),
            "raw": match,
        }
        counties = (match.get("geographies") or {}).get("Counties") or []
        if counties:
            county = counties[0]
            vals["county_fips"] = county.get("GEOID") or (
                (county.get("STATE") or "") + (county.get("COUNTY") or "")
            )
        return vals
