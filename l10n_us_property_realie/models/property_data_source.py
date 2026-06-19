# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError

DEFAULT_URL = "https://app.realie.ai/api/public/property/"

# Realie returns one normalized record per property. Field names are mapped
# defensively (first matching key wins) so minor API drift does not break the
# connector; verify against the live API on first use.
_FIELD_MAP = {
    "apn": ["apn", "parcelNumber", "parcel_number", "parcelId"],
    "lot_area_sqft": [
        "lotSizeSquareFeet",
        "lotSizeSqft",
        "lotSquareFeet",
        "landSquareFeet",
        "lotSize",
    ],
    "county_fips": ["countyFips", "fips", "countyFipsCode"],
    "year_built": ["yearBuilt", "year_built"],
    "building_area_sqft": [
        "buildingSquareFeet",
        "livingSquareFeet",
        "buildingAreaSqft",
        "sqft",
    ],
    "stories": ["stories", "numberOfStories"],
    "beds": ["bedrooms", "beds"],
    "baths": ["bathrooms", "baths"],
    "land_use": ["landUse", "useCode", "propertyType"],
    "zoning": ["zoning", "zoningCode"],
    "assessed_value": ["assessedValue", "totalAssessedValue"],
    "market_value": ["marketValue", "estimatedValue", "avm"],
    "owner_name": ["ownerName", "ownerFullName", "owner1Name", "owner"],
    "owner_mailing": [
        "ownerMailingAddress",
        "mailingAddress",
        "ownerAddress",
    ],
}


def _first(data, keys):
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return None


class PropertyDataSource(models.Model):
    _inherit = "property.data.source"

    provider = fields.Selection(
        selection_add=[("realie", "Realie")],
        ondelete={"realie": "set default"},
    )

    def _realie_capabilities(self):
        return ["parcel_geometry", "attributes", "owner"]

    def _realie_fetch(self, capabilities, lat=None, lon=None, address=None):
        api_key = self._get_api_key()
        if not api_key:
            raise UserError(
                _(
                    "No Realie API key configured. Set it in Settings or as "
                    "the system parameter 'property_data.realie.api_key'."
                )
            )
        url = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("property_data.realie.api_url")
            or DEFAULT_URL
        )
        params = {}
        if lat and lon:
            params.update(latitude=lat, longitude=lon)
        elif address:
            params["address"] = ", ".join(
                p
                for p in [
                    address.get("street"),
                    address.get("city"),
                    address.get("state_code"),
                    address.get("zip"),
                ]
                if p
            )
        if not params:
            return {}
        payload = self._http_get_json(
            url,
            params=params,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        prop = self._realie_first_property(payload)
        if not prop:
            return {}
        return self._realie_normalize(prop)

    def _realie_first_property(self, payload):
        if isinstance(payload, list):
            return payload[0] if payload else None
        for key in ("properties", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list) and value:
                return value[0]
            if isinstance(value, dict):
                return value
        # A bare property object.
        return payload if payload.get("apn") or payload.get("geometry") else None

    def _realie_normalize(self, prop):
        vals = {}
        for field, keys in _FIELD_MAP.items():
            value = _first(prop, keys)
            if value is not None:
                vals[field] = value
        geometry = self._realie_geometry(prop)
        if geometry:
            vals["geometry"] = geometry
        if prop:
            vals["raw"] = prop
        return vals

    def _realie_geometry(self, prop):
        geom = _first(prop, ["geometry", "parcelGeometry", "geojson", "boundary"])
        if not isinstance(geom, dict):
            return None
        # Accept a Feature wrapper or a bare geometry.
        if geom.get("type") == "Feature":
            geom = geom.get("geometry")
        if isinstance(geom, dict) and geom.get("type") in (
            "Polygon",
            "MultiPolygon",
        ):
            return geom
        return None
