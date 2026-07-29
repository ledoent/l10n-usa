# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxExemptionVerification(models.Model):
    _name = "us.tax.exemption.verification"
    _description = "US Tax Exemption Verification"
    _order = "verified_on desc, id desc"
    _rec_name = "display_name"

    exemption_id = fields.Many2one(
        "us.tax.exemption",
        required=True,
        index=True,
        ondelete="cascade",
    )
    partner_id = fields.Many2one(
        related="exemption_id.partner_id", store=True, string="Customer"
    )
    verifier_id = fields.Many2one("us.tax.exemption.verifier", ondelete="restrict")
    verifier_code = fields.Char(
        readonly=True,
        help="Code of the source at the time of the check, kept even if the "
        "verifier record is later renamed or removed.",
    )
    mode = fields.Selection(
        [
            ("api", "Real-time API"),
            ("batch", "Batch submission"),
            ("manual", "Manual check"),
        ],
        readonly=True,
    )
    state_id = fields.Many2one("res.country.state", string="State Checked")
    result = fields.Selection(
        [
            ("verified", "Verified"),
            ("not_found", "Not Found"),
            ("inconclusive", "Inconclusive"),
            ("pending", "Pending"),
        ],
        required=True,
        readonly=True,
    )
    reference = fields.Char(readonly=True, help="Identifier the source matched on.")
    detail = fields.Char(readonly=True)
    payload = fields.Text(
        readonly=True, help="Raw response, kept verbatim as evidence."
    )
    evidence = fields.Binary(
        attachment=True,
        help="Screenshot or letter, for sources with nothing machine-readable "
        "behind them.",
    )
    evidence_filename = fields.Char()
    verified_by = fields.Many2one(
        "res.users", required=True, readonly=True, default=lambda s: s.env.user
    )
    verified_on = fields.Datetime(
        required=True, readonly=True, default=fields.Datetime.now
    )
    company_id = fields.Many2one(
        "res.company", default=lambda s: s.env.company, readonly=True
    )

    @api.depends("exemption_id", "result", "verified_on")
    def _compute_display_name(self):
        for rec in self:
            label = dict(self._fields["result"].selection).get(rec.result, "")
            when = fields.Date.to_string(rec.verified_on) if rec.verified_on else ""
            rec.display_name = f"{label} — {when}" if when else label
