# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class PropertyConstraint(models.Model):
    """A regulatory / construction constraint that applies to a property.

    Used to answer "can this job be done, and what compliance attaches?" for a
    lead - historic district, EPA pre-1978 lead (RRP) rule, FEMA flood zone,
    wetlands, zoning overlay. Rows are produced by sources advertising the
    ``constraints`` capability or derived in-base from already-resolved fields
    (e.g. the lead rule from ``year_built``).
    """

    _name = "property.constraint"
    _description = "Property Constraint"
    _order = "applies desc, severity desc, code"

    record_id = fields.Many2one(
        "property.record", required=True, ondelete="cascade", index=True
    )
    code = fields.Char(required=True, help="Stable machine code, e.g. epa_rrp_lead")
    name = fields.Char(required=True, translate=True)
    severity = fields.Selection(
        [("info", "Info"), ("warning", "Warning"), ("blocking", "Blocking")],
        default="info",
        required=True,
    )
    applies = fields.Boolean(
        default=True,
        help="Whether the constraint is actually in effect for this property "
        "(vs. checked and found not to apply).",
    )
    details = fields.Char()
    url = fields.Char(string="Reference")
    source_id = fields.Many2one(
        "property.data.source",
        ondelete="set null",
        help="Empty for constraints derived in-base from property fields.",
    )
