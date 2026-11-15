# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import UserError


class UsTaxExemptionVerifier(models.Model):
    _name = "us.tax.exemption.verifier"
    _description = "US Tax Exemption Verifier"
    _order = "priority, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, index=True)
    mode = fields.Selection(
        [
            ("api", "Real-time API"),
            ("batch", "Batch submission"),
            ("manual", "Manual check"),
        ],
        required=True,
        default="manual",
        help="How this source answers. Batch sources accept a request and "
        "reply out of band, so a batch verification stays pending until the "
        "reply is reconciled.",
    )
    state_ids = fields.Many2many(
        "res.country.state",
        string="States Covered",
        domain=[("country_id.code", "=", "US")],
        help="Leave empty to offer this verifier for every state.",
    )
    active = fields.Boolean(default=True)
    priority = fields.Integer(
        default=10,
        help="Lowest first. A state-specific source should outrank the "
        "manual fallback.",
    )
    timeout = fields.Integer(default=10, help="Seconds before giving up.")
    api_key_param = fields.Char(
        help="System parameter holding the credential, when the source needs "
        "one. Texas works without a key against the state open-data portal "
        "and uses the Comptroller API when a key is set.",
    )
    description = fields.Text(translate=True)

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Verifier code must be unique."),
    ]

    def get_api_key(self):
        self.ensure_one()
        if not self.api_key_param:
            return ""
        return self.env["ir.config_parameter"].sudo().get_param(self.api_key_param, "")

    def _open_data_headers(self):
        """Socrata raises the rate limit for a token but works without one."""
        self.ensure_one()
        token = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("l10n_us_tax.socrata_app_token", "")
        )
        return {"X-App-Token": token} if token else {}

    @api.model
    def _verifier_classes(self):
        """The {code: service class} registry.

        Extension point, mirroring the engine's ``_provider_service_classes``:
        an addon adds a state's verifier by overriding this and updating the
        dict from ``super()``, with no edit here.
        """
        from ..services import verifier_manual, verifier_texas  # noqa: PLC0415

        return {
            verifier_manual.VerifierManual.CODE: verifier_manual.VerifierManual,
            verifier_texas.VerifierTexas.CODE: verifier_texas.VerifierTexas,
        }

    def _get_service(self):
        self.ensure_one()
        cls = self._verifier_classes().get(self.code)
        if not cls:
            raise UserError(self.env._('No verifier service for code "%s".', self.code))
        return cls(self)

    @api.model
    def _for_state(self, state):
        """Best verifier for ``state`` — most specific wins, manual last."""
        candidates = self.search(
            [
                "|",
                ("state_ids", "=", False),
                ("state_ids", "in", state.id if state else []),
            ]
        )
        specific = candidates.filtered(lambda v: v.state_ids)
        return (specific or candidates)[:1]
