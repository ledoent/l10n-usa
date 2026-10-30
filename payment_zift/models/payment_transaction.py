# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, models

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    # === BUSINESS METHODS - PAYMENT FLOW === #

    def _get_specific_processing_values(self, processing_values):
        """Override of `payment` to return an access token.

        Everything returned here reaches a web page, so the rule is absolute:
        no `userName`, no `password`, no `accountId`. The access token is what
        lets the payment route trust a reference posted from a public page.
        """
        if self.provider_code != "zift":
            return super()._get_specific_processing_values(processing_values)
        return {
            "access_token": payment_utils.generate_access_token(
                processing_values["reference"], processing_values["partner_id"]
            )
        }

    def _zift_make_request(self, request_type, params):
        """Send one request to the gateway and return the parsed response.

        Credentials are attached here, once, so no call site can forget them —
        and `_send_api_request` is used rather than `requests` directly because
        it supplies the timeout, the sensitive-key-filtered logging and the
        error handling that this module would otherwise have to repeat.
        """
        self.ensure_one()
        payload = {
            "requestType": request_type,
            **self.provider_id._zift_get_credentials(),
            **{k: v for k, v in params.items() if v not in (None, "")},
        }
        return self.provider_id._send_api_request(
            "POST", const.GATEWAY_PATH, data=payload, reference=self.reference
        )

    def _zift_get_amount_in_cents(self):
        """Zift amounts are integers of cents, never decimal dollars."""
        self.ensure_one()
        return payment_utils.to_minor_currency_units(self.amount, self.currency_id)

    def _send_payment_request(self):
        """Override of `payment` to charge a stored Zift token."""
        if self.provider_code != "zift":
            return super()._send_payment_request()

        token = self.token_id
        account_type = token.zift_account_type or const.ACCOUNT_TYPE_CARD
        params = {
            "accountType": account_type,
            "token": token.provider_ref,
            # Required on every charge EVEN WITH a token: the card expiry, or
            # the ABA routing number for a bank account. A token alone cannot
            # be charged, which is why the token model keeps a column for it.
            "accountAccessory": token.zift_account_accessory,
            "holderName": token.zift_holder_name,
            "holderType": const.HOLDER_TYPE_BUSINESS,
            "amount": self._zift_get_amount_in_cents(),
            "orderCode": self.reference,
        }
        response_content = self._zift_make_request("sale", params)
        self._record({"response": response_content})

    def _send_refund_request(self):
        """Override of `payment` to refund through Zift's `credit`."""
        if self.provider_code != "zift":
            return super()._send_refund_request()

        source_tx = self.source_transaction_id
        params = {
            "transactionId": source_tx.provider_reference,
            "amount": self._zift_get_amount_in_cents(),
        }
        response_content = self._zift_make_request("credit", params)
        self._record({"response": response_content})

    def _send_capture_request(self):
        """Override of `payment` to capture an authorised Zift transaction."""
        if self.provider_code != "zift":
            return super()._send_capture_request()

        params = {
            "transactionId": self.provider_reference,
            "amount": self._zift_get_amount_in_cents(),
        }
        response_content = self._zift_make_request("capture", params)
        self._record({"response": response_content})

    def _send_void_request(self):
        """Override of `payment` to void through Zift's `void`."""
        if self.provider_code != "zift":
            return super()._send_void_request()

        params = {"transactionId": self.provider_reference}
        response_content = self._zift_make_request("void", params)
        self._record({"response": response_content})

    # === BUSINESS METHODS - POST-PROCESSING === #

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment` to extract the reference from payment data.

        Zift's `orderCode` is the merchant's own order identifier, which is
        where this module puts the transaction reference. Note that no field in
        Zift's published documentation is obviously the *buyer's* PO number —
        that is an open question with the gateway, recorded in ROADMAP.
        """
        if provider_code != "zift":
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get("response", {}).get("orderCode")

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction from payment data.

        THE ONE RULE THIS METHOD ENFORCES

        An outcome this method does not recognise is an error, never a success.
        Nothing may look paid for that has not been: a wrong decline is a
        support call, a wrong approval is an unpaid invoice marked settled.
        """
        if self.provider_code != "zift":
            return super()._apply_updates(payment_data)

        response = payment_data.get("response", {})

        # Update the provider reference.
        if response.get("transactionId"):
            self.provider_reference = response["transactionId"]

        # Update the payment method.
        account_type = response.get("accountType") or (
            self.token_id.zift_account_type if self.token_id else None
        )
        if account_type:
            generic_code = (
                "ach_direct_debit"
                if account_type in const.ACH_ACCOUNT_TYPES
                else "card"
            )
            payment_method = self.provider_id._get_pm_from_code(generic_code)
            self.payment_method_id = payment_method or self.payment_method_id

        # Update the payment state.
        response_type = response.get("responseType", "")
        message = response.get("responseMessage") or ""

        if response_type == const.EXCEPTION_RESPONSE_TYPE:
            self._set_canceled(state_message=message)
            return

        if not response_type or not response.get("transactionId"):
            # A response that is neither an echo nor an exception is a shape
            # nobody here has seen, and a shape nobody has seen is not evidence
            # of a payment. Approval also requires something to refer back to:
            # a transaction we cannot name later cannot be voided or refunded.
            self._set_error(
                self.env._(
                    'Zift returned responseType "%(type)s" without a transaction'
                    " id, which this module does not recognise.",
                    type=response_type or "(none)",
                )
            )
            return

        if self.operation == "validation":
            # The $0 account verification. It moves no money, so there is
            # nothing to confirm — the point was the token.
            self._set_done()
        elif account_type in const.ACH_ACCOUNT_TYPES:
            # AN ACH ACCEPTANCE IS NOT A PAYMENT.
            #
            # A card approval is an issuer guaranteeing funds. An accepted bank
            # debit has merely entered the ACH network: it settles in one to
            # three business days and can be returned after that. `pending`
            # leaves the invoice unreconciled, which is the truth; `_set_done`
            # would create an `account.payment` for money that has not arrived.
            self._set_pending(
                state_message=self.env._(
                    "Bank debit accepted for processing. ACH settles in one to"
                    " three business days and can still be returned; this"
                    " payment is not confirmed until settlement."
                )
            )
        elif self.provider_id.capture_manually:
            self._set_authorized()
        else:
            self._set_done()

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to return the amount data for validation."""
        if self.provider_code != "zift":
            return super()._extract_amount_data(payment_data)

        response = payment_data.get("response", {})
        amount = response.get("amount")
        if amount is None:
            # Opting out of amount validation entirely. Returning an empty dict
            # instead would put the transaction in error for a missing amount.
            return None
        return {
            "amount": payment_utils.to_major_currency_units(
                float(amount), self.currency_id
            ),
            "currency_code": self.currency_id.name,
        }

    def _extract_token_values(self, payment_data):
        """Override of `payment` to return the token values."""
        if self.provider_code != "zift":
            return super()._extract_token_values(payment_data)
        if self.token_id:
            return {}

        response = payment_data.get("response", {})
        token = response.get("token")
        if not token:
            return {}

        masked = response.get("accountNumberMasked", "")
        digits = "".join(c for c in masked if c.isdigit())
        last_four = digits[-4:] if len(digits) >= 4 else ""

        return {
            "provider_ref": token,
            "payment_details": last_four,
            "zift_account_type": response.get("accountType") or const.ACCOUNT_TYPE_CARD,
            # Zift requires this on every later charge, so it is stored beside
            # the token rather than discarded as display metadata.
            "zift_account_accessory": response.get("accountAccessory"),
            "zift_holder_name": response.get("holderName"),
        }
