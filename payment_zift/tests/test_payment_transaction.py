# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import ZiftCommon

_SEND = "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request"


@tagged("post_install", "-at_install")
class TestPaymentTransaction(ZiftCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Apply updates for real rather than through PaymentCommon's patch.
        cls.enable_process_patcher = False

    def _apply(self, tx, payment_data):
        """Call `_apply_updates` the way the framework does.

        20.0 refuses a direct write to a payment.transaction unless the
        context carries `payment_safe_write`. In production `_apply_updates`
        is reached from `_process`, which runs inside that context; a test
        calling it directly has to supply it.
        """
        tx.with_context(payment_safe_write=True)._apply_updates(payment_data)

    # === STATE MAPPING === #

    def test_card_approval_confirms_the_payment(self):
        tx = self._create_transaction("direct")
        self._apply(tx, {"response": self.card_approval})
        self.assertEqual(tx.state, "done")
        self.assertEqual(tx.provider_reference, "MOCKTXN00000001")

    def test_ach_acceptance_is_pending_and_never_done(self):
        """THE ASSERTION THIS MODULE EXISTS FOR.

        A card approval is an issuer guaranteeing funds. An accepted ACH debit
        has only entered the network: it settles in one to three business days
        and can be returned afterwards. `done` would create an account.payment
        and reconcile the invoice for money that has not arrived.
        """
        tx = self._create_transaction("direct")
        self._apply(tx, {"response": self.ach_acceptance})
        self.assertEqual(tx.state, "pending")
        self.assertNotEqual(tx.state, "done")
        self.assertIn("not confirmed until settlement", tx.state_message)

    def test_decline_cancels_the_transaction(self):
        tx = self._create_transaction("direct")
        self._apply(tx, {"response": self.decline})
        self.assertEqual(tx.state, "cancel")
        self.assertIn("Do not honour", tx.state_message)

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_unrecognised_response_is_an_error_not_an_approval(self):
        """Nothing may look paid for that has not been."""
        tx = self._create_transaction("direct")
        self._apply(tx, {"response": {"responseType": "something-new"}})
        self.assertEqual(tx.state, "error")

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    def test_approval_without_a_transaction_id_is_an_error(self):
        """A transaction nobody can name later cannot be voided or refunded."""
        tx = self._create_transaction("direct")
        self._apply(tx, {"response": {"responseType": "sale", "responseCode": "A01"}})
        self.assertEqual(tx.state, "error")

    def test_validation_operation_confirms_without_moving_money(self):
        tx = self._create_transaction("direct", operation="validation")
        self._apply(tx, {"response": self.card_approval})
        self.assertEqual(tx.state, "done")

    # === TOKENIZATION === #

    def test_token_values_keep_what_a_later_charge_needs(self):
        tx = self._create_transaction("direct", tokenize=True)
        values = tx._extract_token_values({"response": self.card_approval})
        self.assertEqual(values["provider_ref"], "ziftcardtoken")
        self.assertEqual(values["payment_details"], "5655")
        self.assertEqual(values["zift_account_type"], "R")
        # Zift requires the accessory on every charge even with a token, so a
        # token stored without it could never be charged.
        self.assertEqual(values["zift_account_accessory"], "1228")

    def test_bank_token_keeps_the_routing_number_as_the_accessory(self):
        tx = self._create_transaction("direct", tokenize=True)
        values = tx._extract_token_values({"response": self.ach_acceptance})
        self.assertEqual(values["zift_account_type"], "C")
        self.assertEqual(values["zift_account_accessory"], "011000015")
        self.assertEqual(values["payment_details"], "7890")

    def test_tokenization_is_idempotent(self):
        tx = self._create_transaction("direct", tokenize=True)
        self._update_transaction(tx, token_id=self._create_token().id)
        self.assertEqual(tx._extract_token_values({"response": self.card_approval}), {})

    def test_no_token_in_the_response_stores_nothing(self):
        tx = self._create_transaction("direct", tokenize=True)
        response = dict(self.card_approval)
        response.pop("token")
        self.assertEqual(tx._extract_token_values({"response": response}), {})

    # === REQUESTS === #

    def test_amount_is_sent_in_cents(self):
        tx = self._create_transaction("direct", amount=39.45)
        self.assertEqual(tx._zift_get_amount_in_cents(), 3945)

    def test_credentials_are_attached_to_every_request(self):
        """No call site supplies them, so no call site can forget them."""
        tx = self._create_transaction("direct")
        with patch(_SEND, return_value=self.card_approval) as send_mock:
            tx._zift_make_request("sale", {"amount": 100})
        payload = send_mock.call_args.kwargs["data"]
        self.assertEqual(payload["requestType"], "sale")
        self.assertEqual(payload["userName"], "dummy")
        self.assertEqual(payload["password"], "dummy")
        self.assertEqual(payload["accountId"], "dummy")

    def test_empty_params_are_dropped_from_the_request(self):
        tx = self._create_transaction("direct")
        with patch(_SEND, return_value=self.card_approval) as send_mock:
            tx._zift_make_request("sale", {"amount": 100, "orderCode": None})
        self.assertNotIn("orderCode", send_mock.call_args.kwargs["data"])

    def test_token_payment_sends_the_stored_accessory(self):
        token = self._create_token(
            provider_ref="ziftcardtoken",
            zift_account_type="R",
            zift_account_accessory="1228",
            zift_holder_name="Measurement Instruments East Inc.",
        )
        tx = self._create_transaction("token", token_id=token.id)
        with patch(_SEND, return_value=self.card_approval) as send_mock:
            tx._send_payment_request()
        payload = send_mock.call_args.kwargs["data"]
        self.assertEqual(payload["token"], "ziftcardtoken")
        self.assertEqual(payload["accountAccessory"], "1228")
        self.assertEqual(payload["accountType"], "R")

    # === REFERENCE === #

    def test_reference_is_read_from_the_order_code(self):
        tx = self._create_transaction("direct")
        reference = self.env["payment.transaction"]._extract_reference(
            "zift", {"response": {"orderCode": tx.reference}}
        )
        self.assertEqual(reference, tx.reference)
