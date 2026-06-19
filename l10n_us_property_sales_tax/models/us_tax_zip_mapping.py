# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class UsTaxZipMapping(models.Model):
    _inherit = "us.tax.zip.mapping"

    @api.model
    def _geocode_jurisdiction(self, address):
        """Resolve a tax jurisdiction from a rooftop geocode.

        Geocode the address with the property-data geocoder (free, e.g. US
        Census) to get the county FIPS, then match the county tax jurisdiction
        by FIPS. The engine learns the result, so a straddling ZIP resolves to
        the correct county without any paid provider call.
        """
        res = super()._geocode_jurisdiction(address)
        if res:
            return res

        geocoders = (
            self.env["property.data.source"]
            .search([("active", "=", True)], order="sequence, id")
            .filtered(lambda s: s.provides("geocode"))
        )
        if not geocoders:
            return res

        full = address.get("address") or ""
        street = full.split(",")[0].strip() if full else ""
        if not street:
            return res
        vals = {
            "street": street,
            "city": address.get("city") or "",
            "state_code": address.get("state") or "",
            "zip": (address.get("zip") or "")[:5],
        }
        try:
            geo = geocoders[0].geocode(vals) or {}
        except Exception as exc:  # noqa: BLE001 - geocoding is best-effort
            _logger.info("Geocode jurisdiction lookup failed: %s", exc)
            return res

        fips = geo.get("county_fips") or ""
        if len(fips) < 5:
            return res
        return self.env["us.tax.jurisdiction"].search(
            [("fips_state", "=", fips[:2]), ("fips_county", "=", fips[2:5])],
            limit=1,
        )
