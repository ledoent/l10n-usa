# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxExemptionValidity(models.Model):
    _name = "us.tax.exemption.validity"
    _description = "US Sales Tax Exemption Validity Rule"
    _order = "state_id, reason_id"

    state_id = fields.Many2one(
        "res.country.state",
        string="State",
        domain=[("country_id.code", "=", "US")],
        help="Leave empty to apply to every state.",
    )
    reason_id = fields.Many2one(
        "us.tax.exemption.reason",
        string="Exemption Reason",
        help="Leave empty to apply to every reason.",
    )
    validity_years = fields.Integer(
        default=3,
        help="How long a certificate issued under this rule stays valid.",
    )
    never_expires = fields.Boolean(
        help="Some states issue certificates with no expiry. A certificate "
        "matched by this rule is given no expiry date and is never picked up "
        "for renewal.",
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        (
            "state_reason_unique",
            "UNIQUE(state_id, reason_id)",
            "There is already a validity rule for this state and reason.",
        ),
    ]

    @api.constrains("validity_years", "never_expires")
    def _check_validity_years(self):
        for rec in self:
            if not rec.never_expires and rec.validity_years <= 0:
                raise ValidationError(
                    self.env._(
                        "A validity rule needs a positive number of years, "
                        "unless it never expires."
                    )
                )

    @api.depends("state_id", "reason_id", "validity_years", "never_expires")
    def _compute_display_name(self):
        for rec in self:
            scope = " / ".join(
                filter(
                    None,
                    [
                        rec.state_id.code or self.env._("Any state"),
                        rec.reason_id.name or self.env._("Any reason"),
                    ],
                )
            )
            term = (
                self.env._("never expires")
                if rec.never_expires
                else self.env._("%s years", rec.validity_years)
            )
            rec.display_name = f"{scope} — {term}"

    @api.model
    def _match(self, state, reason):
        """The most specific rule covering ``state`` and ``reason``.

        Exact match first, then a state-wide rule, then a reason-wide one.
        Returns an empty recordset when nothing matches, which sends the
        caller on to the reason's own term and then the company default.
        """
        for domain in (
            [
                ("state_id", "=", state.id if state else False),
                ("reason_id", "=", reason.id if reason else False),
            ],
            [
                ("state_id", "=", state.id if state else False),
                ("reason_id", "=", False),
            ],
            [
                ("state_id", "=", False),
                ("reason_id", "=", reason.id if reason else False),
            ],
        ):
            rule = self.search(domain, limit=1)
            if rule:
                return rule
        return self.browse()
