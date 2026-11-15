from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestResPartnerBank(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us_bank = cls.env["res.partner.bank"].create(
            {
                "bank_name": "US Bank",
                "account_number": "US-123",
                "partner_id": cls.env.company.partner_id.id,
                "country_id": cls.env.ref("base.us").id,
            }
        )
        cls.canadian_bank = cls.env["res.partner.bank"].create(
            {
                "bank_name": "Canadian Bank",
                "account_number": "CA-123",
                "partner_id": cls.env.company.partner_id.id,
                "country_id": cls.env.ref("base.ca").id,
            }
        )
        cls.belgium_bank = cls.env["res.partner.bank"].create(
            {
                "bank_name": "Belgium Bank",
                "account_number": "BE-123",
                "partner_id": cls.env.company.partner_id.id,
                "country_id": cls.env.ref("base.be").id,
            }
        )

    def test_routing_number_us_bank(self):
        number = self.us_bank.clearing_number = "310033974"
        bank_name = self.us_bank.bank_name
        self.assertEqual(
            number,
            "310033974",
            f"You should have the routing number {number} for the bank {bank_name}",
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.us_bank.clearing_number = "1"

    def test_routing_number_canadian_bank(self):
        number = self.canadian_bank.clearing_number = "000412162"
        bank_name = self.canadian_bank.bank_name
        self.assertEqual(
            number,
            "000412162",
            f"You should have the routing number 000412162 for the bank {bank_name}",
        )
        # We want to test the exception
        with self.assertRaises(ValidationError):
            self.canadian_bank.clearing_number = "1"
        # Odoo 20's native EFT field no longer accepts the old eight-digit form.
        with self.assertRaises(ValidationError):
            self.canadian_bank.clearing_number = "12162004"

    def test_routing_number_belgium_bank(self):
        number = self.belgium_bank.clearing_number = "5"
        bank_name = self.belgium_bank.bank_name
        self.assertEqual(
            number,
            "5",
            f"You should have the routing number 5 for the bank {bank_name}",
        )
