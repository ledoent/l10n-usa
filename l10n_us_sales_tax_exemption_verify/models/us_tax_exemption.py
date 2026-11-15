# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..services.verifier_base import VerificationError


class UsTaxExemption(models.Model):
    _inherit = "us.tax.exemption"

    verification_ids = fields.One2many(
        "us.tax.exemption.verification", "exemption_id", string="Verifications"
    )
    verification_count = fields.Integer(compute="_compute_verification", store=True)
    last_verification_id = fields.Many2one(
        "us.tax.exemption.verification", compute="_compute_verification", store=True
    )
    last_verified_on = fields.Datetime(
        related="last_verification_id.verified_on", store=True
    )
    verification_result = fields.Selection(
        related="last_verification_id.result", store=True, string="Verification"
    )

    @api.depends("verification_ids.verified_on", "verification_ids.result")
    def _compute_verification(self):
        for rec in self:
            # Two checks in the same transaction share a timestamp to the
            # second, so break the tie on id — same order the model declares.
            checks = rec.verification_ids.sorted(
                key=lambda v: (v.verified_on, v.id), reverse=True
            )
            rec.verification_count = len(checks)
            rec.last_verification_id = checks[:1]

    def _verification_state(self):
        """The state whose authority should be asked about this certificate.

        A blanket certificate covers several states, so there is no single
        answer; the caller passes one explicitly when it matters. Defaults to
        the only covered state when there is exactly one.
        """
        self.ensure_one()
        return (
            self.state_ids
            if len(self.state_ids) == 1
            else self.env["res.country.state"]
        )

    def action_verify(self, state=None, verifier=None, **kwargs):
        """Run a verification and record it, whatever the outcome.

        A negative or inconclusive answer is recorded too — the point of the
        trail is what was checked and when, not only the good news.
        """
        Verification = self.env["us.tax.exemption.verification"]
        records = Verification
        for certificate in self:
            target_state = state or certificate._verification_state()
            source = verifier or self.env["us.tax.exemption.verifier"]._for_state(
                target_state
            )
            if not source:
                raise UserError(
                    self.env._("No verifier is configured for this certificate.")
                )
            service = source._get_service()
            state_code = target_state.code or ""
            if not service.covers(state_code):
                raise UserError(
                    self.env._(
                        "%(verifier)s does not cover %(state)s.",
                        verifier=source.name,
                        state=state_code or self.env._("that state"),
                    )
                )
            vals = {
                "exemption_id": certificate.id,
                "verifier_id": source.id,
                "verifier_code": source.code,
                "mode": source.mode,
                "state_id": target_state.id if target_state else False,
            }
            try:
                outcome = service.verify(certificate, state_code, **kwargs)
            except VerificationError as exc:
                # Unreachable is not the same as invalid: record that we tried
                # and could not tell, and leave the certificate alone.
                vals.update(
                    {"result": "inconclusive", "detail": str(exc)[:200], "payload": ""}
                )
                records |= Verification.create(vals)
                continue
            vals.update(
                {
                    "result": outcome.get("result", "inconclusive"),
                    "reference": outcome.get("reference", ""),
                    "detail": (outcome.get("detail") or "")[:200],
                    "payload": outcome.get("payload", ""),
                }
            )
            records |= Verification.create(vals)
        return records

    def action_open_verifications(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Verifications"),
            "res_model": "us.tax.exemption.verification",
            "view_mode": "list,form",
            "domain": [("exemption_id", "=", self.id)],
            "context": {"default_exemption_id": self.id},
        }
