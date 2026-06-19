# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from .common import UsTaxBaseTest


class TestSingleLocalUseRate(UsTaxBaseTest):
    """Texas-style remote-seller single local use rate.

    A remote (interstate) seller that has elected a state's single local use
    rate collects a flat state + single-local rate (TX: 6.25% + 1.75% = 8.00%)
    instead of the actual local rate at each destination ZIP.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.svc = cls.env["us.tax.engine.service"]
        cls.Nexus = cls.env["us.tax.nexus"]
        cls.tx = cls.env["res.country.state"].search(
            [("code", "=", "TX"), ("country_id", "=", cls.us.id)], limit=1
        )
        # A TX destination with a real local rate: 6.25% state + 2.00% city.
        cls.jur_tx = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Houston",
                "type": "city",
                "state_id": cls.tx.id,
                "city": "HOUSTON",
                "fips_state": "48",
            }
        )
        cls.env["us.tax.rate"].create(
            {
                "jurisdiction_id": cls.jur_tx.id,
                "state_rate": 0.0625,
                "county_rate": 0.0,
                "city_rate": 0.02,
                "district_rate": 0.0,
                "effective_date": "2020-01-01",
                "source": "test",
            }
        )
        cls.env["us.tax.zip.mapping"].create(
            {
                "zip": "77001",
                "state_id": cls.tx.id,
                "jurisdiction_id": cls.jur_tx.id,
                "confidence": 1.0,
                "source": "test",
            }
        )
        # Seller in FL -> interstate (remote) relative to TX.
        cls.env.company.partner_id.write(
            {"country_id": cls.us.id, "state_id": cls.fl.id, "zip": "33102"}
        )
        cls.nexus_tx = cls.Nexus.create(
            {"company_id": cls.env.company.id, "state_id": cls.tx.id, "active": True}
        )

    def _tx_base_rate(self):
        prov = self.env["us.tax.provider"].search([("code", "=", "local")], limit=1)
        svc = prov._get_provider_service()(prov)
        return svc.get_rate({"zip": "77001", "state": "TX", "date": "2026-01-15"})

    def test_fl_seller_is_interstate_into_tx(self):
        self.assertTrue(self.svc._is_interstate(self.env.company.id, "TX"))

    def test_no_election_keeps_actual_local_rate(self):
        base = self._tx_base_rate()
        self.assertAlmostEqual(base["total_rate"], 0.0825, places=4)
        self.assertIsNone(
            self.Nexus.get_single_local_rate(self.env.company.id, self.tx.id)
        )

    def test_election_helper_returns_rate(self):
        self.nexus_tx.write(
            {"single_local_rate_elected": True, "single_local_rate": 0.0175}
        )
        self.assertEqual(
            self.Nexus.get_single_local_rate(self.env.company.id, self.tx.id),
            0.0175,
        )

    def test_election_not_elected_returns_none(self):
        self.nexus_tx.write(
            {"single_local_rate_elected": False, "single_local_rate": 0.0175}
        )
        self.assertIsNone(
            self.Nexus.get_single_local_rate(self.env.company.id, self.tx.id)
        )

    def test_single_local_override_flattens_to_state_plus_single(self):
        base = self._tx_base_rate()  # 6.25 + 2.00 city = 8.25 actual
        out = self.svc._apply_single_local_rate(base, 0.0175, "TX")
        self.assertAlmostEqual(out["total_rate"], 0.08, places=4)
        self.assertAlmostEqual(out["state_rate"], 0.0625, places=4)
        self.assertAlmostEqual(out["district_rate"], 0.0175, places=4)
        self.assertEqual(out["county_rate"], 0.0)
        self.assertEqual(out["city_rate"], 0.0)  # actual city rate dropped
        self.assertEqual(out["source"], "single_local")
        labels = [j.get("label") for j in out["jurisdictions"]]
        self.assertTrue(any("Single Local Use" in (lb or "") for lb in labels))
        # State component keeps its jurisdiction tag + FIPS.
        state_j = [j for j in out["jurisdictions"] if j["level"] == "state"][0]
        self.assertEqual(state_j["fips"], "48")
