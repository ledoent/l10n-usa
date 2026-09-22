# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from ..services.address_resolver import _partner_to_address
from .common import UsTaxBaseTest


class TestSourcing(UsTaxBaseTest):
    """Unit tests for origin/destination sourcing (`_sourcing_address`).

    Destination-based sales rate the buyer's ZIP; intrastate sales in an
    origin-based state rate the seller's ship-from ZIP. Interstate sales are
    always destination-based.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["us.tax.engine.service"]
        cls.company = cls.env.company
        cls.tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", cls.us.id)], limit=1
        )

    def _set_origin(self, state, zip_code):
        self.company.partner_id.write(
            {"country_id": self.us.id, "state_id": state.id, "zip": zip_code}
        )

    def test_destination_based_state_keeps_buyer_zip(self):
        # FL is not origin-based → always rate the destination ZIP.
        self._set_origin(self.fl, "33102")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "33101", "FL"),
            "33101",
        )

    def test_origin_based_intrastate_uses_seller_zip(self):
        # TX is origin-based; seller in TX → rate the seller's ship-from ZIP.
        self._set_origin(self.tx, "75001")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "77001", "TX"),
            "75001",
        )

    def test_origin_based_interstate_keeps_buyer_zip(self):
        # Buyer in TX (origin-based) but seller is in FL → interstate → dest ZIP.
        self._set_origin(self.fl, "33101")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "77001", "TX"),
            "77001",
        )

    def test_ca_excluded_from_origin_sourcing(self):
        # CA is a hybrid state we deliberately exclude → destination ZIP.
        ca = self.env["res.country.state"].search(
            [("code", "=", "CA"), ("country_id", "=", self.us.id)], limit=1
        )
        self._set_origin(ca, "90001")
        self.assertEqual(
            self.service._sourcing_zip(False, False, self.company.id, "90210", "CA"),
            "90210",
        )

    def test_origin_based_blank_seller_zip_falls_back_to_destination(self):
        # Origin-based, seller in-state but no ship-from ZIP → fall back to dest.
        # It warns about the misconfiguration; assert (and swallow) that warning
        # so it doesn't trip the OCA checklog gate.
        self._set_origin(self.tx, "")
        logger = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"
        with self.assertLogs(logger, level="WARNING"):
            self.assertEqual(
                self.service._sourcing_zip(
                    False, False, self.company.id, "77001", "TX"
                ),
                "77001",
            )

    def _tx_jurisdiction(self, name, zip_code, county_rate):
        jur = self.env["us.tax.jurisdiction"].create(
            {
                "name": name,
                "type": "county",
                "state_id": self.tx.id,
                "county": name.upper(),
            }
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": jur.id,
                "state_rate": 0.0625,
                "county_rate": county_rate,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        self.env["us.tax.zip.mapping"].create(
            {
                "zip": zip_code,
                "state_id": self.tx.id,
                "jurisdiction_id": jur.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        return jur

    def test_origin_sourcing_rates_the_origin_address_not_a_learned_rooftop(self):
        """Origin sourcing must switch the whole rate-lookup address to the
        ship-from. Sending the origin ZIP with the destination street lets a
        learned destination rooftop win in the resolver and silently undo the
        sourcing."""
        self._tx_jurisdiction("Origin", "75001", 0.01)
        jur_dest = self._tx_jurisdiction("Dest", "77001", 0.02)
        self.env["us.tax.nexus"].create(
            {
                "company_id": self.company.id,
                "state_id": self.tx.id,
                "active": True,
                "start_date": "2020-01-01",
            }
        )
        self.company.partner_id.write(
            {
                "country_id": self.us.id,
                "state_id": self.tx.id,
                "zip": "75001",
                "city": "Dallas",
                "street": "1 Origin St",
            }
        )
        buyer = self.env["res.partner"].create(
            {
                "name": "Houston Buyer",
                "country_id": self.us.id,
                "state_id": self.tx.id,
                "zip": "77001",
                "city": "Houston",
                "street": "2 Dest Ave",
            }
        )
        buyer_address = _partner_to_address(buyer)
        self.env["us.tax.zip.mapping"].learn_jurisdiction(
            buyer_address, jur_dest, source="api"
        )

        rated = self.service._sourcing_address(
            "sale.order", False, self.company.id, buyer_address
        )
        self.assertEqual(rated["zip"], "75001")
        self.assertEqual(rated["address"], "1 Origin St, Dallas, TX 75001")

        order = self.env["sale.order"].create(
            {
                "partner_id": buyer.id,
                "order_line": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    )
                ],
            }
        )
        self.service.calculate_for_sale_order(order)
        self.assertAlmostEqual(
            order.amount_tax, 7.25, places=2, msg="origin 6.25 + 1, not dest 6.25 + 2"
        )
