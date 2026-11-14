# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import http
from odoo.exceptions import ValidationError

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

from .. import const

_logger = get_payment_logger(__name__, const.SENSITIVE_KEYS)


class ZiftController(http.Controller):
    """The one route the inline form posts to.

    THERE IS DELIBERATELY NO WEBHOOK ROUTE HERE.

    Zift sends asynchronous notifications — ACH settlements, returns, and
    Notices of Change that correct a stored account's token, routing number,
    holder name or account type. Handling them needs an endpoint, and an
    endpoint that rewrites stored payment credentials must authenticate the
    caller.

    How Zift signs or authenticates a callback is not in its published
    documentation. An unauthenticated endpoint that accepts "replace this
    token" from anyone on the internet is the worst thing this module could
    ship, so the route is absent rather than guessed at. See readme/ROADMAP.md.
    """

    @http.route(
        const.PAYMENT_REQUEST_ROUTE, type="jsonrpc", auth="public", methods=["POST"]
    )
    def zift_payment(
        self,
        reference,
        partner_id,
        access_token,
        zift_data=None,
        fee_quote_id=None,
        fee_accepted=False,
    ):
        """Make a payment request with a token minted in the browser.

        `zift_data` carries only what proxynization hands back — a token, the
        account type, the accessory (card expiry or routing number) and the
        holder name. It never carries a card number or a bank account number;
        those stay in the browser and go straight to Zift.
        """
        # The reference and partner arrive from a public page, so neither is
        # trusted until the access token proves they were not altered.
        if not payment_utils.check_access_token(access_token, reference, partner_id):
            raise ValidationError(self.env._("Received tampered payment request data."))

        tx_sudo = (
            self.env["payment.transaction"]
            .sudo()
            .search([("reference", "=", reference)], limit=1)
        )
        if not tx_sudo:
            raise ValidationError(
                self.env._("No transaction found matching the reference.")
            )

        if tx_sudo.provider_code != "zift" or tx_sudo.partner_id.id != int(partner_id):
            raise ValidationError(
                self.env._("This payment does not belong to this payer and provider.")
            )
        if tx_sudo.provider_id.zift_pass_fees and tx_sudo.operation != "validation":
            return tx_sudo._zift_send_quoted_payment(
                zift_data, fee_quote_id, fee_accepted
            )
        if fee_quote_id:
            raise ValidationError(
                self.env._("Fee settings changed; review this payment again.")
            )
        zift_data = zift_data or {}
        account_type = zift_data.get("accountType") or const.ACCOUNT_TYPE_CARD
        is_ach = account_type in const.ACH_ACCOUNT_TYPES

        params = {
            "accountType": account_type,
            "token": zift_data.get("token"),
            "accountAccessory": zift_data.get("accountAccessory"),
            "holderName": zift_data.get("holderName"),
            "holderType": const.HOLDER_TYPE_BUSINESS,
        }

        if tx_sudo.operation == "validation":
            # Store the instrument without moving money. Zift's
            # `account-verification` is a genuine $0 operation — no hold, and
            # nothing to reverse — which is why the provider leaves Odoo's
            # validation amount at its 0.0 default.
            #
            # `PF` makes the processor's verdict decide whether anything is
            # stored at all. For a bank account that is what NACHA's WEB Debit
            # Account Validation Rule asks for, and it is the difference
            # between refusing an unverifiable account now and discovering it
            # as a returned debit days later.
            params["verificationMode"] = const.VERIFICATION_MODE_PROCESSOR
            response_content = tx_sudo._zift_make_request(
                "account-verification", params
            )
        else:
            params["amount"] = tx_sudo._zift_get_amount_in_cents()
            params["orderCode"] = tx_sudo.reference
            if is_ach:
                # An ACH debit has no interchange, so no Level II or III data
                # is attached: it would be a record that cannot reconcile
                # against anything.
                response_content = tx_sudo._zift_make_request("sale", params)
            else:
                request_type = (
                    "sale-auth" if tx_sudo.provider_id.capture_manually else "sale"
                )
                response_content = tx_sudo._zift_make_request(request_type, params)

        tx_sudo._record({"response": response_content})

    @http.route(
        "/payment/zift/fee_quote", type="jsonrpc", auth="public", methods=["POST"]
    )
    def zift_fee_quote(self, reference, partner_id, access_token, zift_data=None):
        if not payment_utils.check_access_token(access_token, reference, partner_id):
            raise ValidationError(self.env._("Received tampered fee quote request."))
        transaction = (
            self.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("reference", "=", reference),
                    ("partner_id", "=", int(partner_id)),
                    ("provider_code", "=", "zift"),
                ],
                limit=1,
            )
        )
        if not transaction:
            raise ValidationError(self.env._("No matching Zift transaction was found."))
        return transaction._zift_quote_fee(zift_data)
