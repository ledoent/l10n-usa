# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Resolve a US address to its SST jurisdiction set via the boundary file."""

import re

from odoo.addons.l10n_us_sales_tax_engine.services.address_resolver import house_number

_WORD = re.compile(r"[A-Z0-9]+")


def _words(text):
    return set(_WORD.findall((text or "").upper()))


class SstResolver:
    def __init__(self, env):
        self.env = env

    def resolve(self, state, zip5, doc_date, zip4=None, street=None):
        """Return the us.tax.jurisdiction recordset for an address, or empty."""
        boundary = self.resolve_boundary(state, zip5, doc_date, zip4, street)
        if not boundary:
            return self.env["us.tax.jurisdiction"]
        return boundary.jurisdiction_ids

    def resolve_boundary(self, state, zip5, doc_date, zip4=None, street=None):
        """Return the boundary record for an address via the SST A → 4 → Z tiers."""
        return (
            self._match_address(state, zip5, street, doc_date)
            or self._match_zip4(state, zip5, zip4, doc_date)
            or self._match_zip5(state, zip5, doc_date)
        )

    # ── Tier matchers (A → 4 → Z) ─────────────────────────────────────────────

    def _date_domain(self, doc_date):
        return [
            "|",
            ("begin_date", "=", False),
            ("begin_date", "<=", doc_date),
            "|",
            ("end_date", "=", False),
            ("end_date", ">=", doc_date),
        ]

    def _zip_domain(self, zip5):
        # Either a single ZIP on the row, or zip5 within the row's ZIP range.
        return [
            "|",
            ("zip", "=", zip5),
            "&",
            ("zip_low", "<=", zip5),
            ("zip_high", ">=", zip5),
        ]

    def _match_zip5(self, state, zip5, doc_date):
        if not zip5:
            return self.env["us.tax.boundary"]
        domain = (
            [("state_id", "=", state.id), ("record_type", "=", "Z")]
            + self._date_domain(doc_date)
            + self._zip_domain(zip5)
        )
        return self.env["us.tax.boundary"].search(domain, limit=1)

    def _match_zip4(self, state, zip5, zip4, doc_date):
        if not (zip5 and zip4):
            return self.env["us.tax.boundary"]
        zip9 = zip5.zfill(5) + str(zip4).zfill(4)
        domain = [
            ("state_id", "=", state.id),
            ("record_type", "=", "4"),
            ("zip9_low", "<=", zip9),
            ("zip9_high", ">=", zip9),
        ] + self._date_domain(doc_date)
        return self.env["us.tax.boundary"].search(domain, limit=1)

    def _match_address(self, state, zip5, street, doc_date):
        num = self._as_int(house_number(street))
        if not (zip5 and num is not None):
            return self.env["us.tax.boundary"]
        # Ranges are variable-width integers, so containment must be numeric:
        # "300" <= "2000" is False lexicographically. Filter in Python.
        domain = (
            [("state_id", "=", state.id), ("record_type", "=", "A")]
            + self._date_domain(doc_date)
            + self._zip_domain(zip5)
        )
        words = _words(street)
        for boundary in self.env["us.tax.boundary"].search(domain):
            low = self._as_int(boundary.addr_low)
            high = self._as_int(boundary.addr_high)
            if low is None or high is None or not low <= num <= high:
                continue
            if not self._odd_even_ok(boundary.odd_even, num):
                continue
            if not self._street_ok(boundary, words):
                continue
            return boundary
        return self.env["us.tax.boundary"]

    @staticmethod
    def _street_ok(boundary, words):
        """True when the row's street name appears in the address street.

        Several A ranges in one ZIP share house numbers on different streets,
        so the number alone would book a neighbour's districts.
        """
        name = _words(boundary.street_name)
        return name <= words if name else True

    @staticmethod
    def _as_int(value):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return None

    @classmethod
    def _odd_even_ok(cls, odd_even, num):
        if not odd_even or odd_even == "B":
            return True
        num = cls._as_int(num)
        if num is None:
            return True
        return (odd_even == "O") == (num % 2 == 1)
