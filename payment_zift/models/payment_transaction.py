# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import hashlib
import json
import re
import uuid
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)

_FEE_TOKEN = object()
_OUTPUTS = {
    "zift_fee_principal",
    "zift_fee_amount",
    "zift_fee_quote_id",
    "zift_fee_expires_at",
    "zift_fee_fingerprint",
    "zift_fee_accepted_at",
    "zift_fee_processed",
}


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
            ),
            "zift_fee_enabled": self.provider_id.zift_pass_fees
            and self.operation != "validation",
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

        if self.provider_id.zift_pass_fees:
            if self.operation == "online_token":
                return  # The payment form obtains an accepted quote before charging.
            raise ValidationError(
                self.env._(
                    "This payment requires the payer to accept a current "
                    "processing-fee quote."
                )
            )

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
            "amount": abs(self._zift_get_amount_in_cents()),
        }
        if source_tx.zift_fee_processed:
            params["feeAmount"] = 0
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

    zift_fee_principal = fields.Monetary(readonly=True, copy=False)
    zift_fee_amount = fields.Monetary(readonly=True, copy=False)
    zift_fee_quote_id = fields.Char(
        readonly=True, copy=False, groups="base.group_system"
    )
    zift_fee_expires_at = fields.Datetime(readonly=True, copy=False)
    zift_fee_fingerprint = fields.Char(
        readonly=True, copy=False, groups="base.group_system"
    )
    zift_fee_accepted_at = fields.Datetime(readonly=True, copy=False)
    zift_fee_processed = fields.Boolean(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("zift_fee_token") is not _FEE_TOKEN and (
            any(_OUTPUTS & values.keys() for values in vals_list)
            or any("default_" + name in self.env.context for name in _OUTPUTS)
        ):
            raise AccessError(
                self.env._("Use the Zift fee quote and payment workflow.")
            )
        return super().create(vals_list)

    def write(self, vals):
        if {"amount", "currency_id", "provider_id", "partner_id"} & vals.keys() and any(
            tx.zift_fee_processed for tx in self
        ):
            raise ValidationError(
                self.env._("Keep the accepted payment inputs for reconciliation.")
            )
        if (
            _OUTPUTS & vals.keys()
            and self.env.context.get("zift_fee_token") is not _FEE_TOKEN
        ):
            raise AccessError(
                self.env._("Fee quotes and acceptance are payment evidence.")
            )
        return super().write(vals)

    def _zift_instrument(self, data=None):
        self.ensure_one()
        data = data or {}
        if self.token_id:
            token = self.token_id
            if (
                not token.active
                or token.provider_id != self.provider_id
                or token.partner_id.commercial_partner_id
                != self.partner_id.commercial_partner_id
            ):
                raise ValidationError(
                    self.env._(
                        "Use an active payment method belonging to this payer "
                        "and provider."
                    )
                )
            data = {
                "token": token.provider_ref,
                "accountType": token.zift_account_type,
                "accountAccessory": token.zift_account_accessory,
                "holderName": token.zift_holder_name,
            }
        account_type = data.get("accountType") or const.ACCOUNT_TYPE_CARD
        if (
            account_type not in (const.ACCOUNT_TYPE_CARD, *const.ACH_ACCOUNT_TYPES)
            or not isinstance(data.get("token"), str)
            or not data["token"]
            or not data.get("accountAccessory")
        ):
            raise ValidationError(
                self.env._("Provide a tokenized card or bank account.")
            )
        return {
            "token": data["token"],
            "accountType": account_type,
            "accountAccessory": data["accountAccessory"],
            "holderName": data.get("holderName") or "",
            "holderType": const.HOLDER_TYPE_BUSINESS,
        }

    def _zift_fee_fingerprint(self, instrument):
        values = {
            "instrument": instrument,
            "provider": self.provider_id.id,
            "company": self.company_id.id,
            "partner": self.partner_id.id,
            "merchant": self.provider_id.sudo().zift_account_id,
            "is_live": self.provider_id.is_live,
            "is_published": self.provider_id.is_published,
            "manual_capture": self.provider_id.capture_manually,
            "currency": self.currency_id.id,
            "amount": self._zift_get_amount_in_cents(),
            "operation": self.operation,
            "reference": self.reference,
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def _zift_check_fee_draft(self):
        self.ensure_one()
        self.lock_for_update()
        self.invalidate_recordset()
        if (
            self.provider_code != "zift"
            or self.state != "draft"
            or self.operation == "validation"
            or self.amount <= 0
            or self.currency_id.name != "USD"
            or self.zift_fee_processed
            or self.provider_id.capture_manually
        ):
            raise ValidationError(
                self.env._(
                    "This transaction cannot receive a new fee or payment request."
                )
            )

    def _zift_quote_fee(self, data=None):
        self._zift_check_fee_draft()
        if not self.provider_id.zift_pass_fees:
            raise ValidationError(
                self.env._("Fee pass-through is not enabled for this provider.")
            )
        instrument = self._zift_instrument(data)
        response = self._zift_make_request(
            "convenience-fee",
            {
                **instrument,
                "amount": self._zift_get_amount_in_cents(),
            },
        )
        fee = response.get("feeAmount")
        if (
            response.get("responseType") != "convenience-fee"
            or response.get("responseCode") != "A01"
            or not re.fullmatch(r"[0-9]+", str(fee))
        ):
            raise ValidationError(
                self.env._(
                    "Zift did not return a valid processing-fee quote. "
                    "No charge was made."
                )
            )
        quote_id = uuid.uuid4().hex
        fee_cents = int(fee)
        if fee_cents > 999999999:
            raise ValidationError(
                self.env._("The processing-fee quote is outside the supported range.")
            )
        self.with_context(zift_fee_token=_FEE_TOKEN, payment_safe_write=True).write(
            {
                "zift_fee_principal": self.amount,
                "zift_fee_amount": fee_cents / 100,
                "zift_fee_quote_id": quote_id,
                "zift_fee_expires_at": fields.Datetime.now() + timedelta(minutes=10),
                "zift_fee_fingerprint": self._zift_fee_fingerprint(instrument),
                "zift_fee_accepted_at": False,
            }
        )
        principal = self._zift_get_amount_in_cents()
        return {
            "quote_id": quote_id,
            "principal": principal / 100,
            "fee": fee_cents / 100,
            "total": (principal + fee_cents) / 100,
            "currency": self.currency_id.name,
        }

    def _zift_send_quoted_payment(self, data=None, quote_id=None, accepted=False):
        self._zift_check_fee_draft()
        instrument = self._zift_instrument(data)
        if (
            not self.provider_id.zift_pass_fees
            or accepted is not True
            or not quote_id
            or quote_id != self.zift_fee_quote_id
            or not self.zift_fee_expires_at
            or self.zift_fee_expires_at < fields.Datetime.now()
            or self.zift_fee_fingerprint != self._zift_fee_fingerprint(instrument)
        ):
            raise ValidationError(
                self.env._(
                    "Review and accept a current fee quote for this "
                    "payment method and amount."
                )
            )
        self.with_context(zift_fee_token=_FEE_TOKEN, payment_safe_write=True).write(
            {
                "zift_fee_accepted_at": fields.Datetime.now(),
                "zift_fee_processed": True,
            }
        )
        params = {
            **instrument,
            "amount": self._zift_get_amount_in_cents(),
            "feeAmount": round(self.zift_fee_amount * 100),
            "orderCode": self.reference,
        }
        try:
            response = self._zift_make_request("sale", params)
            if response.get("responseType") != const.EXCEPTION_RESPONSE_TYPE and (
                response.get("responseType") != "sale"
                or response.get("responseCode") != "A01"
                or response.get("accountType") != instrument["accountType"]
                or str(response.get("feeAmount")) != str(params["feeAmount"])
                or str(response.get("amount")) != str(params["amount"])
            ):
                if response.get("transactionId"):
                    self.with_context(payment_safe_write=True).write(
                        {"provider_reference": response["transactionId"]}
                    )
                self.with_context(payment_safe_write=True)._set_error(
                    self.env._(
                        "The gateway did not confirm the quoted principal and fee. "
                        "Verify the transaction with Zift before retrying."
                    )
                )
            else:
                self._record({"response": response})
        except ValidationError:
            # Return normally so the consumed quote and uncertain outcome persist.
            self.with_context(payment_safe_write=True)._set_error(
                self.env._(
                    "The gateway outcome could not be confirmed. Verify with "
                    "Zift before creating another payment."
                )
            )
        return {"state": self.state}
