# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Data capabilities filled by ``source.fetch()``, in resolution order.
_DATA_CAPABILITIES = ["parcel_geometry", "attributes", "owner", "footprint"]

# Connector return keys that map onto a differently-named record field.
_FIELD_ALIASES = {
    "lat": "latitude",
    "lon": "longitude",
    "centroid_lat": "latitude",
    "centroid_lon": "longitude",
    "formatted": "formatted_address",
}


class PropertyRecord(models.Model):
    _name = "property.record"
    _description = "Property Record"
    _inherit = ["mail.thread"]
    _order = "create_date desc"

    name = fields.Char(compute="_compute_name", store=True, default="New")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company)
    partner_id = fields.Many2one("res.partner", index=True, tracking=True)

    # Address
    formatted_address = fields.Char(tracking=True)
    street = fields.Char()
    city = fields.Char()
    state_id = fields.Many2one("res.country.state")
    zip = fields.Char()
    country_id = fields.Many2one(
        "res.country",
        default=lambda self: self.env.ref("base.us", raise_if_not_found=False),
    )

    # Geo (centroid)
    latitude = fields.Float(digits=(10, 7))
    longitude = fields.Float(digits=(10, 7))

    # Parcel
    apn = fields.Char(string="APN", help="Assessor's Parcel Number")
    geometry = fields.Json(help="Parcel boundary as a GeoJSON geometry")
    lot_area_sqft = fields.Float(string="Lot Area (sq ft)")
    county_fips = fields.Char(string="County FIPS")

    # Building
    building_footprint = fields.Json(help="Building footprint as GeoJSON")
    building_area_sqft = fields.Float(string="Building Area (sq ft)")
    year_built = fields.Integer()
    stories = fields.Integer()
    beds = fields.Integer()
    baths = fields.Float()

    # Ownership / value
    owner_name = fields.Char()
    owner_mailing = fields.Char(string="Owner Mailing Address")
    assessed_value = fields.Monetary()
    market_value = fields.Monetary(help="Market value / AVM")
    land_use = fields.Char()
    zoning = fields.Char()
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id")

    geometry_summary = fields.Char(
        compute="_compute_geometry_summary",
        help="Human-readable summary of the parcel geometry.",
    )

    # Construction / regulatory constraints (buildability check)
    constraint_ids = fields.One2many(
        "property.constraint", "record_id", string="Constraints"
    )
    constraint_count = fields.Integer(compute="_compute_constraint_stats")
    has_blocking_constraint = fields.Boolean(compute="_compute_constraint_stats")

    # Provenance / cache
    source_ids = fields.Many2many("property.data.source", string="Sources")
    fetched_on = fields.Datetime(readonly=True)
    is_stale = fields.Boolean(compute="_compute_is_stale")
    raw_response = fields.Json(
        help="Raw provider payloads keyed by provider, for audit."
    )

    @api.depends("formatted_address", "street", "city", "apn", "partner_id")
    def _compute_name(self):
        for rec in self:
            rec.name = (
                rec.formatted_address
                or rec.street
                or (rec.apn and _("Parcel %s") % rec.apn)
                or (rec.partner_id and rec.partner_id.name)
                or _("New")
            )

    @api.depends("geometry")
    def _compute_geometry_summary(self):
        for rec in self:
            geom = rec.geometry
            if not isinstance(geom, dict) or not geom.get("type"):
                rec.geometry_summary = False
                continue
            coords = geom.get("coordinates") or []
            rings = (
                len(coords)
                if geom["type"] == "Polygon"
                else sum(len(poly) for poly in coords)
            )
            rec.geometry_summary = _("%(type)s, %(rings)s ring(s)") % {
                "type": geom["type"],
                "rings": rings,
            }

    @api.depends("constraint_ids.applies", "constraint_ids.severity")
    def _compute_constraint_stats(self):
        for rec in self:
            applicable = rec.constraint_ids.filtered("applies")
            rec.constraint_count = len(applicable)
            rec.has_blocking_constraint = any(
                c.severity == "blocking" for c in applicable
            )

    @api.depends("fetched_on", "source_ids.cache_ttl_days")
    def _compute_is_stale(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.fetched_on:
                rec.is_stale = True
                continue
            ttls = rec.source_ids.mapped("cache_ttl_days") or [31]
            # A source with ttl 0 disables caching -> always stale. Otherwise
            # the shortest-lived source dictates freshness.
            if any(t <= 0 for t in ttls):
                rec.is_stale = True
                continue
            rec.is_stale = rec.fetched_on + timedelta(days=min(ttls)) < now

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def _address_vals(self):
        """Address dict handed to geocoders, preferring the linked partner."""
        self.ensure_one()
        src = self.partner_id if self.partner_id else self
        return {
            "street": src.street or self.formatted_address,
            "city": src.city,
            "state_code": src.state_id.code,
            "zip": src.zip,
            "country_code": (src.country_id and src.country_id.code) or "US",
        }

    def _resolve(self, capabilities=None, force=False):
        """Fill empty fields by walking active sources in priority order.

        For each capability the highest-priority source that returns data wins;
        fields already set are never overwritten. Honours the cache TTL unless
        ``force`` is set, so a fresh record makes no network calls.
        """
        capabilities = capabilities or _DATA_CAPABILITIES + ["constraints"]
        sources = self.env["property.data.source"].search(
            [("active", "=", True)], order="sequence, id"
        )
        errors = []
        for rec in self:
            if rec.fetched_on and not rec.is_stale and not force:
                continue
            errors += rec._resolve_one(sources, capabilities)
        return errors

    def _resolve_one(self, sources, capabilities):
        """Resolve one record. Returns ``[(source, message), ...]`` for sources
        that failed - one misconfigured/paid source (e.g. a missing API key)
        must not abort the whole chain, so each source call is isolated.
        """
        self.ensure_one()
        errors = []

        # Geocode first - downstream parcel/footprint lookups need a point.
        if not (self.latitude and self.longitude):
            for source in sources.filtered(lambda s: s.provides("geocode")):
                vals = self._call_source(
                    errors, source, "geocode", self._address_vals()
                )
                if vals:
                    self._apply(vals, source)
                    break

        # Each source is called once for all the data capabilities it serves,
        # in priority order. Scalar capabilities are first-wins (highest-
        # priority source is authoritative); ``constraints`` is additive, so
        # every source that provides it is consulted.
        want_constraints = "constraints" in capabilities
        needed = [c for c in _DATA_CAPABILITIES if c in capabilities]
        for source in sources:
            serve = [c for c in needed if source.provides(c)]
            if want_constraints and source.provides("constraints"):
                serve.append("constraints")
            if not serve:
                continue
            vals = self._call_source(
                errors,
                source,
                "fetch_data",
                serve,
                lat=self.latitude or None,
                lon=self.longitude or None,
                address=self._address_vals(),
            )
            if vals:
                self._apply(vals, source)
                needed = [c for c in needed if c not in serve]

        # Constraints derived in-base from already-resolved fields (free, no
        # external call) - e.g. the EPA pre-1978 lead rule from year_built.
        if want_constraints:
            self._sync_constraints(self._derive_constraints(), source=None)
        return errors

    def _derive_constraints(self):
        """Hook: constraints inferred from resolved fields, no external call.

        Base returns none; localisation modules extend this (e.g.
        ``l10n_us_property_constraints`` adds the EPA RRP lead rule).
        """
        self.ensure_one()
        return []

    def _sync_constraints(self, items, source):
        """Replace this source's constraint rows with ``items`` (idempotent).

        ``source`` is an empty recordset / falsy for in-base derived
        constraints, which live in their own bucket.
        """
        self.ensure_one()
        if source:
            stale = self.constraint_ids.filtered(lambda c, s=source: c.source_id == s)
        else:
            stale = self.constraint_ids.filtered(lambda c: not c.source_id)
        stale.unlink()
        for item in items or []:
            self.env["property.constraint"].create(
                {
                    "record_id": self.id,
                    "code": item.get("code"),
                    "name": item.get("name") or item.get("code"),
                    "severity": item.get("severity") or "info",
                    "applies": item.get("applies", True),
                    "details": item.get("details"),
                    "url": item.get("url"),
                    "source_id": source.id if source else False,
                }
            )

    def _call_source(self, errors, source, method_name, *args, **kwargs):
        """Call ``source.<method_name>(...)``, isolating its failure so the
        chain continues - one misconfigured source must not abort the rest.
        """
        try:
            return getattr(source, method_name)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - isolate one source's failure
            _logger.warning(
                "Property source %s skipped on %s: %s",
                source.name,
                self.display_name,
                exc,
            )
            errors.append((source, str(exc)))
            return {}

    def _apply(self, vals, source):
        """Fill empty fields from ``vals`` and record provenance."""
        self.ensure_one()
        vals = dict(vals)
        raw = vals.pop("raw", None)
        state_code = vals.pop("state_code", None)
        constraints = vals.pop("constraints", None)

        to_write = {}
        for key, value in vals.items():
            field = _FIELD_ALIASES.get(key, key)
            # Keep legitimate 0 / 0.0; only None / "" / [] count as "unset".
            if field not in self._fields or value in (None, "", []):
                continue
            if self[field]:  # never overwrite existing data
                continue
            to_write[field] = value

        if state_code and not self.state_id:
            state = self._find_state(state_code, vals.get("country_code"))
            if state:
                to_write["state_id"] = state.id

        # Nothing usable resolved (raw-only or empty payload): don't stamp
        # fetched_on / provenance, which would falsely mark the record fresh
        # and short-circuit later resolves. Constraints (even an empty list)
        # count as a real result - the source was consulted.
        if not to_write and constraints is None:
            return

        to_write.setdefault("source_ids", [(4, source.id)])
        to_write["fetched_on"] = fields.Datetime.now()
        if raw is not None:
            stored = dict(self.raw_response or {})
            stored[source.provider] = raw
            to_write["raw_response"] = stored

        self.write(to_write)

        if constraints is not None:
            self._sync_constraints(constraints, source)

    def _find_state(self, code, country_code=None):
        country = self.country_id
        if country_code:
            country = (
                self.env["res.country"].search([("code", "=", country_code)], limit=1)
                or country
            )
        return self.env["res.country.state"].search(
            [("code", "=", code), ("country_id", "=", country.id)], limit=1
        )

    def action_resolve(self):
        self.ensure_one()
        if not self.env["property.data.source"].search_count([("active", "=", True)]):
            raise UserError(
                _(
                    "No active property data source is configured. "
                    "Install a connector (e.g. Census, Realie) and add a "
                    "source under Property Data > Configuration."
                )
            )
        errors = self._resolve(force=True)
        if errors:
            if not self.fetched_on:
                # Nothing resolved at all - surface the underlying cause.
                raise UserError(errors[0][1])
            # Partial success: note the skipped sources without blocking.
            skipped = "\n".join(f"- {s.name}: {m}" for s, m in errors)
            self.message_post(
                body=_("Some property data sources were skipped:") + "\n" + skipped
            )
        return True
