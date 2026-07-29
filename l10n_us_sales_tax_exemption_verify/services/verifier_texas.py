# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Texas — the one state in this module that answers in real time.

Two routes, both from the Comptroller:

* the Active Sales Tax Permit Holders dataset on the state open-data portal,
  which needs no credentials at all;
* the Comptroller's public-data API, which needs a free key and is used when
  one is configured.

A Texas resale certificate carries the purchaser's 11-digit taxpayer number,
so verification means asking whether that number belongs to a holder with an
active permit.
"""

import json
import logging

import requests

from .verifier_base import VerificationError, VerifierBase

_logger = logging.getLogger(__name__)

SOCRATA_URL = "https://data.texas.gov/resource/jrea-zgmq.json"
CPA_API_URL = "https://api.comptroller.texas.gov/public-data/v1/public/sales-tax-payer"


class VerifierTexas(VerifierBase):
    CODE = "us_tx_cpa"
    NAME = "Texas Comptroller"
    MODE = "api"
    STATES = ("TX",)

    def _normalize(self, number):
        """Texas taxpayer numbers are 11 digits; certificates are written with
        spaces and dashes in them."""
        return "".join(ch for ch in (number or "") if ch.isdigit())

    def _query_open_data(self, taxpayer_number):
        response = requests.get(
            SOCRATA_URL,
            params={"taxpayer_number": taxpayer_number, "$limit": 1},
            timeout=self.timeout,
            headers=self.verifier._open_data_headers(),
        )
        response.raise_for_status()
        return response.json()

    def _query_cpa_api(self, taxpayer_number, api_key):
        response = requests.get(
            f"{CPA_API_URL}/{taxpayer_number}",
            timeout=self.timeout,
            headers={"api-key": api_key},
        )
        if response.status_code == 404:
            return []
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]

    def verify(self, certificate, state_code, **kwargs):
        number = self._normalize(certificate.certificate_number)
        if len(number) != 11:
            return {
                "result": "inconclusive",
                "reference": certificate.certificate_number or "",
                "detail": self.env._(
                    "A Texas taxpayer number is 11 digits; got %(n)s.", n=len(number)
                ),
                "payload": "",
            }

        api_key = self.verifier.get_api_key()
        try:
            records = (
                self._query_cpa_api(number, api_key)
                if api_key
                else self._query_open_data(number)
            )
        except requests.RequestException as exc:
            # Unreachable is not the same as invalid — say so rather than
            # letting a network blip look like a bad certificate.
            _logger.warning("Texas verification failed for %s: %s", number, exc)
            raise VerificationError(
                self.env._("Could not reach the Texas Comptroller: %s", exc)
            ) from exc

        if not records:
            return {
                "result": "not_found",
                "reference": number,
                "detail": self.env._("No active sales tax permit for this number."),
                "payload": "[]",
            }

        record = records[0]
        name = (
            record.get("taxpayer_name")
            or record.get("taxpayerName")
            or record.get("outlet_name")
            or ""
        )
        return {
            "result": "verified",
            "reference": number,
            "detail": self.env._("Active permit: %s", name) if name else "",
            "payload": json.dumps(record, indent=1, sort_keys=True)[:8000],
        }
