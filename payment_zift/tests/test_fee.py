# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import ZiftCommon

_SEND = "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request"


class FeeFlowMixin:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.enable_process_patcher = False
        cls.instrument = {
            "token": "fictional-card-token",
            "accountType": "R",
            "accountAccessory": "1228",
            "holderName": "Fictional Payer",
        }

    def setUp(self):
        super().setUp()
        self.zift.zift_pass_fees = True
        self.tx = self._create_transaction("direct", amount=100)

    def quote(self, tx=None, instrument=None, fee="325"):
        with patch(
            _SEND,
            return_value={
                "responseType": "convenience-fee",
                "responseCode": "A01",
                "feeAmount": fee,
            },
        ) as send:
            result = (tx or self.tx)._zift_quote_fee(instrument or self.instrument)
        return result, send

    def pay(self, quote, tx=None, instrument=None, response=None):
        response = response or dict(self.card_approval, amount="10000", feeAmount="325")
        with patch(_SEND, return_value=response) as send:
            (tx or self.tx)._zift_send_quoted_payment(
                instrument or self.instrument, quote["quote_id"], True
            )
        return send


@tagged("post_install", "-at_install")
class TestZiftFee(FeeFlowMixin, ZiftCommon):
    def test_quote_principal_fee_and_total_are_separate(self):
        quote, send = self.quote()
        self.assertEqual(
            (quote["principal"], quote["fee"], quote["total"]), (100, 3.25, 103.25)
        )
        self.assertEqual(self.tx.amount, 100)
        self.assertEqual(
            send.call_args.kwargs["data"]["requestType"], "convenience-fee"
        )
        self.assertEqual(send.call_args.kwargs["data"]["amount"], 10000)
        self.assertFalse(self.tx.zift_fee_accepted_at)
        self.assertFalse(self.tx.zift_fee_processed)

    def test_zero_fee_is_valid_but_malformed_quotes_are_rejected(self):
        quote, _send = self.quote(fee="0")
        self.assertEqual(quote["total"], 100)
        for value in (None, "-1", "1.23", "NaN", True, "1000000000"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                self.quote(fee=value)

    def test_card_payment_consumes_quote_and_processes_native_data(self):
        quote, _send = self.quote()
        send = self.pay(quote)
        payload = send.call_args.kwargs["data"]
        self.assertEqual((payload["amount"], payload["feeAmount"]), (10000, 325))
        self.assertEqual(payload["requestType"], "sale")
        self.assertTrue(self.tx.zift_fee_accepted_at)
        self.assertTrue(self.tx.zift_fee_processed)
        self.assertEqual(self.tx.state, "draft")  # Native processing is asynchronous.
        with patch(_SEND) as replay, self.assertRaises(ValidationError):
            self.tx._zift_send_quoted_payment(self.instrument, quote["quote_id"], True)
        replay.assert_not_called()
        self._run_processing()
        self.assertEqual(self.tx.state, "done")
        self.assertEqual(self.tx.amount, 100)

    def test_ach_acceptance_stays_pending(self):
        instrument = dict(
            self.instrument, accountType="C", accountAccessory="011000015"
        )
        quote, _send = self.quote(instrument=instrument, fee="50")
        self.pay(
            quote,
            instrument=instrument,
            response=dict(self.ach_acceptance, amount="10000", feeAmount="50"),
        )
        self._run_processing()
        self.assertEqual(self.tx.state, "pending")
        self.assertFalse(self.tx.payment_id)

    def test_acceptance_and_current_quote_are_required(self):
        quote, _send = self.quote()
        with patch(_SEND) as send:
            for quote_id, accepted in (
                (None, True),
                ("forged", True),
                (quote["quote_id"], False),
                (quote["quote_id"], "true"),
            ):
                with (
                    self.subTest(accepted=accepted),
                    self.assertRaises(ValidationError),
                ):
                    self.tx._zift_send_quoted_payment(
                        self.instrument, quote_id, accepted
                    )
            with (
                freeze_time(fields.Datetime.now() + timedelta(minutes=11)),
                self.assertRaises(ValidationError),
            ):
                self.tx._zift_send_quoted_payment(
                    self.instrument, quote["quote_id"], True
                )
        send.assert_not_called()

    def test_changed_amount_instrument_and_provider_invalidate_quote(self):
        quote, _send = self.quote()
        with patch(_SEND) as send:
            for instrument in (
                dict(self.instrument, token="another"),
                dict(self.instrument, accountAccessory="0129"),
            ):
                with self.assertRaises(ValidationError):
                    self.tx._zift_send_quoted_payment(
                        instrument, quote["quote_id"], True
                    )
            self._update_transaction(self.tx, amount=101)
            with self.assertRaises(ValidationError):
                self.tx._zift_send_quoted_payment(
                    self.instrument, quote["quote_id"], True
                )
            self._update_transaction(self.tx, amount=100)
            self.zift.zift_account_id = "changed-merchant"
            with self.assertRaises(ValidationError):
                self.tx._zift_send_quoted_payment(
                    self.instrument, quote["quote_id"], True
                )
        send.assert_not_called()

    def test_replaced_quote_cannot_be_used(self):
        old, _send = self.quote()
        self.quote(fee="100")
        with patch(_SEND) as send, self.assertRaises(ValidationError):
            self.tx._zift_send_quoted_payment(self.instrument, old["quote_id"], True)
        send.assert_not_called()

    def test_quoted_evidence_cannot_be_forged(self):
        for values in (
            {"zift_fee_amount": 1},
            {"zift_fee_processed": True},
            {"zift_fee_accepted_at": fields.Datetime.now()},
        ):
            with self.assertRaises(AccessError):
                self.tx.with_context(
                    payment_safe_write=True, zift_fee_token=True
                ).write(values)
        with self.assertRaises(AccessError):
            self._create_transaction("direct", zift_fee_amount=1)
        with self.assertRaises(AccessError):
            self.tx.with_context(default_zift_fee_processed=True).copy()

    def test_stored_token_waits_for_acceptance_and_ignores_client_instrument(self):
        token = self._create_token(
            provider_ref="saved", zift_account_type="R", zift_account_accessory="1228"
        )
        self._update_transaction(self.tx, token_id=token.id, operation="online_token")
        with patch(_SEND) as send:
            self.tx._send_payment_request()
        send.assert_not_called()
        quote, send = self.quote()
        self.assertEqual(send.call_args.kwargs["data"]["token"], "saved")
        send = self.pay(quote)
        self.assertEqual(send.call_args.kwargs["data"]["token"], "saved")

    def test_wrong_owner_or_inactive_token_is_rejected(self):
        token = self._create_token(
            partner_id=self.portal_user.partner_id.id,
            zift_account_type="R",
            zift_account_accessory="1228",
        )
        self._update_transaction(self.tx, token_id=token.id)
        with patch(_SEND) as send, self.assertRaises(ValidationError):
            self.tx._zift_quote_fee()
        send.assert_not_called()

    def test_off_session_payment_requires_payer(self):
        self._update_transaction(self.tx, operation="offline")
        with patch(_SEND) as send, self.assertRaises(ValidationError):
            self.tx._send_payment_request()
        send.assert_not_called()

    def test_mismatched_gateway_amount_is_uncertain_and_not_retried(self):
        quote, _send = self.quote()
        self.pay(
            quote, response=dict(self.card_approval, amount="10325", feeAmount="325")
        )
        self.assertEqual(self.tx.state, "error")
        self.assertTrue(self.tx.zift_fee_processed)
        self.assertFalse(self.tx.payment_id)

    def test_timeout_preserves_consumed_quote(self):
        quote, _send = self.quote()
        with patch(_SEND, side_effect=ValidationError("Synthetic timeout")):
            self.tx._zift_send_quoted_payment(self.instrument, quote["quote_id"], True)
        self.assertEqual(self.tx.state, "error")
        self.assertTrue(self.tx.zift_fee_processed)
        with self.assertRaises(ValidationError):
            self.tx._zift_send_quoted_payment(self.instrument, quote["quote_id"], True)

    def test_refund_is_positive_principal_and_does_not_refund_fee(self):
        quote, _send = self.quote()
        self.pay(quote)
        self._run_processing()
        refund = self._create_transaction(
            "direct",
            amount=-40,
            reference="Test refund",
            operation="refund",
            source_transaction_id=self.tx.id,
        )
        with patch(
            _SEND, return_value=dict(self.card_approval, responseType="credit")
        ) as send:
            refund._send_refund_request()
        payload = send.call_args.kwargs["data"]
        self.assertEqual((payload["amount"], payload["feeAmount"]), (4000, 0))
        self.assertFalse(refund.zift_fee_accepted_at)

    def test_fee_mode_requires_automatic_capture_and_is_default_off(self):
        self.assertFalse(
            self.env["payment.provider"]
            .default_get(["zift_pass_fees"])
            .get("zift_pass_fees", False)
        )
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.zift.capture_manually = True

    def test_gateway_missing_instrument_does_not_look_paid(self):
        quote, _send = self.quote()
        response = dict(self.card_approval, amount="10000", feeAmount="325")
        response.pop("accountType")
        self.pay(quote, response=response)
        self.assertEqual(self.tx.state, "error")
        self.assertEqual(self.tx.provider_reference, response["transactionId"])

    def test_accepted_principal_cannot_be_rewritten(self):
        quote, _send = self.quote()
        self.pay(quote)
        with self.assertRaises(ValidationError):
            self._update_transaction(self.tx, amount=103.25)
        self.assertEqual(self.tx.zift_fee_principal, 100)

    def test_disabled_provider_and_validation_cannot_quote(self):
        self.zift.zift_pass_fees = False
        with self.assertRaises(ValidationError), patch(_SEND) as send:
            self.tx._zift_quote_fee(self.instrument)
        send.assert_not_called()
        self.zift.zift_pass_fees = True
        self._update_transaction(self.tx, operation="validation", amount=0)
        with self.assertRaises(ValidationError), patch(_SEND) as send:
            self.tx._zift_quote_fee(self.instrument)
        send.assert_not_called()
