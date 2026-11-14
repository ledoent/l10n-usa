# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

from odoo.tests import JsonRpcException, tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon

from .common import ZiftCommon
from .test_fee import _SEND


@tagged("post_install", "-at_install")
class TestZiftFeeController(ZiftCommon, PaymentHttpCommon):
    def test_signed_payer_quote_and_explicit_acceptance(self):
        self.authenticate(None, None)
        self.zift.zift_pass_fees = True
        tx = self._create_transaction("direct", amount=100)
        params = {
            "reference": tx.reference,
            "partner_id": self.partner.id,
            "access_token": self._generate_test_access_token(
                tx.reference, self.partner.id
            ),
            "zift_data": {
                "token": "fictional",
                "accountAccessory": "1228",
                "accountType": "R",
            },
        }
        with patch(
            _SEND,
            return_value={
                "responseType": "convenience-fee",
                "responseCode": "A01",
                "feeAmount": "325",
            },
        ) as send:
            for values in (
                dict(params, access_token="forged"),
                dict(params, reference="other"),
                dict(params, partner_id=self.portal_partner.id),
            ):
                with self.assertRaises(JsonRpcException), mute_logger("odoo.http"):
                    self.make_jsonrpc_request("/payment/zift/fee_quote", values)
            send.assert_not_called()
            quote = self.make_jsonrpc_request("/payment/zift/fee_quote", params)
            self.assertEqual(quote["total"], 103.25)
        with (
            patch(_SEND) as send,
            self.assertRaises(JsonRpcException),
            mute_logger("odoo.http"),
        ):
            self.make_jsonrpc_request(
                "/payment/zift/payment",
                dict(params, fee_quote_id=quote["quote_id"], fee_accepted=False),
            )
        send.assert_not_called()
        with patch(
            _SEND,
            return_value=dict(self.card_approval, amount="10000", feeAmount="325"),
        ) as send:
            self.make_jsonrpc_request(
                "/payment/zift/payment",
                dict(params, fee_quote_id=quote["quote_id"], fee_accepted=True),
            )
        self.assertEqual(send.call_count, 1)
