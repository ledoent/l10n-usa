# Copyright (C) 2019 Odoo GAP
# Copyright (C) 2019 Open Source Integrators
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo.tests.common import TransactionCase

_logger = logging.getLogger("us_gaap")


class TestChartAcount(TransactionCase):
    def with_context(self, *args, **kwargs):
        context = dict(args[0] if args else self.env.context, **kwargs)
        self.env = self.env(context=context)
        return self

    def test_basic(self):
        existing = self.env.company
        existing_chart = existing.chart_template
        existing_paperformat = existing.paperformat_id
        accounts = self.env["account.account"].with_company(existing)
        existing_accounts = accounts.search([("company_ids", "in", existing.id)])
        _logger.debug("Creating chart of account")
        self.company = self.env["res.company"].create({"name": "US test company"})
        self.env.ref("base.group_multi_company").write(
            {"user_ids": [(4, self.env.uid)]}
        )
        self.env.user.write(
            {"company_ids": [(4, self.company.id)], "company_id": self.company.id}
        )
        self.env["account.chart.template"].try_loading(
            template_code="us_gaap", company=self.company, install_demo=False
        )
        self.assertEqual(self.company.chart_template, "us_gaap")
        self.assertEqual(existing.chart_template, existing_chart)
        self.assertEqual(existing.paperformat_id, existing_paperformat)
        self.assertEqual(
            accounts.search([("company_ids", "in", existing.id)]), existing_accounts
        )
        # 20.0 shares accounts across companies: account.account.company_id is
        # gone in favour of company_ids, and `code` is no longer stored at all
        # (the stored column is code_store) because it is company-dependent.
        # Both together mean a code lookup only resolves with the company in
        # context, which is what with_company supplies.
        accounts = self.env["account.account"].with_company(self.company)
        bank_account = accounts.search(
            [("code", "=", "111102"), ("company_ids", "in", self.company.id)]
        )
        liquidity_transfer = accounts.search(
            [("code", "=", "111701"), ("company_ids", "in", self.company.id)]
        )
        finished_goods = accounts.search(
            [("code", "=", "133000"), ("company_ids", "in", self.company.id)]
        )
        self.assertEqual(bank_account.name, "Bank Suspense Account")
        # Core generates this account from transfer_account_code_prefix rather
        # than from the chart CSV, and 20.0 renamed it: chart_template.py:905
        # now reads _("Funds in Transit"). (The docstring 18 lines below it
        # still says "Liquidity Transfer Account" — stale upstream, not a clue.)
        self.assertEqual(liquidity_transfer.name, "Funds in Transit")
        self.assertEqual(finished_goods.name, "Finished Goods")
