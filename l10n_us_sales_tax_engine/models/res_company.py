# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_payable_account_id = fields.Many2one(
        "account.account",
        string="Sales Tax Payable Account",
        domain="[('account_type', '=', 'liability_current')]",
        help="Liability account collected US sales tax accrues to. The engine "
        "books each per-jurisdiction tax line here so it can be reconciled and "
        "remitted; auto-created on first use if left empty.",
    )

    def get_us_tax_payable_account(self):
        """Return (find-or-create) the company's sales-tax-payable account.

        Collected tax must book to a reconcilable liability, not income. Users
        can pick the account in Settings; otherwise a dedicated 'US Sales Tax
        Payable' current-liability account is created once and reused.
        """
        self.ensure_one()
        if self.us_tax_payable_account_id:
            return self.us_tax_payable_account_id
        Account = self.env["account.account"].sudo().with_company(self)
        acc = Account.search(
            [
                ("account_type", "=", "liability_current"),
                ("name", "=", "US Sales Tax Payable"),
                ("company_ids", "in", self.id),
            ],
            limit=1,
        )
        if not acc:
            existing = set(
                Account.search([("company_ids", "in", self.id)]).mapped("code")
            )
            code = 251100
            while str(code) in existing:
                code += 1
            acc = Account.create(
                {
                    "name": "US Sales Tax Payable",
                    "code": str(code),
                    "account_type": "liability_current",
                    "company_ids": [(4, self.id)],
                }
            )
        self.sudo().us_tax_payable_account_id = acc
        return acc
