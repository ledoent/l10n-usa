# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json
from datetime import timedelta

from odoo import fields
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .common import UsTaxBaseTest


class TestJurisdictionBooking(UsTaxBaseTest):
    """Booking composition: the per-jurisdiction breakdown must survive into
    the applied account.tax records — distinct children per level, groups
    keyed by composition (never by state + total alone)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Alpha: city-type jurisdiction where county and city share the SAME
        # rate (1% each) — the collapse trap.
        cls.jur_alpha = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Alphaville",
                "type": "city",
                "state_id": cls.fl.id,
                "county": "ALPHA",
                "city": "ALPHAVILLE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_alpha.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.01,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33201",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_alpha.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        # Beta: same 8% combined total as Alpha, but split differently
        # (6 + 2 city, no county) — the same-total/different-composition trap.
        cls.jur_beta = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Betaville",
                "type": "city",
                "state_id": cls.fl.id,
                "county": "BETA",
                "city": "BETAVILLE",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_beta.id,
                "state_rate": 0.06,
                "county_rate": 0.00,
                "city_rate": 0.02,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "33301",
                "state_id": cls.fl.id,
                "jurisdiction_id": cls.jur_beta.id,
                "confidence": 1.0,
                "source": "test",
            }
        )

    def _order_for_zip(self, zip_code):
        partner = self.env["res.partner"].create(
            {
                "name": f"Customer {zip_code}",
                "zip": zip_code,
                "state_id": self.fl.id,
                "country_id": self.us.id,
            }
        )
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
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

    def test_equal_rate_levels_book_distinct_taxes(self):
        """County 1% + city 1% must produce two distinct child taxes — equal
        rates on different levels must never collapse into one record."""
        order = self._order_for_zip("33201")
        self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        tax = order.order_line.tax_id
        self.assertEqual(tax.amount_type, "group")
        children = tax.children_tax_ids
        self.assertEqual(len(children), 3, "state + county + city children")
        self.assertEqual(
            sorted(children.mapped("amount")), [1.0, 1.0, 6.0], "no collapsed child"
        )
        self.assertEqual(
            len(set(children.mapped("name"))), 3, "child names must be distinct"
        )
        self.assertEqual(
            sorted(children.mapped("us_tax_level")), ["city", "county", "state"]
        )
        city_child = children.filtered(lambda t: t.us_tax_level == "city")
        self.assertEqual(
            city_child.us_tax_jurisdiction_id,
            self.jur_alpha,
            "only the level matching the resolved record's type is tagged",
        )
        other = children - city_child
        self.assertFalse(
            other.us_tax_jurisdiction_id,
            "state/county lines of a city-type record book level-only",
        )

    def test_same_total_different_composition_groups_stay_distinct(self):
        """Two destinations sharing a combined total must keep separate group
        taxes; recalculating one must not rewrite the other's children."""
        order_a = self._order_for_zip("33201")
        order_b = self._order_for_zip("33301")
        engine = self.env["us.tax.engine.service"]
        engine.calculate_for_sale_order(order_a)
        tax_a = order_a.order_line.tax_id
        children_a = tax_a.children_tax_ids
        engine.calculate_for_sale_order(order_b)
        tax_b = order_b.order_line.tax_id
        self.assertNotEqual(tax_a, tax_b, "same total, different composition")
        self.assertEqual(sorted(tax_b.children_tax_ids.mapped("amount")), [2.0, 6.0])
        self.assertEqual(
            tax_a.children_tax_ids,
            children_a,
            "recalculating another destination must not rewrite this group",
        )
        # Recalculate A — must reuse the same group, not create a third.
        engine.calculate_for_sale_order(order_a)
        self.assertEqual(order_a.order_line.tax_id, tax_a)

    def _city_child(self, group):
        return group.children_tax_ids.filtered(lambda t: t.us_tax_level == "city")

    def _rate_alpha_city(self, city_rate, effective_date):
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": self.jur_alpha.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": city_rate,
                "district_rate": 0.00,
                "effective_date": effective_date,
                "source": "test",
            }
        )

    def test_rate_change_updates_the_stable_jurisdiction_tax(self):
        """A rate change on a known jurisdiction updates its child tax in
        place: one stable record per jurisdiction, named without the rate,
        no per-rate copies. The group (keyed by composition) is the same
        record too, with its total label refreshed."""
        engine = self.env["us.tax.engine.service"]
        Tax = self.env["account.tax"]
        order = self._order_for_zip("33201")
        engine.calculate_for_sale_order(order)
        group = order.order_line.tax_id
        city = self._city_child(group)
        self.assertEqual(city.amount, 1.0)
        self.assertEqual(city.name, "US Sales Tax FL ALPHAVILLE", "label, no rate")
        self.assertEqual(group.name, "US Sales Tax FL 8%")
        count = Tax.search_count([("company_id", "=", self.env.company.id)])

        # Alphaville's city rate goes 1% -> 1.5%, effective today.
        self._rate_alpha_city(0.015, fields.Date.today())
        order_new = self._order_for_zip("33201")
        engine.calculate_for_sale_order(order_new)
        group_new = order_new.order_line.tax_id
        self.assertEqual(group_new, group, "same composition, same group record")
        self.assertEqual(self._city_child(group_new), city, "same jurisdiction record")
        self.assertEqual(city.amount, 1.5, "amount follows the rate in force")
        self.assertEqual(group.name, "US Sales Tax FL 8.5%", "label refreshed")
        self.assertEqual(
            Tax.search_count([("company_id", "=", self.env.company.id)]),
            count,
            "a rate change must not mint tax records",
        )
        self.assertAlmostEqual(order_new.amount_tax, 8.5, places=2)

    def test_backdated_document_books_current_rate_and_logs_mismatch(self):
        """A document dated before a rate change resolves the historical rate.
        The shared record is not rewritten to it (that would re-rate every
        open draft): the line books the current amount and the log flags the
        mismatch, keeping both rates in its per-line snapshot."""
        engine = self.env["us.tax.engine.service"]
        self._rate_alpha_city(0.015, fields.Date.today())
        order_now = self._order_for_zip("33201")
        engine.calculate_for_sale_order(order_now)
        city = self._city_child(order_now.order_line.tax_id)
        self.assertEqual(city.amount, 1.5)

        order_old = self._order_for_zip("33201")
        order_old.date_order = fields.Datetime.now() - timedelta(days=30)
        engine.calculate_for_sale_order(order_old)
        group = order_old.order_line.tax_id
        self.assertEqual(self._city_child(group), city)
        self.assertEqual(city.amount, 1.5, "historical rate must not overwrite")
        self.assertEqual(
            group.name, "US Sales Tax FL 8.5%", "label follows the booked amounts"
        )
        log = self.env["us.tax.calculation.log"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", order_old.id)],
            order="id desc",
            limit=1,
        )
        self.assertEqual(log.source, "local", "the source is still where it came from")
        self.assertTrue(log.rate_mismatch)
        booked = next(
            c
            for c in json.loads(log.line_detail)[0]["components"]
            if c["level"] == "city"
        )
        self.assertTrue(booked["rate_mismatch"])
        self.assertEqual(booked["pct"], 1.0, "the rate the document resolved")
        self.assertEqual(booked["booked_pct"], 1.5, "the amount it was booked at")
        self.assertEqual(booked["tax_id"], city.id)

    def test_same_label_in_two_jurisdictions_books_distinct_records(self):
        """Two places sharing a label in one state (two "Springfield" cities)
        must not share a record: the second gets the jurisdiction id in its
        name and both keep their own tag."""
        engine = self.env["us.tax.engine.service"]
        twin = self.env["us.tax.jurisdiction"].create(
            {
                "name": "Alphaville (other county)",
                "type": "city",
                "state_id": self.fl.id,
                "county": "OMEGA",
                "city": "ALPHAVILLE",
            }
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": twin.id,
                "state_rate": 0.06,
                "city_rate": 0.02,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        self.env["us.tax.zip.mapping"].create(
            {
                "zip": "33202",
                "state_id": self.fl.id,
                "jurisdiction_id": twin.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        order_a = self._order_for_zip("33201")
        order_b = self._order_for_zip("33202")
        engine.calculate_for_sale_order(order_a)
        engine.calculate_for_sale_order(order_b)
        city_a = self._city_child(order_a.order_line.tax_id)
        city_b = self._city_child(order_b.order_line.tax_id)
        self.assertNotEqual(city_a, city_b)
        self.assertEqual(city_a.name, "US Sales Tax FL ALPHAVILLE")
        self.assertEqual(city_b.name, f"US Sales Tax FL ALPHAVILLE [#{twin.id}]")
        self.assertEqual(city_b.us_tax_jurisdiction_id, twin)
        self.assertEqual(city_b.amount, 2.0)

    def test_level_only_component_never_shares_a_jurisdiction_record(self):
        """A level-only component (no resolved jurisdiction) reuses an
        untagged record of the same name, healing its level/state tags, but
        never a jurisdiction's record that happens to carry that name —
        sharing it would let this component's rate updates re-rate the
        jurisdiction's drafts."""
        Tax = self.env["account.tax"]
        common = {
            "type_tax_use": "sale",
            "amount_type": "percent",
            "amount": 1.0,
            "company_id": self.env.company.id,
        }
        untagged = Tax.create(
            dict(common, name="US Sales Tax FL ALPHA County 1%", us_tax_level="city")
        )
        order = self._order_for_zip("33201")
        self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        county = order.order_line.tax_id.children_tax_ids.filtered(
            lambda t: t.us_tax_level == "county"
        )
        self.assertEqual(county, untagged, "reused by name")
        self.assertEqual(untagged.us_tax_level, "county", "level healed")
        self.assertEqual(untagged.us_tax_state_id, self.fl, "state healed")
        self.assertFalse(untagged.us_tax_jurisdiction_id)

        untagged.name = "was US Sales Tax FL ALPHA County 1%"
        tagged = Tax.create(
            dict(
                common,
                name="US Sales Tax FL ALPHA County 1%",
                us_tax_level="county",
                us_tax_jurisdiction_id=self.jur_beta.id,
            )
        )
        order2 = self._order_for_zip("33201")
        self.env["us.tax.engine.service"].calculate_for_sale_order(order2)
        county2 = order2.order_line.tax_id.children_tax_ids.filtered(
            lambda t: t.us_tax_level == "county"
        )
        self.assertNotEqual(county2, tagged, "a jurisdiction's record is not shared")
        self.assertEqual(tagged.us_tax_jurisdiction_id, self.jur_beta, "untouched")

    def test_category_specific_rate_books_its_own_record(self):
        """One jurisdiction, two rates on the same day (general goods 1%,
        food 0.5%): each books to its own record and neither calculation
        rewrites the other's amount."""
        engine = self.env["us.tax.engine.service"]
        food_cat = self.env["us.tax.product.category"].search(
            [("code", "=", "FOOD")], limit=1
        )
        # Groceries are exempt by default; this state taxes them at a
        # reduced local rate.
        self.env["us.tax.rule"].create(
            {
                "product_tax_category_id": food_cat.id,
                "state_id": self.fl.id,
                "taxable": True,
            }
        )
        self.env["us.tax.rate"].create(
            {
                "jurisdiction_id": self.jur_alpha.id,
                "product_tax_category_id": food_cat.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.005,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        food = self.env["product.product"].create(
            {
                "name": "Groceries",
                "type": "consu",
                "list_price": 100.0,
                "us_tax_category_id": food_cat.id,
            }
        )
        order_general = self._order_for_zip("33201")
        order_food = self._order_for_zip("33201")
        order_food.order_line.product_id = food
        engine.calculate_for_sale_order(order_general)
        engine.calculate_for_sale_order(order_food)
        city_general = self._city_child(order_general.order_line.tax_id)
        city_food = self._city_child(order_food.order_line.tax_id)
        self.assertNotEqual(city_general, city_food)
        self.assertEqual(city_food.name, "US Sales Tax FL ALPHAVILLE (FOOD)")
        self.assertEqual(city_food.us_tax_product_category_id, food_cat)
        self.assertEqual((city_general.amount, city_food.amount), (1.0, 0.5))
        # Recalculating the general order must not drag the food record along.
        engine.calculate_for_sale_order(order_general)
        self.assertEqual((city_general.amount, city_food.amount), (1.0, 0.5))
        self.assertAlmostEqual(order_food.amount_tax, 7.5, places=2)

    def test_legacy_per_rate_record_is_adopted_and_relabelled(self):
        """A record from before this version ("... ALPHAVILLE 1%", tagged with
        the jurisdiction) is reused as the stable record, not duplicated, and
        its label loses the rate."""
        Tax = self.env["account.tax"]
        legacy = Tax.create(
            {
                "name": "US Sales Tax FL ALPHAVILLE 1%",
                "type_tax_use": "sale",
                "amount_type": "percent",
                "amount": 1.0,
                "company_id": self.env.company.id,
                "us_tax_level": "city",
                "us_tax_state_id": self.fl.id,
                "us_tax_jurisdiction_id": self.jur_alpha.id,
            }
        )
        order = self._order_for_zip("33201")
        self.env["us.tax.engine.service"].calculate_for_sale_order(order)
        self.assertEqual(self._city_child(order.order_line.tax_id), legacy)
        self.assertEqual(legacy.name, "US Sales Tax FL ALPHAVILLE")


@tagged("post_install", "-at_install")
class TestJurisdictionBookingGL(AccountTestInvoicingCommon):
    """End to end: posted invoice books one move line per jurisdiction level
    on the US tax payable account."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_mode", "hybrid"
        )
        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.jurisdiction_gl = jurisdiction = (
            cls.env["us.tax.jurisdiction"]
            .sudo()
            .create(
                {
                    "name": "Miami-Dade GL",
                    "type": "county",
                    "state_id": cls.fl.id,
                    "county": "MIAMI-DADE",
                }
            )
        )
        cls.env["us.tax.rate"].sudo().create(
            {
                "jurisdiction_id": jurisdiction.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "city_rate": 0.00,
                "district_rate": 0.00,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].sudo().create(
            {
                "zip": "33401",
                "state_id": cls.fl.id,
                "jurisdiction_id": jurisdiction.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        cls.env["us.tax.nexus"].sudo().create(
            {
                "company_id": cls.env.company.id,
                "state_id": cls.fl.id,
                "active": True,
                "start_date": "2020-01-01",
            }
        )
        cls.partner_fl = cls.env["res.partner"].create(
            {
                "name": "GL Customer",
                "zip": "33401",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )
        cat_tangible = (
            cls.env["us.tax.product.category"]
            .sudo()
            .search([("code", "=", "TANGIBLE")], limit=1)
        )
        cls.product_gl = cls.env["product.product"].create(
            {
                "name": "GL Widget",
                "type": "consu",
                "list_price": 100.0,
                "us_tax_category_id": cat_tangible.id,
            }
        )

    def test_posted_invoice_books_per_jurisdiction_move_lines(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner_fl,
            invoice_date="2024-06-01",
            products=self.product_gl,
        )
        self.env["us.tax.engine.service"].calculate_for_invoice(invoice)
        invoice.action_post()
        tax_lines = invoice.line_ids.filtered("tax_line_id")
        self.assertEqual(
            len(tax_lines), 2, "one move line per jurisdiction level (state, county)"
        )
        self.assertEqual(
            sorted(tax_lines.mapped("tax_line_id.us_tax_level")),
            ["county", "state"],
        )
        payable = invoice.company_id.get_us_tax_payable_account()
        for line in tax_lines:
            self.assertEqual(
                line.account_id,
                payable,
                "collected tax must book to the US tax payable account",
            )
        self.assertAlmostEqual(sum(tax_lines.mapped("credit")), 7.0, places=2)

    def test_backdated_invoice_pays_the_rate_of_its_date(self):
        """An invoice dated before a county rate change keeps the shared
        record at the current rate but books the historical amount on its
        own tax line, and that amount survives posting."""
        self.env["us.tax.rate"].sudo().create(
            {
                "jurisdiction_id": self.jurisdiction_gl.id,
                "state_rate": 0.06,
                "county_rate": 0.015,
                "effective_date": fields.Date.today(),
                "source": "test",
            }
        )
        engine = self.env["us.tax.engine.service"]
        current = self.init_invoice(
            "out_invoice",
            partner=self.partner_fl,
            invoice_date=fields.Date.today(),  # the helper defaults to 2019
            products=self.product_gl,
        )
        engine.calculate_for_invoice(current)
        county = current.invoice_line_ids.tax_ids.children_tax_ids.filtered(
            lambda t: t.us_tax_level == "county"
        )
        self.assertEqual(county.amount, 1.5)

        old = self.init_invoice(
            "out_invoice",
            partner=self.partner_fl,
            invoice_date="2024-06-01",
            products=self.product_gl,
        )
        engine.calculate_for_invoice(old)
        self.assertEqual(county.amount, 1.5, "not rewound to the 2024 rate")
        log = (
            self.env["us.tax.calculation.log"]
            .sudo()
            .search(
                [("res_model", "=", "account.move"), ("res_id", "=", old.id)],
                order="id desc",
                limit=1,
            )
        )
        self.assertTrue(log.rate_mismatch)
        self.assertEqual(log.source, "local")
        county_line = old.line_ids.filtered(lambda ml: ml.tax_line_id == county)
        self.assertAlmostEqual(county_line.credit, 1.0, places=2, msg="2024 rate")
        self.assertAlmostEqual(old.amount_tax, 7.0, places=2)
        old.action_post()
        county_line = old.line_ids.filtered(lambda ml: ml.tax_line_id == county)
        self.assertAlmostEqual(county_line.credit, 1.0, places=2, msg="kept on post")
        self.assertAlmostEqual(old.amount_total, 107.0, places=2)

    def test_reuses_the_chart_tax_account_instead_of_creating_one(self):
        """Charts already ship a sales-tax account; don't split the balance.

        Creating a second liability alongside the chart's own account would
        scatter the sales-tax balance over two accounts and leave the tax
        report reconciling against the wrong one.
        """
        company = self.env.company
        chart_account = company._us_tax_account_from_chart()
        self.assertTrue(
            chart_account,
            "fixture chart has no sale tax to inherit an account from",
        )
        company.us_tax_payable_account_id = False

        resolved = company.get_us_tax_payable_account()
        self.assertEqual(
            resolved,
            chart_account,
            "engine invented an account instead of reusing the chart's",
        )
        # And it is written back, so the choice is visible in Settings.
        self.assertEqual(company.us_tax_payable_account_id, chart_account)

    def test_explicit_configuration_wins_over_the_chart(self):
        company = self.env.company
        chosen = self.env["account.account"].create(
            {
                "name": "Custom Sales Tax Payable",
                "code": "251900",
                "account_type": "liability_current",
                "company_ids": [(4, company.id)],
            }
        )
        company.us_tax_payable_account_id = chosen
        self.assertEqual(company.get_us_tax_payable_account(), chosen)

    def test_tax_group_is_configured_for_the_tax_closing_entry(self):
        """Odoo reports a group with no payable/receivable account as broken."""
        company = self.env.company
        group = self.env["us.tax.engine.service"]._get_us_tax_group(company)
        self.assertTrue(
            group.tax_payable_account_id,
            "US Sales Tax group has no payable account; tax closing cannot run",
        )
        self.assertTrue(group.tax_receivable_account_id)
        self.assertFalse(
            self.env["account.tax.group"]._check_misconfigured_tax_groups(
                company, company.account_fiscal_country_id or self.us
            ),
            "Odoo still reports the tax groups as misconfigured",
        )
