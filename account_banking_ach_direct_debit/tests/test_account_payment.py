# Copyright (C) 2021 - TODAY, Open Source Integrators
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class TestPayment(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref(
            "account_payment_order.group_account_payment"
        )
        cls.company = cls.company_data["company"]
        cls.partner = cls.partner_a
        cls.company.legal_id_number = "12-3456789"
        cls.ach_payment_method_01 = cls.env.ref(
            "account_banking_ach_direct_debit.ach_direct_debit"
        )
        bank_account = cls.env["res.partner.bank"].create(
            {
                "account_number": "0023032234211123",
                "partner_id": cls.company.partner_id.id,
                "bank_name": "ACME Bank",
                "country_id": cls.env.ref("base.us").id,
                "clearing_number": "021000021",
                "company_id": cls.company.id,
            }
        )
        cls.journal_c1 = cls.company_data["default_journal_bank"]
        cls.journal_c1.bank_account_id = bank_account
        cls.payment_mode_c1 = cls.env["account.payment.mode"].create(
            {
                "name": "ACH Direct Debit",
                "bank_account_link": "variable",
                "payment_method_id": cls.ach_payment_method_01.id,
                "company_id": cls.company.id,
                "variable_journal_ids": [Command.set(cls.journal_c1.ids)],
            }
        )
        cls.partner.customer_payment_mode_id = cls.payment_mode_c1
        cls.customer_bank = cls.env["res.partner.bank"].create(
            {
                "account_number": "123456789",
                "partner_id": cls.partner.id,
                "bank_name": "ACME Bank",
                "country_id": cls.env.ref("base.us").id,
                "clearing_number": "021000021",
            }
        )
        cls.mandate = cls.env["account.banking.mandate"].create(
            {
                "partner_bank_id": cls.customer_bank.id,
                "signature_date": fields.Date.today() - timedelta(days=20),
                "company_id": cls.company.id,
                "format": "ach",
                "type": "recurrent",
                "recurrent_sequence_type": "first",
            }
        )
        cls.mandate.validate()

    def test_account_payment_order(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.today() - timedelta(days=15),
                "invoice_date_due": fields.Date.today() - timedelta(days=1),
                "payment_mode_id": self.payment_mode_c1.id,
                "mandate_id": self.mandate.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "ACH debit fixture",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "quantity": 1,
                            "price_unit": 125,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        order = self.env["account.payment.order"].create(
            {
                "payment_type": "inbound",
                "payment_mode_id": self.payment_mode_c1.id,
                "journal_id": self.journal_c1.id,
            }
        )
        wizard = (
            self.env["account.payment.line.create"]
            .with_context(active_model="account.payment.order", active_id=order.id)
            .create(
                {
                    "date_type": "due",
                    "due_on": "<=",
                    "filter_date": fields.Date.today(),
                    "payment_mode": "any",
                    "target_move": "posted",
                }
            )
        )
        wizard.populate()
        receivable = invoice.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )
        self.assertTrue(receivable <= wizard.move_line_ids)
        wizard.move_line_ids = receivable
        wizard.create_payment_lines()
        self.assertEqual(len(order.payment_line_ids), 1)
        order.draft2open()
        payload, filename = order.generate_payment_file()
        self.assertTrue(filename.endswith(".txt"))
        self.assertIn(b"62702100002", payload)
        self.assertIn(b"0000012500", payload)
        order.open2generated()
        order.generated2uploaded()
        self.assertEqual(order.state, "uploaded")
        self.assertEqual(self.mandate.recurrent_sequence_type, "recurring")
        self.assertEqual(self.mandate.last_debit_date, fields.Date.today())
        self.assertEqual(invoice.amount_residual, 0)

    def test_expired_mandate_is_rejected(self):
        self.mandate.state = "expired"
        order = self.env["account.payment.order"].new({"payment_type": "inbound"})
        payment = self.env["account.payment"].new(
            {"partner_id": self.partner.id, "mandate_id": self.mandate.id}
        )
        with self.assertRaisesRegex(UserError, "has expired"):
            order.validate_mandates(payment)

    def test_used_oneoff_mandate_is_rejected(self):
        self.mandate.write({"type": "oneoff", "last_debit_date": fields.Date.today()})
        order = self.env["account.payment.order"].new({"payment_type": "inbound"})
        payment = self.env["account.payment"].new(
            {"partner_id": self.partner.id, "mandate_id": self.mandate.id}
        )
        with self.assertRaisesRegex(UserError, "last debit date"):
            order.validate_mandates(payment)
