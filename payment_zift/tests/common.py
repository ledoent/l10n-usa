# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.fields import Command

from odoo.addons.payment.tests.common import PaymentCommon


class ZiftCommon(PaymentCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.zift = cls._prepare_provider(
            "zift",
            update_values={
                "zift_username": "dummy",
                "zift_password": "dummy",
                "zift_account_id": "dummy",
                "available_currency_ids": [Command.set(cls.currency_usd.ids)],
            },
        )
        cls.provider = cls.zift
        cls.currency = cls.currency_usd

        # A card approval. `responseType` echoes the request on success, which
        # is the signal this module reads.
        cls.card_approval = {
            "responseType": "sale",
            "responseCode": "A01",
            "responseMessage": "Approved",
            "transactionId": "MOCKTXN00000001",
            "accountType": "R",
            "token": "ziftcardtoken",
            "accountNumberMasked": "4********5655",
            "accountAccessory": "1228",
            "holderName": "Measurement Instruments East Inc.",
        }

        # An ACH acceptance. Note the identical shape: the only thing that
        # makes this different from a payment is `accountType`.
        cls.ach_acceptance = {
            "responseType": "sale",
            "responseCode": "A01",
            "responseMessage": "Accepted for processing.",
            "transactionId": "MOCKTXN00000002",
            "accountType": "C",
            "token": "ziftbanktoken",
            "accountNumberMasked": "*****7890",
            "accountAccessory": "011000015",
            "holderName": "Measurement Instruments East Inc.",
        }

        # `responseType` is the literal string "exception" on failure.
        cls.decline = {
            "responseType": "exception",
            "responseCode": "D05",
            "responseMessage": "Declined. Do not honour.",
        }
