# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSaleTaxSourceAdoption(UsTaxBaseTest):
    """Adopting the engine as the company's sale-tax source.

    The chart's default sale tax only ever displays on an engine-active
    company (the engine replaces it at every calculation point), but it shows
    on quotations and carts before the first calculation. The adopt action
    swaps it for a 0% pending placeholder, reversibly.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.default_tax = cls.env["account.tax"].create(
            {
                "name": "Placeholder 15% (test)",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 15.0,
                "company_id": cls.company.id,
            }
        )
        cls.company.account_sale_tax_id = cls.default_tax
        cls.widget = cls.env["product.product"].create(
            {
                "name": "Adoption Widget",
                "type": "consu",
                "list_price": 100.0,
                "taxes_id": [(6, 0, [cls.default_tax.id])],
            }
        )

    def test_adopt_swaps_default_and_product_taxes(self):
        self.company.action_us_tax_adopt_sale_tax_source()
        pending = self.company._get_us_tax_pending_tax()
        self.assertTrue(self.company.us_tax_sale_tax_adopted)
        self.assertEqual(self.company.account_sale_tax_id, pending)
        self.assertEqual(self.company.us_tax_previous_sale_tax_id, self.default_tax)
        self.assertIn(pending, self.widget.taxes_id)
        self.assertNotIn(self.default_tax, self.widget.taxes_id)

    def test_restore_brings_everything_back(self):
        self.company.action_us_tax_adopt_sale_tax_source()
        self.company.action_us_tax_restore_sale_tax_source()
        self.assertFalse(self.company.us_tax_sale_tax_adopted)
        self.assertEqual(self.company.account_sale_tax_id, self.default_tax)
        self.assertIn(self.default_tax, self.widget.taxes_id)
        self.assertNotIn(self.company._get_us_tax_pending_tax(), self.widget.taxes_id)

    def test_adopt_is_idempotent(self):
        self.company.action_us_tax_adopt_sale_tax_source()
        pending = self.company.account_sale_tax_id
        self.company.action_us_tax_adopt_sale_tax_source()
        self.assertEqual(self.company.account_sale_tax_id, pending)
        # previous must not be overwritten by the second call
        self.assertEqual(self.company.us_tax_previous_sale_tax_id, self.default_tax)

    def test_pending_tax_is_distinct_from_exempt_and_carries_country(self):
        pending = self.company._get_us_tax_pending_tax()
        exempt = self.env["us.tax.engine.service"]._get_or_create_exempt_tax(
            self.company
        )
        self.assertNotEqual(pending, exempt)
        self.assertTrue(pending.country_id)
        self.assertEqual(pending.amount, 0.0)

    def test_new_quotation_shows_pending_zero_not_fifteen(self):
        self.company.action_us_tax_adopt_sale_tax_source()
        partner = self.env["res.partner"].create(
            {"name": "Quote Customer", "country_id": self.us.id}
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "order_line": [
                    (0, 0, {"product_id": self.widget.id, "product_uom_qty": 1})
                ],
            }
        )
        self.assertEqual(order.amount_tax, 0.0)
        self.assertEqual(
            order.order_line.tax_id, self.company._get_us_tax_pending_tax()
        )

    def test_restore_without_adopt_is_a_noop(self):
        before = self.company.account_sale_tax_id
        self.company.action_us_tax_restore_sale_tax_source()
        self.assertEqual(self.company.account_sale_tax_id, before)
