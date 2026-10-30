# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.addons.payment.const import SENSITIVE_KEYS as PAYMENT_SENSITIVE_KEYS

# Keys that must never reach the log.
#
# THIS IS NOT DECORATION. Zift authenticates every request with `userName`,
# `password` and `accountId` *in the request body*, and
# `payment.provider._send_api_request` logs the payload it sends. Core's
# `SENSITIVE_KEYS` is an empty set, so without the update below every Zift call
# would write live merchant credentials into the Odoo log at INFO level.
#
# The mechanism is a mutation of core's shared set at import time: `payment`
# builds its loggers with a reference to that same mutable object, so adding to
# it here retroactively redacts these keys in core's own request and response
# logging too.
SENSITIVE_KEYS = {
    "userName",
    "password",
    "accountId",
    "token",
    "accountNumber",
    "accountAccessory",
    "csc",
}
PAYMENT_SENSITIVE_KEYS.update(SENSITIVE_KEYS)

# The gateway is a single endpoint; `requestType` selects the operation.
GATEWAY_PATH = "/gates/xurl"
LIVE_URL = "https://secure.zift.io"
TEST_URL = "https://sandbox-secure.zift.io"

# Where the browser loads the tokenizer from, per environment.
PROXYNIZATION_PATH = "/services/api.proxynization.js"

# The route the inline form posts its token to.
PAYMENT_REQUEST_ROUTE = "/payment/zift/payment"

# Zift's `accountType`. One field selects card or bank, which is why all three
# values live together: reading one without the others invites sending a card
# down the ACH path, where an acceptance is reported as merely pending.
ACCOUNT_TYPE_CARD = "R"
ACCOUNT_TYPE_CHECKING = "C"
ACCOUNT_TYPE_SAVINGS = "S"
ACH_ACCOUNT_TYPES = (ACCOUNT_TYPE_CHECKING, ACCOUNT_TYPE_SAVINGS)

# `holderType`: P personal, O organization. Required as O for Level II and III.
HOLDER_TYPE_PERSONAL = "P"
HOLDER_TYPE_BUSINESS = "O"

# `verificationMode`: NN performs no pre-tokenization verification; PF has the
# processor verify and DECLINES the tokenization when verification fails.
#
# PF is the only correct value for a bank account. NACHA's WEB Debit Account
# Validation Rule wants an account validated before first use, and Zift's own
# guidance is to validate before storing. NN would store an unverified account,
# which is precisely what becomes a return days later.
VERIFICATION_MODE_NONE = "NN"
VERIFICATION_MODE_PROCESSOR = "PF"

# The codes of the default primary payment methods to activate.
DEFAULT_PAYMENT_METHOD_CODES = {"card", "ach_direct_debit"}

# Mapping of Odoo payment method codes to Zift account types.
PAYMENT_METHODS_MAPPING = {
    "ach_direct_debit": ACCOUNT_TYPE_CHECKING,
    "card": ACCOUNT_TYPE_CARD,
}

# Zift settles in USD only.
SUPPORTED_CURRENCIES = ("USD",)

# `responseType` echoes the request on success and is the literal string
# "exception" on failure. Observed against the sandbox on 2026-09-09 with
# deliberately wrong credentials:
#
#   responseType=exception&responseCode=L01&responseMessage=Username+or+...
EXCEPTION_RESPONSE_TYPE = "exception"
