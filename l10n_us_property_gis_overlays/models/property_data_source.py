# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models

# Free US government ArcGIS REST services. Both are configurable via system
# parameters so deployers can pin a state/regional mirror or a refreshed
# endpoint without patching the addon.
DEFAULT_FEMA_URL = (
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
)
# Layer 1 is the National Register *polygons* (districts), so a point query
# resolves "is this parcel inside a historic district".
DEFAULT_NRHP_URL = (
    "https://mapservices.nps.gov/arcgis/rest/services/cultural_resources/"
    "nrhp_locations/MapServer/1/query"
)

# FEMA zones beginning with these letters are Special Flood Hazard Areas.
_SFHA_PREFIXES = ("A", "V")


class PropertyDataSource(models.Model):
    _inherit = "property.data.source"

    provider = fields.Selection(
        selection_add=[
            ("fema_flood", "FEMA Flood Zone"),
            ("nrhp", "NRHP Historic District"),
        ],
        ondelete={"fema_flood": "set default", "nrhp": "set default"},
    )

    def _overlay_url(self, param, default):
        return self.env["ir.config_parameter"].sudo().get_param(param) or default

    # ------------------------------------------------------------------
    # FEMA National Flood Hazard Layer
    # ------------------------------------------------------------------
    def _fema_flood_capabilities(self):
        return ["constraints"]

    def _fema_flood_fetch(self, capabilities, lat=None, lon=None, address=None):
        if not (lat and lon):
            return {}
        url = self._overlay_url("property_data.fema_flood.url", DEFAULT_FEMA_URL)
        rows = self._arcgis_point_query(
            url, lat, lon, out_fields="FLD_ZONE,ZONE_SUBTY,SFHA_TF"
        )
        constraints = []
        for row in rows:
            zone = row.get("FLD_ZONE")
            if not zone:
                continue
            sfha = row.get("SFHA_TF") == "T" or zone[:1] in _SFHA_PREFIXES
            constraints.append(
                {
                    "code": "fema_flood_zone",
                    "name": _("FEMA Flood Zone %s") % zone,
                    "severity": "warning" if sfha else "info",
                    "applies": bool(sfha),
                    "details": " ".join(filter(None, [zone, row.get("ZONE_SUBTY")])),
                    "url": "https://msc.fema.gov/portal/home",
                }
            )
        # Always return the (possibly empty) list when we actually queried, so a
        # point that no longer matches clears its stale constraint on re-resolve.
        return {"constraints": constraints, "raw": rows}

    # ------------------------------------------------------------------
    # National Register of Historic Places
    # ------------------------------------------------------------------
    def _nrhp_capabilities(self):
        return ["constraints"]

    def _nrhp_fetch(self, capabilities, lat=None, lon=None, address=None):
        if not (lat and lon):
            return {}
        url = self._overlay_url("property_data.nrhp.url", DEFAULT_NRHP_URL)
        rows = self._arcgis_point_query(url, lat, lon, out_fields="*")
        constraints = []
        for row in rows:
            name = (
                row.get("RESNAME")
                or row.get("NAME")
                or row.get("ResName")
                or _("Listed district")
            )
            constraints.append(
                {
                    "code": "nrhp_historic_district",
                    "name": _("Historic district: %s") % name,
                    "severity": "warning",
                    "applies": True,
                    "details": _("Listed on the National Register of Historic Places."),
                    "url": "https://www.nps.gov/subjects/nationalregister/",
                }
            )
        return {"constraints": constraints, "raw": rows}
