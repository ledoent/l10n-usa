# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import fields, models


class PaymentToken(models.Model):
    _inherit = "payment.token"

    zift_account_type = fields.Char(
        help="Zift's accountType: R for a card, C for checking, S for savings.",
        readonly=True,
    )
    zift_account_accessory = fields.Char(
        help=(
            "The card expiry as MMYY, or the ABA routing number for a bank "
            "account. Zift requires it on every charge even when the account "
            "is identified by a token, so a token cannot be used without it."
        ),
        readonly=True,
    )
    zift_holder_name = fields.Char(
        string="Zift Account Holder",
        help=(
            "The name on the card or bank account. Not cosmetic for ACH: a "
            "name that does not match the account is a documented cause of a "
            "returned debit."
        ),
        readonly=True,
    )

    # NOTE: there is deliberately no field here for a card number, a security
    # code, or a bank account number, and there must never be one. A security
    # code may not be retained after authorisation under any circumstances, and
    # a model definition is where that rule gets quietly broken first. The
    # accessory above is an expiry or a routing number — neither authorises
    # anything on its own.
