# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .common import ZiftCommon
from .test_fee import _SEND, FeeFlowMixin


@tagged("post_install", "-at_install")
class TestZiftFeeAccounting(FeeFlowMixin, ZiftCommon, AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zift.journal_id = cls.company_data["default_journal_bank"]
        cls.zift.journal_id.inbound_payment_method_line_ids.filtered(
            lambda line: line.payment_provider_id == cls.zift
        ).payment_account_id = cls.inbound_payment_method_line.payment_account_id

    def test_fee_does_not_inflate_invoice_receipt_or_revenue(self):
        self._disable_post_process_patcher()
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner.id,
                "invoice_date": fields.Date.today(),
                "currency_id": self.currency.id,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Fictional rent",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "quantity": 1,
                            "price_unit": 100,
                            "tax_ids": [Command.clear()],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        self._update_transaction(self.tx, invoice_ids=[Command.set(invoice.ids)])
        quote, _send = self.quote()
        self.pay(quote)
        self._run_processing()
        self._run_post_processing()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(invoice.amount_total, 100)
        self.assertEqual(self.tx.payment_id.amount, 100)
        self.assertEqual(self.tx.payment_id.currency_id, self.currency)
        self.assertTrue(self.tx.payment_id.move_id)
        self.assertFalse(
            self.tx.payment_id.move_id.line_ids.filtered(
                lambda line: line.account_id.account_type in ("income", "income_other")
            )
        )

    def test_pending_bank_debit_does_not_reconcile_receivable(self):
        self._disable_post_process_patcher()
        instrument = dict(
            self.instrument, accountType="C", accountAccessory="011000015"
        )
        quote, _send = self.quote(instrument=instrument)
        with patch(
            _SEND,
            return_value=dict(self.ach_acceptance, amount="10000", feeAmount="325"),
        ):
            self.tx._zift_send_quoted_payment(instrument, quote["quote_id"], True)
        self._run_processing()
        self._run_post_processing()
        self.assertEqual(self.tx.state, "pending")
        self.assertFalse(self.tx.payment_id)
