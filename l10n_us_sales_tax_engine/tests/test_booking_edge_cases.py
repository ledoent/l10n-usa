# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from types import SimpleNamespace

from odoo.exceptions import UserError
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

from .common import UsTaxBaseTest


class TestExemptTaxCountry(UsTaxBaseTest):
    """The exempt tax must set country_id like the booked taxes do.

    account.tax.country_id is NOT NULL in 18.0 and is precomputed from the
    company's fiscal country, so a company that has neither a fiscal country
    nor a country cannot create one implicitly. The per-jurisdiction booking
    path sets it; the exempt path is reached by exactly the company that has
    no chart of accounts (and therefore no fiscal country) — no nexus rows
    means every calculation ends in exempt_nexus.
    """

    def test_exempt_tax_creates_for_a_company_without_a_fiscal_country(self):
        bare = self.env["res.company"].create({"name": "No Chart Co"})
        bare.write({"country_id": False})
        self.assertFalse(bare.account_fiscal_country_id)
        tax = self.env["us.tax.engine.service"]._get_or_create_exempt_tax(bare)
        self.assertTrue(tax, "exempt tax could not be created")
        self.assertTrue(tax.country_id, "exempt tax must carry an explicit country_id")

    def test_exempt_tax_country_matches_the_booking_path(self):
        company = self.env.company
        svc = self.env["us.tax.engine.service"]
        booked = svc._get_or_create_jurisdiction_tax(
            "FL",
            company,
            {
                "state_rate": 0.06,
                "county_rate": 0.0,
                "city_rate": 0.0,
                "district_rate": 0.0,
                "total_rate": 0.06,
                "source": "local",
            },
        )
        exempt = svc._get_or_create_exempt_tax(company)
        self.assertEqual(exempt.country_id, booked.country_id)


class TestMandatorySingleLocalWithoutRateData(UsTaxBaseTest):
    """A mandatory combined-flat regime does not depend on local rate data.

    Alabama's SSUT is 8% flat for an enrolled remote seller. It replaces state
    + local rather than adding to a state rate, so gating it on a resolved
    state rate means a seller with no Alabama rate rows loaded collects
    nothing on a sale it is required to collect 8% on.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc = cls.env["us.tax.engine.service"]
        cls.al = cls.env["res.country.state"].search(
            [("code", "=", "AL"), ("country_id", "=", cls.us.id)], limit=1
        )
        # Seller in FL → remote relative to AL. No AL jurisdictions, no AL
        # rates: the provider chain will find nothing.
        cls.env.company.partner_id.write(
            {"country_id": cls.us.id, "state_id": cls.fl.id, "zip": "33102"}
        )
        cls.env["us.tax.nexus"].create(
            {
                "company_id": cls.env.company.id,
                "state_id": cls.al.id,
                "active": True,
                "single_local_mandatory": True,
                "single_local_rate": 0.08,
                "single_local_mode": "combined",
            }
        )
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_tax.engine_active", "True")
        ICP.set_param("l10n_us_tax.engine_mode", "local")
        ICP.set_param("l10n_us_tax.fail_policy", "warn")

    def test_ssut_applies_even_though_no_al_rate_is_loaded(self):
        logger = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"
        with self.assertLogs(logger, level="WARNING"):
            result = self.svc._process(
                "sale.order",
                0,
                {"zip": "35004", "state": "AL", "city": "MOODY", "country": "US"},
                [
                    SimpleNamespace(
                        id=0,
                        price_subtotal=100.0,
                        product_id=self.env["product.product"],
                    )
                ],
                "2026-01-15",
                self.env.company.id,
                self.env.company.currency_id.id,
                lambda res: None,
            )
        detail = result["lines"][0]["rate_detail"]
        self.assertEqual(detail["source"], "single_local")
        self.assertAlmostEqual(detail["total_rate"], 0.08, places=4)
        self.assertAlmostEqual(result["tax_amount"], 8.0, places=2)

    def test_add_on_mode_still_requires_a_state_rate(self):
        """The Texas-style election adds to a state rate, so with no rate data
        there is nothing to add to and the failure must stay visible."""
        nexus = self.env["us.tax.nexus"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("state_id", "=", self.al.id),
            ],
            limit=1,
        )
        nexus.write({"single_local_mode": "add_on", "single_local_rate": 0.0175})
        logger = "odoo.addons.l10n_us_sales_tax_engine.services.tax_engine"
        with self.assertLogs(logger, level="WARNING"):
            result = self.svc._process(
                "sale.order",
                0,
                {"zip": "35004", "state": "AL", "city": "MOODY", "country": "US"},
                [
                    SimpleNamespace(
                        id=0,
                        price_subtotal=100.0,
                        product_id=self.env["product.product"],
                    )
                ],
                "2026-01-15",
                self.env.company.id,
                self.env.company.currency_id.id,
                lambda res: None,
            )
        self.assertEqual(result["lines"][0]["rate_detail"]["source"], "error")


@tagged("post_install", "-at_install")
class TestPostedInvoiceGuard(AccountTestInvoicingCommon):
    """Recalculating a posted invoice must fail loudly, not silently no-op."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.engine_active", "True"
        )
        cls.us = cls.env.ref("base.us")
        cls.fl = cls.env["res.country.state"].search(
            [("code", "=", "FL"), ("country_id", "=", cls.us.id)], limit=1
        )
        jurisdiction = (
            cls.env["us.tax.jurisdiction"]
            .sudo()
            .create(
                {
                    "name": "Posted Guard County",
                    "type": "county",
                    "state_id": cls.fl.id,
                    "county": "GUARD",
                }
            )
        )
        cls.env["us.tax.rate"].sudo().create(
            {
                "jurisdiction_id": jurisdiction.id,
                "state_rate": 0.06,
                "county_rate": 0.01,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].sudo().create(
            {
                "zip": "33402",
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
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Posted Guard Customer",
                "zip": "33402",
                "state_id": cls.fl.id,
                "country_id": cls.us.id,
            }
        )

    def test_recalculating_a_posted_invoice_raises(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner,
            invoice_date="2024-06-01",
            products=self.product_a,
        )
        invoice.action_post()
        stamp = invoice.us_tax_calculated_at
        with self.assertRaises(UserError):
            invoice.action_calculate_us_tax()
        self.assertEqual(
            invoice.us_tax_calculated_at,
            stamp,
            "a refused recalculation must not stamp the document",
        )

    def test_posting_still_calculates(self):
        invoice = self.init_invoice(
            "out_invoice",
            partner=self.partner,
            invoice_date="2024-06-01",
            products=self.product_a,
        )
        invoice.action_post()
        tax_lines = invoice.line_ids.filtered("tax_line_id")
        self.assertTrue(tax_lines, "auto-calculation on post regressed")
