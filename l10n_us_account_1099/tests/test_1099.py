# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import Command
from odoo.tests.common import Form, TransactionCase


class TestUs1099(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.year = 2025  # $600 threshold era
        cls.box_nec_1 = cls.env.ref("l10n_us_account_1099.box_nec_1")
        cls.box_misc_1 = cls.env.ref("l10n_us_account_1099.box_misc_1")
        cls.box_misc_6 = cls.env.ref("l10n_us_account_1099.box_misc_6")
        cls.engine = cls.env["l10n.us.1099.engine"]

        # Expense accounts standing in for payment categories
        cls.acc_services = cls._account("US1099SVC", cls.box_nec_1, False)
        cls.acc_legal = cls._account("US1099LEG", cls.box_nec_1, True)
        cls.acc_rent = cls._account("US1099RENT", cls.box_misc_1, False)
        cls.acc_goods = cls._account("US1099GOODS", False, False)

        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "purchase"), ("company_id", "=", cls.company.id)],
            limit=1,
        ) or cls.env["account.journal"].create(
            {
                "name": "Test Purchases",
                "code": "TPUR",
                "type": "purchase",
                "company_id": cls.company.id,
            }
        )

        # Payees with different W-9 classifications
        cls.individual = cls._partner("Jane Contractor", "individual")
        cls.ccorp = cls._partner("Mega Corp", "c_corp")
        cls.llc_p = cls._partner("Builders LLC", "llc", llc="p")
        cls.llc_c = cls._partner("Holdings LLC", "llc", llc="c")

    @classmethod
    def _account(cls, code, box, corp):
        return cls.env["account.account"].create(
            {
                "name": code,
                "code": code,
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
                "us_1099_box_id": box.id if box else False,
                "us_1099_corporate_reportable": corp,
            }
        )

    @classmethod
    def _partner(cls, name, classification, llc=False):
        return cls.env["res.partner"].create(
            {
                "name": name,
                "us_1099_tax_classification": classification,
                "us_1099_llc_tax_class": llc or False,
                "us_1099_tin_type": "ein",
                "vat": "12-3456789",
            }
        )

    def _bill(self, partner, account, amount, excluded=False, refund=False):
        move = self.env["account.move"].create(
            {
                "move_type": "in_refund" if refund else "in_invoice",
                "partner_id": partner.id,
                "invoice_date": "%04d-06-01" % self.year,
                "journal_id": self.journal.id,
                "us_1099_excluded": excluded,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "test",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": account.id,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        move.action_post()
        return move

    # ---- classification ----
    def test_is_corporation(self):
        self.assertFalse(self.individual.us_1099_is_corporation)
        self.assertTrue(self.ccorp.us_1099_is_corporation)
        self.assertFalse(self.llc_p.us_1099_is_corporation)
        self.assertTrue(self.llc_c.us_1099_is_corporation)

    # ---- line-level determination ----
    def test_line_reportable_matrix(self):
        ind = self._bill(self.individual, self.acc_services, 1000)
        ind_line = ind.line_ids.filtered(lambda x: x.account_id == self.acc_services)
        self.assertTrue(self.engine._line_reportable(ind_line))

        # Corp + ordinary services -> exempt
        corp = self._bill(self.ccorp, self.acc_services, 1000)
        corp_line = corp.line_ids.filtered(lambda x: x.account_id == self.acc_services)
        self.assertFalse(self.engine._line_reportable(corp_line))

        # Corp + legal fees -> reportable (override)
        legal = self._bill(self.ccorp, self.acc_legal, 1000)
        legal_line = legal.line_ids.filtered(lambda x: x.account_id == self.acc_legal)
        self.assertTrue(self.engine._line_reportable(legal_line))

        # Goods (no box) -> not reportable
        goods = self._bill(self.individual, self.acc_goods, 1000)
        goods_line = goods.line_ids.filtered(lambda x: x.account_id == self.acc_goods)
        self.assertFalse(self.engine._line_reportable(goods_line))

        # Card-excluded bill -> not reportable
        carded = self._bill(self.individual, self.acc_services, 1000, excluded=True)
        carded_line = carded.line_ids.filtered(
            lambda x: x.account_id == self.acc_services
        )
        self.assertFalse(self.engine._line_reportable(carded_line))

    # ---- aggregation + threshold ----
    def test_collect_and_threshold(self):
        self._bill(self.individual, self.acc_services, 400)
        self._bill(self.individual, self.acc_services, 300)  # total 700 > 600
        self._bill(self.llc_p, self.acc_rent, 500)  # below 600
        buckets = self.engine._collect(self.company, self.year)
        self.assertEqual(
            buckets[(self.individual.id, self.box_nec_1.id)], 700
        )
        self.assertEqual(buckets[(self.llc_p.id, self.box_misc_1.id)], 500)

    def test_threshold_effective_dating(self):
        self.assertEqual(self.box_nec_1._threshold_for_year(2025), 600)
        self.assertEqual(self.box_nec_1._threshold_for_year(2026), 2000)
        self.assertEqual(self.box_misc_6._threshold_for_year(2026), 2000)

    # ---- generate wizard + reportable flag ----
    def test_generate_and_reportable_flag(self):
        self._bill(self.individual, self.acc_services, 700)  # reportable
        self._bill(self.llc_p, self.acc_rent, 500)  # below threshold
        self._bill(self.ccorp, self.acc_services, 5000)  # corp exempt -> excluded
        wizard = self.env["l10n.us.1099.generate"].create(
            {"year": self.year, "company_id": self.company.id}
        )
        wizard.action_generate()
        lines = self.env["l10n.us.1099.line"].search(
            [("company_id", "=", self.company.id), ("year", "=", self.year)]
        )
        by_partner = {line.partner_id: line for line in lines}
        self.assertNotIn(self.ccorp, by_partner)  # corp services never bucketed
        self.assertTrue(by_partner[self.individual].reportable)
        self.assertFalse(by_partner[self.llc_p].reportable)

    # ---- CSV ----
    def test_build_csv(self):
        self._bill(self.individual, self.acc_services, 700)
        self._bill(self.llc_p, self.acc_rent, 500)
        self.env["l10n.us.1099.generate"].create(
            {"year": self.year, "company_id": self.company.id}
        ).action_generate()
        lines = self.env["l10n.us.1099.line"].search(
            [("year", "=", self.year)]
        )
        csv_text = lines._build_csv()
        self.assertIn("Payee,TIN Type,TIN,Form,Box,Description,Amount", csv_text)
        self.assertIn("Jane Contractor", csv_text)  # reportable
        self.assertNotIn("Builders LLC", csv_text)  # below threshold, excluded
        action = lines.action_export_csv()
        self.assertEqual(action["res_model"], "l10n.us.1099.export")

    # ---- misc coverage ----
    def test_account_box_onchange_defaults_corp_flag(self):
        with Form(self.env["account.account"]) as form:
            form.name = "Onchange Acct"
            form.code = "US1099OC"
            form.account_type = "expense"
            form.us_1099_box_id = self.box_misc_6  # corp-reportable by default
            self.assertTrue(form.us_1099_corporate_reportable)
            form.us_1099_box_id = self.box_nec_1  # not corp-reportable
            self.assertFalse(form.us_1099_corporate_reportable)

    def test_box_display_name(self):
        self.assertEqual(
            self.box_nec_1.display_name, "1099-NEC Box 1 - Nonemployee compensation"
        )

    def test_line_without_partner_not_reportable(self):
        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.acc_services.id,
                            "name": "no partner",
                            "debit": 100,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.acc_goods.id,
                            "name": "balance",
                            "credit": 100,
                        }
                    ),
                ],
            }
        )
        line = move.line_ids.filtered(lambda x: x.account_id == self.acc_services)
        self.assertFalse(line.partner_id)
        self.assertFalse(self.engine._line_reportable(line))

    def test_filer_base_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.env["l10n.us.1099.filer"].transmit(
                self.env["l10n.us.1099.line"]
            )
