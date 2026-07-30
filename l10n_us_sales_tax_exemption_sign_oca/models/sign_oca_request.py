# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import models

from .us_tax_exemption import FIELD_NUMBER, FIELD_STATE, FIELD_TYPE

_logger = logging.getLogger(__name__)


class SignOcaRequest(models.Model):
    _inherit = "sign.oca.request"

    def _check_signed(self):
        """Record the certificate once the last signer is done.

        Hooked here rather than on ``action_send_signed_request`` — that method
        returns early unless ``sign_oca_send_sign_request_copy`` is set on the
        company, which is a preference about emailing a copy. Hanging the
        write-back off it would make capture depend on an unrelated mail
        setting. ``_check_signed`` is the one place the state becomes signed.

        By the time it runs, ``action_sign`` has already written the merged
        ``signatory_data`` and the signed PDF into ``data``, so both are the
        final versions here.
        """
        self.ensure_one()
        was_signed = self.state == "signed"
        res = super()._check_signed()
        if not was_signed and self.state == "signed":
            self._us_tax_capture_exemption()
        return res

    def _us_tax_capture_exemption(self):
        """Turn a signed request for an exemption certificate into a record."""
        self.ensure_one()
        record = self.record_ref
        if not record or record._name != "us.tax.exemption":
            return self.env["us.tax.exemption"]
        values = self._us_tax_signed_values()
        exemptions = self.env["us.tax.exemption"]
        return (
            exemptions.sudo()
            .with_company(record.company_id)
            ._record_signed_certificate(
                partner=record.partner_id,
                state_codes=exemptions._sign_oca_state_codes(values.get(FIELD_STATE)),
                reason_code=values.get(FIELD_TYPE),
                certificate_number=values.get(FIELD_NUMBER),
                document=self.data,
                document_filename=f"{self.name}.pdf" if self.data else None,
                company=record.company_id,
            )
        )

    def _us_tax_signed_values(self):
        """Flatten ``signatory_data`` to ``{field name: value}``.

        It is a dict keyed by placement-item id, so the field name lives inside
        each entry rather than being the key.
        """
        self.ensure_one()
        return {
            entry.get("name"): entry.get("value")
            for entry in (self.signatory_data or {}).values()
            if entry.get("name")
        }
