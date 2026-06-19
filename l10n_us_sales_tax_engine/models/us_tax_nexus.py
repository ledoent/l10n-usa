# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxNexus(models.Model):
    _name = "us.tax.nexus"
    _description = "US Tax Nexus Configuration"
    _check_company_auto = True
    _order = "company_id, state_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda s: s.env.company,
    )
    state_id = fields.Many2one(
        "res.country.state",
        required=True,
        domain=[("country_id.code", "=", "US")],
    )
    active = fields.Boolean(default=True)
    start_date = fields.Date(
        help="Date when economic nexus was established in this state.",
    )
    threshold_amount = fields.Float(
        help="Economic nexus threshold in USD (informational for MVP).",
    )
    threshold_transactions = fields.Integer(
        help="Transaction count threshold (informational for MVP).",
    )
    single_local_rate_elected = fields.Boolean(
        string="Single Local Use Rate Elected",
        help="Remote seller has elected this state's single local use tax rate "
        "(e.g. Texas) in lieu of the actual local rate at each destination. "
        "Only valid for an interstate (remote) seller into this state.",
    )
    single_local_rate = fields.Float(
        string="Single Local Use Rate",
        digits=(7, 6),
        help="The single local use tax rate as a decimal (e.g. 0.0175 for the "
        "Texas 1.75% rate). The state sets this annually.",
    )
    notes = fields.Text()

    _sql_constraints = [
        (
            "company_state_unique",
            "UNIQUE(company_id, state_id)",
            "A nexus record for this company and state already exists.",
        ),
    ]

    @api.model
    def has_nexus(self, company_id, state_id):
        """Check if a company has active nexus in a given state."""
        return bool(
            self.search(
                [
                    ("company_id", "=", company_id),
                    ("state_id", "=", state_id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )

    @api.model
    def get_single_local_rate(self, company_id, state_id):
        """Elected single local use rate for this company+state, else None.

        Returns the configured decimal rate only when the election is active
        and a non-zero rate is set; the caller has already confirmed the sale
        is interstate (remote) into this state.
        """
        nx = self.search(
            [
                ("company_id", "=", company_id),
                ("state_id", "=", state_id),
                ("active", "=", True),
                ("single_local_rate_elected", "=", True),
            ],
            limit=1,
        )
        return nx.single_local_rate if (nx and nx.single_local_rate) else None
