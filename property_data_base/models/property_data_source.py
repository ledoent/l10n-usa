# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# The capabilities a source can advertise: where the property is, its parcel
# shape, what's on it, who owns/values it, and what may restrict building on it.
# ``footprint`` and ``valuation`` are wired extension points reserved for
# upcoming connectors (footprint via Overture/Microsoft, valuation via ATTOM).
CAPABILITIES = [
    ("geocode", "Geocode (address -> lat/lon)"),
    ("parcel_geometry", "Parcel boundary geometry"),
    ("attributes", "Property attributes"),
    ("owner", "Ownership"),
    ("footprint", "Building footprint"),
    ("valuation", "Valuation / AVM"),
    ("constraints", "Construction / regulatory constraints"),
]
CAPABILITY_CODES = [code for code, _label in CAPABILITIES]


class PropertyDataSource(models.Model):
    """A configured property-data provider.

    One row per usable provider. The ``provider`` selection is extended by each
    connector module (``selection_add``); the connector implements the
    capability and fetch methods named ``_<provider>_<suffix>`` which the public
    methods below dispatch to. This mirrors the ``delivery.carrier`` /
    ``payment.provider`` dispatch pattern so connectors stay self-contained.
    """

    _name = "property.data.source"
    _description = "Property Data Source"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    provider = fields.Selection(
        selection=[("manual", "Manual entry")],
        required=True,
        default="manual",
        help="Connector that backs this source. Installed connector modules "
        "add their own entries.",
    )
    sequence = fields.Integer(
        default=10,
        help="Resolution priority. Lower runs first, so put free/preferred "
        "sources above paid fallbacks.",
    )
    active = fields.Boolean(default=True)
    capability_display = fields.Char(
        string="Capabilities",
        compute="_compute_capability_display",
        help="What this source can return, derived from the connector.",
    )
    cache_ttl_days = fields.Integer(
        string="Cache TTL (days)",
        default=31,
        help="A property record fetched from this source is considered fresh "
        "for this many days, so it is not re-fetched (and re-billed) within "
        "the window. 0 disables caching.",
    )
    request_timeout = fields.Integer(
        string="Request Timeout (s)",
        default=15,
    )

    @api.depends("provider")
    def _compute_capability_display(self):
        labels = dict(CAPABILITIES)
        for source in self:
            caps = source._get_capabilities()
            source.capability_display = ", ".join(labels.get(cap, cap) for cap in caps)

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------
    def _provider_method(self, suffix):
        """Return the connector method ``_<provider>_<suffix>`` or None."""
        self.ensure_one()
        return getattr(self, f"_{self.provider}_{suffix}", None)

    def _get_capabilities(self):
        """List of capability codes this source advertises."""
        self.ensure_one()
        method = self._provider_method("capabilities")
        return list(method()) if method else []

    def provides(self, capability):
        self.ensure_one()
        return capability in self._get_capabilities()

    # ------------------------------------------------------------------
    # Public fetch API
    #
    # Two entry points only, so a multi-capability provider (e.g. one that
    # returns parcel geometry + attributes + owner in a single call) is billed
    # once. Connectors implement:
    #   ``_<provider>_geocode(address_vals)`` for the geocode capability, and
    #   ``_<provider>_fetch(capabilities, lat, lon, address)`` for any of the
    #   data capabilities (parcel_geometry/attributes/owner/footprint),
    #   returning the merged normalized dict documented on ``property.record``.
    # ------------------------------------------------------------------
    def geocode(self, address_vals):
        """address_vals -> {lat, lon, formatted, county_fips, raw, ...}."""
        self.ensure_one()
        if not self.provides("geocode"):
            return {}
        return self._dispatch("geocode", address_vals)

    def fetch_data(self, capabilities, lat=None, lon=None, address=None):
        """Fetch every requested capability this source serves in one call.

        Note: not named ``fetch`` - that is a reserved ORM method on
        ``BaseModel`` (field prefetch) and overriding it breaks the ORM.
        """
        self.ensure_one()
        served = [c for c in capabilities if self.provides(c)]
        if not served:
            return {}
        return self._dispatch("fetch", served, lat, lon, address)

    def _dispatch(self, suffix, *args, **kwargs):
        method = self._provider_method(suffix)
        if not method:
            return {}
        try:
            return method(*args, **kwargs) or {}
        except UserError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface any connector error
            _logger.warning(
                "Property data source %s failed on %s: %s",
                self.name,
                suffix,
                exc,
            )
            raise UserError(
                _("Property data source '%(name)s' failed: %(error)s")
                % {"name": self.name, "error": exc}
            ) from exc

    # ------------------------------------------------------------------
    # Shared utilities for connectors
    # ------------------------------------------------------------------
    def _get_api_key(self):
        """API key for this provider from ``property_data.<provider>.api_key``."""
        self.ensure_one()
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(f"property_data.{self.provider}.api_key")
        )

    def _http_get_json(self, url, params=None, headers=None):
        """GET ``url`` and return parsed JSON, raising UserError on failure."""
        self.ensure_one()
        response = requests.get(
            url,
            params=params or {},
            headers=headers or {},
            timeout=self.request_timeout or 15,
        )
        response.raise_for_status()
        return response.json()

    def _arcgis_point_query(self, url, lat, lon, out_fields="*"):
        """Query an Esri ArcGIS REST FeatureServer/MapServer layer at a point.

        The free government overlay services (FEMA flood, NPS historic, county
        parcels) all speak this dialect, so connectors share it. Returns the
        list of matched feature ``attributes`` dicts (empty if none/no point).
        """
        self.ensure_one()
        if not (lat and lon):
            return []
        payload = self._http_get_json(
            url,
            params={
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": out_fields,
                "returnGeometry": "false",
                "f": "json",
            },
        )
        return [f.get("attributes", {}) for f in payload.get("features", [])]

    # Base "manual" provider advertises nothing automated; rows of this type
    # exist so a property record can be hand-entered.
    def _manual_capabilities(self):
        return []
