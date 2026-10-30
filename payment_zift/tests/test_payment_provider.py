# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
from unittest.mock import MagicMock

from odoo.tests import tagged

from odoo.addons.payment.const import SENSITIVE_KEYS as PAYMENT_SENSITIVE_KEYS

from .. import const
from .common import ZiftCommon


@tagged("post_install", "-at_install")
class TestPaymentProvider(ZiftCommon):
    def test_gateway_url_switches_on_the_environment(self):
        """A test provider must never reach the live gateway.

        20.0 replaced the `state` selection with the `is_live` boolean, so a
        provider written against 19.0's `state == "test"` would read as live.
        """
        self.zift.is_live = False
        self.assertIn("sandbox-secure.zift.io", self.zift._build_request_url(""))
        self.zift.is_live = True
        url = self.zift._build_request_url("")
        self.assertIn("secure.zift.io", url)
        self.assertNotIn("sandbox", url)

    def test_request_is_form_encoded(self):
        headers = self.zift._build_request_headers("POST", "", {})
        self.assertEqual(headers["Content-Type"], "application/x-www-form-urlencoded")

    def test_response_is_parsed_as_form_encoded(self):
        """The reply is form-urlencoded too, not JSON.

        This is the detail most likely to catch out someone arriving from a
        JSON API, so it is pinned rather than assumed.
        """
        response = MagicMock()
        response.text = (
            "responseType=exception&responseCode=L01&"
            "responseMessage=Username+or+password+is+invalid."
        )
        parsed = self.zift._parse_response_content(response)
        self.assertEqual(parsed["responseType"], "exception")
        self.assertEqual(parsed["responseCode"], "L01")
        self.assertEqual(parsed["responseMessage"], "Username or password is invalid.")

    def test_error_message_is_extracted_from_the_response(self):
        response = MagicMock()
        response.text = "responseType=exception&responseMessage=Declined."
        self.assertEqual(self.zift._parse_response_error(response), "Declined.")

    def test_only_usd_is_supported(self):
        supported = self.zift._get_supported_currencies()
        self.assertTrue(supported)
        self.assertEqual(set(supported.mapped("name")), {"USD"})

    def test_card_and_ach_are_the_default_methods(self):
        self.assertEqual(
            self.zift._get_default_payment_method_codes(),
            {"card", "ach_direct_debit"},
        )

    def test_tokenization_is_supported(self):
        self.assertTrue(self.zift.support_tokenization)

    def test_validation_amount_is_zero(self):
        """Zift's account-verification genuinely moves no money.

        Odoo's default is already 0.0, so the provider deliberately does not
        override it — this asserts the default is what actually applies, since
        a non-zero value would place a hold on a customer's account.
        """
        self.assertEqual(self.zift._get_validation_amount(), 0.0)

    def test_inline_form_values_carry_no_credential(self):
        """Everything here reaches a web page."""
        values = json.loads(self.zift._zift_get_inline_form_values())
        self.assertIn("proxynization_url", values)
        serialised = json.dumps(values)
        for secret in ("dummy", "userName", "password", "accountId"):
            self.assertNotIn(secret, serialised)

    def test_credentials_are_cleared_on_reset(self):
        reset_values = self.zift._get_reset_values()
        self.assertFalse(reset_values["zift_username"])
        self.assertFalse(reset_values["zift_password"])
        self.assertFalse(reset_values["zift_account_id"])

    def test_credential_keys_are_registered_as_sensitive(self):
        """The single most important line in const.py.

        Zift authenticates in the request BODY, and `_send_api_request` logs
        the payload it sends. Core's SENSITIVE_KEYS is an empty set, so without
        the update in const.py every call would write live merchant credentials
        into the Odoo log. If this test fails, that is what is happening.
        """
        for key in ("userName", "password", "accountId", "token"):
            self.assertIn(key, const.SENSITIVE_KEYS)
            self.assertIn(key, PAYMENT_SENSITIVE_KEYS)
