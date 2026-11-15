# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Manual verification — a person checked, and we record what they saw.

This is the default and it covers most of the country. Georgia's GATE card,
for instance, is verified through a web portal with no service behind it, so
the only honest thing to record is that a named user checked it on a date and
what the portal said. That is still worth far more than a certificate whose
"valid" flag has no provenance at all.
"""

from .verifier_base import VerifierBase


class VerifierManual(VerifierBase):
    CODE = "manual"
    NAME = "Manual check"
    MODE = "manual"
    STATES = ()

    def verify(self, certificate, state_code, **kwargs):
        result = kwargs.get("result") or "verified"
        return {
            "result": result,
            "reference": certificate.certificate_number or "",
            "detail": kwargs.get("detail")
            or self.env._("Checked by %(user)s", user=self.env.user.name),
            "payload": "",
        }
