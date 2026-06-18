# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class L10nUs1099Box(models.Model):
    _name = "l10n.us.1099.box"
    _description = "1099 Form Box"
    _order = "form, code"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(required=True, help="Box number on the form, e.g. 1.")
    form = fields.Selection(
        [("nec", "1099-NEC"), ("misc", "1099-MISC")],
        required=True,
    )
    applies_to_corporations = fields.Boolean(
        string="Reportable to Corporations by Default",
        help="Default for accounts mapped to this box: payments are reportable "
        "even when the payee is a corporation (e.g. attorney fees, medical "
        "and health-care payments).",
    )
    threshold_ids = fields.One2many(
        "l10n.us.1099.threshold", "box_id", string="Thresholds"
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "form_code_uniq",
            "unique(form, code)",
            "A box number must be unique per form.",
        )
    ]

    @api.depends("form", "code", "name")
    def _compute_display_name(self):
        forms = dict(self._fields["form"].selection)
        for box in self:
            box.display_name = "%s Box %s - %s" % (
                forms.get(box.form, box.form or ""),
                box.code or "",
                box.name or "",
            )

    def _threshold_for_year(self, year):
        """Return the reporting threshold effective for the given calendar
        year (the latest threshold whose start date is on/before year-end)."""
        self.ensure_one()
        year_end = fields.Date.to_date("%04d-12-31" % year)
        effective = self.threshold_ids.filtered(
            lambda t: t.date_from <= year_end
        ).sorted("date_from")
        return effective[-1].amount if effective else 0.0
