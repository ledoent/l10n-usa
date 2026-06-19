# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, models

# Federal RRP rule applies to housing built before this year.
EPA_RRP_CUTOFF_YEAR = 1978


class PropertyRecord(models.Model):
    _inherit = "property.record"

    def _derive_constraints(self):
        """Add US construction constraints inferred from property fields.

        These are free derivations - no external API call. Currently the EPA
        Renovation, Repair and Painting (RRP) lead rule, which a home-
        improvement contractor must follow on pre-1978 housing.
        """
        items = super()._derive_constraints()
        if self.year_built and self.year_built < EPA_RRP_CUTOFF_YEAR:
            items.append(
                {
                    "code": "epa_rrp_lead",
                    "name": _("EPA RRP - pre-1978 lead-safe practices"),
                    "severity": "warning",
                    "applies": True,
                    "details": _(
                        "Built %s. Federal Renovation, Repair and Painting "
                        "(RRP) Rule requires a certified renovator and "
                        "lead-safe work practices."
                    )
                    % self.year_built,
                    "url": "https://www.epa.gov/lead/"
                    "renovation-repair-and-painting-program",
                }
            )
        return items
