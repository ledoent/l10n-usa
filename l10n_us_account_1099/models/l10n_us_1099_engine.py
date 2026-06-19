# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class L10nUs1099Engine(models.AbstractModel):
    """The 1099 reportability determination engine.

    Reportability is *not* "is the payee a company?". It is the intersection
    of the payee's W-9 tax classification, the payment category (driven by the
    expense account's box mapping), the payment method, and the effective-dated
    threshold -- with corporate-exemption overrides (attorney, medical, ...).

    This model holds the pure determination logic so it can be unit-tested and
    reused independently of the reporting wizard.
    """

    _name = "l10n.us.1099.engine"
    _description = "1099 Determination Engine"

    @api.model
    def _line_reportable(self, move_line):
        """Whether a single vendor-bill line is 1099-reportable."""
        account = move_line.account_id
        box = account.us_1099_box_id
        if not box:
            return False
        # Bills paid by card / third-party network are reported on 1099-K by
        # the processor and must be excluded here.
        if move_line.move_id.us_1099_excluded:
            return False
        partner = move_line.partner_id.commercial_partner_id
        if not partner:
            return False
        # Corporations are exempt unless the payment category overrides it
        # (legal/attorney fees, medical & health-care payments, ...).
        if partner.us_1099_is_corporation and not account.us_1099_corporate_reportable:
            return False
        return True

    @api.model
    def _collect(self, company, year):
        """Aggregate reportable amounts as {(partner_id, box_id): amount} for a
        company and calendar year, from posted vendor bills/refunds.

        v1 aggregates on an accrual basis (bill date). Cash-basis aggregation
        by payment date is a planned enhancement; the per-bill exclusion flag
        already covers the card/third-party-network case.
        """
        date_from = fields.Date.to_date("%04d-01-01" % year)
        date_to = fields.Date.to_date("%04d-12-31" % year)
        move_lines = self.env["account.move.line"].search(
            [
                ("parent_state", "=", "posted"),
                ("company_id", "=", company.id),
                ("move_id.move_type", "in", ("in_invoice", "in_refund")),
                ("move_id.us_1099_excluded", "=", False),
                ("date", ">=", date_from),
                ("date", "<=", date_to),
                ("account_id.us_1099_box_id", "!=", False),
                ("partner_id", "!=", False),
            ]
        )
        buckets = {}
        for line in move_lines:
            if not self._line_reportable(line):
                continue
            partner = line.partner_id.commercial_partner_id
            box = line.account_id.us_1099_box_id
            key = (partner.id, box.id)
            buckets[key] = buckets.get(key, 0.0) + line.balance
        return buckets
