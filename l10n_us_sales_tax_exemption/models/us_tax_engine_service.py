# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, models


class UsTaxEngineService(models.AbstractModel):
    _inherit = "us.tax.engine.service"

    @api.model
    def _get_customer_exemption(self, partner_id, state, doc_date, company_id=False):
        """Return the reason code of a valid exemption certificate, if any.

        Looks up a certificate held by the customer in ``company_id`` (or a
        company-blank global certificate) that covers ``state`` and is valid on
        ``doc_date`` (effective, not expired, not revoked). v1 fully exempts the
        sale; product-conditional exemption is a future refinement.
        """
        if not partner_id or not state:
            return False
        domain = [
            ("partner_id", "=", partner_id),
            ("state", "=", "valid"),
            ("state_ids", "in", state.id),
            ("effective_date", "<=", doc_date),
            "|",
            ("expiry_date", "=", False),
            ("expiry_date", ">=", doc_date),
        ]
        if company_id:
            # Match the company's own certificates or company-blank (global) ones.
            domain.append(("company_id", "in", [company_id, False]))
        exemption = self.env["us.tax.exemption"].search(domain, limit=1)
        return exemption.reason_id.code if exemption else False
