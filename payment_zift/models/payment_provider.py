# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import json
from urllib.parse import parse_qsl

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class PaymentProvider(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(
        selection_add=[("zift", "Zift")], ondelete={"zift": "set default"}
    )
    zift_username = fields.Char(
        string="Zift User Name",
        help="The user name identifying the merchant account with Zift.",
        required_if_provider="zift",
        copy=False,
    )
    zift_password = fields.Char(
        required_if_provider="zift",
        copy=False,
        groups="base.group_system",
    )
    zift_account_id = fields.Char(
        string="Zift Account ID",
        help="The Zift merchant account to process against.",
        required_if_provider="zift",
        copy=False,
        groups="base.group_system",
    )

    zift_pass_fees = fields.Boolean(
        string="Pass gateway processing fees to the payer",
        help="Quote the gateway's convenience fee and obtain acceptance "
        "before charging. "
        "Use a merchant profile where Zift collects and retains that fee separately "
        "from the principal. This does not add a merchant markup.",
    )

    # === COMPUTE METHODS === #

    @api.constrains("zift_pass_fees", "capture_manually", "code")
    def _check_zift_fee_capture(self):
        if any(
            p.code == "zift" and p.zift_pass_fees and p.capture_manually for p in self
        ):
            raise ValidationError(
                self.env._("Zift fee pass-through requires automatic capture.")
            )

    def _compute_feature_support_fields(self):
        """Override of `payment` to enable additional features."""
        res = super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "zift").update(
            {
                "support_manual_capture": "full_only",
                "support_refund": "partial",
                "support_tokenization": True,
            }
        )
        return res

    # === BUSINESS METHODS === #

    def _get_supported_currencies(self):
        """Override of `payment` to return the supported currencies."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == "zift":
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        self.ensure_one()
        if self.code != "zift":
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    def _zift_get_base_url(self):
        """Return the gateway host for this provider's environment."""
        self.ensure_one()
        return const.LIVE_URL if self.is_live else const.TEST_URL

    def _zift_get_proxynization_url(self):
        """Return the URL the browser loads Zift's tokenizer from.

        Public by nature — it is a script tag on a payment page — so it carries
        no credential and is safe to hand to the inline form.
        """
        self.ensure_one()
        return f"{self._zift_get_base_url()}{const.PROXYNIZATION_PATH}"

    def _zift_get_inline_form_values(self):
        """Return the values the inline form's script needs, as JSON.

        Read by the template into a `data-` attribute, because the tokenizer
        has to be loaded when the form is prepared — before any processing
        values exist. Nothing here is a credential: the tokenizer URL is a
        script tag, and proxynization authenticates with a temporary password
        the gateway mints server-side rather than a publishable client key.
        """
        self.ensure_one()
        return json.dumps({"proxynization_url": self._zift_get_proxynization_url()})

    def _zift_get_credentials(self):
        """Return the three fields every Zift request authenticates with.

        Read through `sudo` because two of them are restricted to
        `base.group_system`, and the request is made on behalf of a public
        customer paying an invoice.
        """
        self.ensure_one()
        provider_sudo = self.sudo()
        return {
            "userName": provider_sudo.zift_username,
            "password": provider_sudo.zift_password,
            "accountId": provider_sudo.zift_account_id,
        }

    # === REQUEST BUILDING === #

    def _build_request_url(self, endpoint, **kwargs):
        """Override of `payment` to build the Zift gateway URL.

        Zift exposes a single endpoint for every operation; `requestType` in the
        body selects which one, so `endpoint` is ignored here by design.
        """
        if self.code != "zift":
            return super()._build_request_url(endpoint, **kwargs)
        return f"{self._zift_get_base_url()}{const.GATEWAY_PATH}"

    def _build_request_headers(self, method, endpoint, payload, **kwargs):
        """Override of `payment` to send a form-encoded body."""
        if self.code != "zift":
            return super()._build_request_headers(method, endpoint, payload, **kwargs)
        return {"Content-Type": "application/x-www-form-urlencoded"}

    def _parse_response_content(self, response, **kwargs):
        """Override of `payment` to parse Zift's form-encoded response.

        The part most likely to surprise someone arriving from a JSON API: the
        *response* is form-urlencoded too, not only the request.

            responseType=exception&responseCode=L01&responseMessage=...
        """
        if self.code != "zift":
            return super()._parse_response_content(response, **kwargs)
        return dict(parse_qsl(response.text))

    def _parse_response_error(self, response):
        """Override of `payment` to extract Zift's error message."""
        if self.code != "zift":
            return super()._parse_response_error(response)
        return dict(parse_qsl(response.text)).get("responseMessage", response.text)

    def _get_reset_values(self):
        """Override of `payment` to clear the credentials on reset."""
        reset_values = super()._get_reset_values()
        if self.code == "zift":
            reset_values.update(
                zift_username=False, zift_password=False, zift_account_id=False
            )
        return reset_values
