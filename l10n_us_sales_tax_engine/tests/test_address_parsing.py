# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from ..services.address_resolver import (
    house_number,
    normalize_zip,
    resolve_invoice_address,
    split_zip,
)
from .common import UsTaxBaseTest


class TestAddressParsing(UsTaxBaseTest):
    """ZIP+4 and house number have to reach the providers that can use them."""

    def test_split_zip(self):
        self.assertEqual(split_zip("55013-0001"), ("55013", "0001"))
        self.assertEqual(split_zip("550130001"), ("55013", "0001"))
        self.assertEqual(split_zip("55013"), ("55013", ""))
        # A truncated +4 is not a +4.
        self.assertEqual(split_zip("55013-001"), ("55013", ""))
        self.assertEqual(split_zip("ABC"), ("", ""))
        self.assertEqual(split_zip(False), ("", ""))

    def test_normalize_zip_still_returns_five_digits(self):
        self.assertEqual(normalize_zip("55013-0001"), "55013")

    def test_house_number(self):
        self.assertEqual(house_number("100 Main St"), "100")
        self.assertEqual(house_number(" 12B Oak Ave"), "12")
        self.assertEqual(house_number("PO Box 44"), "")
        self.assertEqual(house_number(False), "")

    def test_partner_address_carries_zip4_and_street(self):
        partner = self.env["res.partner"].create(
            {
                "name": "ZIP+4 Buyer",
                "street": "100 Main St",
                "city": "Lindstrom",
                "zip": "55013-0001",
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )
        move = self.env["account.move"].create(
            {"move_type": "out_invoice", "partner_id": partner.id}
        )
        address = resolve_invoice_address(move)
        self.assertEqual(address["zip"], "55013")
        self.assertEqual(address["zip4"], "0001")
        self.assertEqual(address["street"], "100 Main St")


class TestCacheKey(UsTaxBaseTest):
    def test_zip5_key_is_unchanged_by_the_optional_parts(self):
        Cache = self.env["us.tax.api.cache"]
        self.assertEqual(
            Cache.build_hash("55013", "MN", "TANGIBLE", "2026-07"),
            Cache.build_hash("55013", "MN", "TANGIBLE", "2026-07", zip4="", street=""),
        )

    def test_finer_addresses_get_their_own_key(self):
        Cache = self.env["us.tax.api.cache"]
        zip5 = Cache.build_hash("55013", "MN", "TANGIBLE", "2026-07")
        zip9 = Cache.build_hash("55013", "MN", "TANGIBLE", "2026-07", zip4="0001")
        other = Cache.build_hash("55013", "MN", "TANGIBLE", "2026-07", zip4="9999")
        rooftop = Cache.build_hash(
            "55013", "MN", "TANGIBLE", "2026-07", zip4="0001", street="100 Main St"
        )
        self.assertEqual(len({zip5, zip9, other, rooftop}), 4)
