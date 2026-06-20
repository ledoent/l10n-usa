# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from ..services.provider_ziptax import ProviderZipTax
from .common import UsTaxBaseTest


class TestProviderRegistry(UsTaxBaseTest):
    def _provider(self, code):
        # Providers ship inactive by default → bypass the active filter.
        rec = (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("code", "=", code)], limit=1)
        )
        self.assertTrue(rec, f"provider {code} should exist from data")
        return rec

    def test_over_limit_filter_is_searchable(self):
        """The "Over Monthly Limit" search filter must not crash: limit_status
        is stored so it can be filtered (a field-to-field domain cannot)."""
        prov = self._provider("ziptax")
        prov.write({"monthly_call_limit": 100, "calls_this_month": 150})
        self.assertEqual(prov.limit_status, "exceeded")
        found = (
            self.env["us.tax.provider"]
            .with_context(active_test=False)
            .search([("limit_status", "=", "exceeded")])
        )
        self.assertIn(prov, found)

    def test_registry_lists_base_providers(self):
        classes = self._provider("ziptax")._provider_service_classes()
        self.assertTrue({"local", "ziptax", "api_ninjas"} <= set(classes))

    def test_get_service_returns_class(self):
        self.assertIs(self._provider("ziptax")._get_provider_service(), ProviderZipTax)

    def test_resolve_named_jurisdictions_creates_and_skips_zero(self):
        svc = ProviderZipTax(self._provider("ziptax"))
        result = svc.resolve_named_jurisdictions(
            "NY",
            [
                {"level": "state", "name": None, "rate": 0.04},
                {"level": "county", "name": "Kings", "rate": 0.0475},
                {"level": "city", "name": "New York", "rate": 0.0},
            ],
        )
        # Zero-rate city is dropped; state + county remain.
        self.assertEqual({j["level"] for j in result}, {"state", "county"})
        county = next(j for j in result if j["level"] == "county")
        jur = self.env["us.tax.jurisdiction"].browse(county["jurisdiction_id"])
        self.assertEqual(jur.name, "Kings")
        self.assertEqual(jur.type, "county")
        self.assertEqual(jur.state_id, self.ny)

    def test_resolve_named_jurisdictions_reuses_existing(self):
        svc = ProviderZipTax(self._provider("ziptax"))
        comps = [{"level": "county", "name": "Erie", "rate": 0.01}]
        first = svc.resolve_named_jurisdictions("NY", comps)
        second = svc.resolve_named_jurisdictions("NY", comps)
        self.assertEqual(first[0]["jurisdiction_id"], second[0]["jurisdiction_id"])

    def test_ziptax_names_from_raw(self):
        svc = ProviderZipTax(self._provider("ziptax"))
        normalized = {
            "state_rate": 0.04,
            "county_rate": 0.01,
            "city_rate": 0.0,
            "district_rate": 0.0,
        }
        raw = {"geoCounty": "Erie", "geoCity": "Buffalo"}
        result = svc._named_jurisdictions("NY", normalized, raw)
        by_level = {j["level"]: j for j in result}
        self.assertEqual(by_level["county"]["label"], "Erie")
        self.assertTrue(by_level["county"]["jurisdiction_id"])
