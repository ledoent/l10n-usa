# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_previous_sale_tax_id = fields.Many2one(
        "account.tax",
        string="Default Sale Tax Before Adoption",
        help="The default sale tax this company had before the engine was "
        "adopted as its sale-tax source; restored by the companion action.",
    )
    us_tax_sale_tax_adopted = fields.Boolean(
        string="Engine Is the Sale-Tax Source",
        help="The company's default sale tax has been replaced by the 0% "
        "'pending calculation' placeholder.",
    )
    us_tax_payable_account_id = fields.Many2one(
        "account.account",
        string="Sales Tax Payable Account",
        domain="[('account_type', '=', 'liability_current')]",
        help="Liability account collected US sales tax accrues to, so it can "
        "be reconciled and remitted. Left empty, the engine reuses whatever "
        "account the chart of accounts already books sales tax to.",
    )

    def _us_tax_account_from_chart(self):
        """The account this company's chart already books sales tax to.

        Charts ship a tax account (``251000`` in the generic chart) and their
        taxes point at it. Creating a second liability alongside it would split
        the sales-tax balance across two accounts for no reason, so look there
        first and only fall back to creating one when a company has no sale tax
        configured at all.
        """
        self.ensure_one()

        def _tax_account(tax):
            lines = tax.invoice_repartition_line_ids.filtered(
                lambda r: r.repartition_type == "tax" and r.account_id
            )
            return lines[:1].account_id

        default_tax = self.account_sale_tax_id
        if default_tax:
            account = _tax_account(default_tax)
            if account:
                return account

        for tax in (
            self.env["account.tax"]
            .sudo()
            .search([("company_id", "=", self.id), ("type_tax_use", "=", "sale")])
        ):
            account = _tax_account(tax)
            if account:
                return account
        return self.env["account.account"]

    def get_us_tax_payable_account(self):
        """The account collected US sales tax books to.

        Explicit configuration wins; otherwise reuse the chart's own tax
        account. Only a company with no sale tax at all gets a new account,
        and the resolved choice is written back to the setting so it is
        visible and overridable rather than implicit.
        """
        self.ensure_one()
        if self.us_tax_payable_account_id:
            return self.us_tax_payable_account_id

        account = self._us_tax_account_from_chart()
        if not account:
            Account = self.env["account.account"].sudo().with_company(self)
            account = Account.search(
                [
                    ("account_type", "=", "liability_current"),
                    ("name", "=", "US Sales Tax Payable"),
                    ("company_ids", "in", self.id),
                ],
                limit=1,
            )
        if not account:
            existing = set(
                self.env["account.account"]
                .sudo()
                .with_company(self)
                .search([("company_ids", "in", self.id)])
                .mapped("code")
            )
            code = 251100
            while str(code) in existing:
                code += 1
            account = (
                self.env["account.account"]
                .sudo()
                .with_company(self)
                .create(
                    {
                        "name": "US Sales Tax Payable",
                        "code": str(code),
                        "account_type": "liability_current",
                        "company_ids": [(4, self.id)],
                    }
                )
            )
            _logger.info(
                "US Tax: no sale tax account found for %s; created %s (%s).",
                self.display_name,
                account.code,
                account.name,
            )
        self.sudo().us_tax_payable_account_id = account
        return account

    def _get_us_tax_pending_tax(self):
        """The company's 0% 'pending calculation' placeholder sale tax.

        Distinct from the shared exempt tax on purpose: 'exempt' is an
        evaluated outcome the return reporting keys on, while 'pending' only
        means the engine has not run yet on this document. Sharing one record
        would fold un-evaluated quotations into exempt-sales metrics.
        """
        self.ensure_one()
        name = "US Sales Tax (pending calculation)"
        Tax = self.env["account.tax"].sudo()
        tax = Tax.search(
            [
                ("name", "=", name),
                ("type_tax_use", "=", "sale"),
                ("company_id", "=", self.id),
            ],
            limit=1,
        )
        if not tax:
            svc = self.env["us.tax.engine.service"]
            tax = Tax.create(
                {
                    "name": name,
                    "type_tax_use": "sale",
                    "amount_type": "percent",
                    "amount": 0.0,
                    "company_id": self.id,
                    "country_id": svc._us_tax_country_id(self),
                    "tax_group_id": svc._get_us_tax_group(self).id,
                    "description": (
                        "Placeholder shown until the US Sales Tax Engine "
                        "computes the real per-jurisdiction taxes."
                    ),
                }
            )
        return tax

    def action_us_tax_adopt_sale_tax_source(self):
        """Make the engine this company's sale-tax source.

        The chart's default sale tax (15% on the generic chart) only ever
        DISPLAYS on an engine-active company - the engine replaces it at every
        calculation point - but it shows on quotations and website carts
        before the first calculation, which misquotes the customer. Swap it
        for the 0% pending placeholder, on the company default and on the
        products that carry it, remembering the original for restore.

        Deliberately an explicit per-company action, not an install hook:
        install is not activation, other companies in the DB may not be US,
        and an install-time rewrite could not be undone by uninstall.
        """
        for company in self:
            if company.us_tax_sale_tax_adopted:
                continue
            pending = company._get_us_tax_pending_tax()
            previous = company.account_sale_tax_id
            company.write(
                {
                    "us_tax_previous_sale_tax_id": previous.id or False,
                    "us_tax_sale_tax_adopted": True,
                    "account_sale_tax_id": pending.id,
                }
            )
            if previous:
                products = (
                    self.env["product.template"]
                    .sudo()
                    .with_company(company)
                    .search([("taxes_id", "in", previous.id)])
                )
                products.write({"taxes_id": [(3, previous.id), (4, pending.id)]})
                _logger.info(
                    "US Tax: %s adopted as sale-tax source for %s; default and "
                    "%d product(s) moved from %s to the pending placeholder.",
                    pending.name,
                    company.display_name,
                    len(products),
                    previous.name,
                )

    def action_us_tax_restore_sale_tax_source(self):
        """Undo ``action_us_tax_adopt_sale_tax_source`` for this company."""
        for company in self:
            if not company.us_tax_sale_tax_adopted:
                continue
            pending = company._get_us_tax_pending_tax()
            previous = company.us_tax_previous_sale_tax_id
            company.write(
                {
                    "account_sale_tax_id": previous.id or False,
                    "us_tax_previous_sale_tax_id": False,
                    "us_tax_sale_tax_adopted": False,
                }
            )
            if previous:
                products = (
                    self.env["product.template"]
                    .sudo()
                    .with_company(company)
                    .search([("taxes_id", "in", pending.id)])
                )
                products.write({"taxes_id": [(3, pending.id), (4, previous.id)]})
