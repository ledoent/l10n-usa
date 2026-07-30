# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class UsTaxExemption(models.Model):
    _inherit = "us.tax.exemption"

    renewal_requested_on = fields.Datetime(
        readonly=True,
        copy=False,
        help="When a replacement was last requested. Set by the renewal cron "
        "so a certificate is not chased twice, and cleared when a signed "
        "replacement arrives.",
    )
    renewal_due_date = fields.Date(
        compute="_compute_renewal_due_date",
        store=True,
        help="When this certificate becomes eligible for a renewal request.",
    )

    @api.depends("expiry_date", "company_id.us_tax_exemption_renewal_lead_days")
    def _compute_renewal_due_date(self):
        for rec in self:
            lead = rec.company_id.us_tax_exemption_renewal_lead_days or 0
            rec.renewal_due_date = (
                rec.expiry_date - timedelta(days=lead) if rec.expiry_date else False
            )

    # ── Validity ────────────────────────────────────────────────────────────

    @api.model
    def _resolve_validity(self, state, reason, company=None):
        """How long a certificate for ``state`` / ``reason`` is good for.

        Most specific wins: a validity rule, then the reason's own term, then
        the company default. Returns ``(years, never_expires)``; ``years`` is
        meaningless when ``never_expires``.
        """
        company = company or self.env.company
        rule = self.env["us.tax.exemption.validity"]._match(state, reason)
        if rule:
            return rule.validity_years, rule.never_expires
        if reason and reason.never_expires:
            return 0, True
        if reason and reason.validity_years:
            return reason.validity_years, False
        return company.us_tax_exemption_validity_years or 3, False

    @api.model
    def _expiry_for(self, effective_date, state, reason, company=None):
        """The expiry date to stamp on a certificate, or False if open-ended."""
        years, never = self._resolve_validity(state, reason, company)
        if never:
            return False
        return effective_date + relativedelta(years=years)

    # ── Renewal ─────────────────────────────────────────────────────────────

    def _request_renewal(self):
        """Hook: ask the customer for a replacement certificate.

        A no-op here on purpose. This module knows when a certificate needs
        replacing; it should not know how a signature is collected. A bridge
        overrides this — see the DocuSeal and sign_oca addons.
        """
        for rec in self:
            _logger.info(
                "US Tax: %s is due for renewal and no signature bridge is "
                "installed to request one.",
                rec.display_name,
            )
        return False

    @api.model
    def _cron_request_renewals(self):
        """Request a replacement for every certificate nearing expiry.

        ``renewal_requested_on`` is the guard: a certificate is chased once
        and then left alone until a signed replacement clears the field.
        """
        today = fields.Date.context_today(self)
        due = self.search(
            [
                ("state", "=", "valid"),
                ("expiry_date", "!=", False),
                ("renewal_due_date", "<=", today),
                ("renewal_requested_on", "=", False),
            ]
        )
        if not due:
            return 0
        due._request_renewal()
        due.write({"renewal_requested_on": fields.Datetime.now()})
        _logger.info("US Tax: requested %s certificate renewal(s).", len(due))
        return len(due)

    # ── Capture ─────────────────────────────────────────────────────────────

    @api.model
    def _record_signed_certificate(
        self,
        partner,
        state_codes,
        reason_code,
        certificate_number,
        document=None,
        document_filename=None,
        signed_on=None,
        company=None,
    ):
        """Record a certificate a customer has signed.

        The single entry point every signature bridge writes through, so the
        bridges stay thin and the fiscal rules live in one place.

        Idempotent: a bridge may call this more than once for one signature —
        DocuSeal retries a failed webhook twelve times with exponential
        backoff, spanning the better part of a week — so a certificate already
        on file for the same customer, reason, states and number is returned
        untouched rather than duplicated.

        The result is left signed, not approved: the base module holds a
        customer submission until somebody here accepts it. A payload that
        resolves to no known reason or covered state stays a draft, so the gap
        is visible and fixable rather than silently discarded.
        """
        company = company or self.env.company
        partner = partner.commercial_partner_id
        signed_on = signed_on or fields.Date.context_today(self)

        reason = self.env["us.tax.exemption.reason"].search(
            [("code", "=", (reason_code or "").strip().lower())], limit=1
        )
        states = self.env["res.country.state"]
        for code in state_codes or []:
            code = (code or "").strip().upper()
            if not code:
                continue
            found = states.search(
                [("code", "=", code), ("country_id.code", "=", "US")], limit=1
            )
            if found:
                states |= found
            else:
                _logger.warning(
                    "US Tax: unknown state code %r on a signed certificate.", code
                )

        existing = self.search(
            [
                ("partner_id", "=", partner.id),
                ("reason_id", "=", reason.id if reason else False),
                ("certificate_number", "=", certificate_number or False),
                ("company_id", "in", [company.id, False]),
                ("state", "in", ("draft", "signed", "valid")),
            ],
            limit=1,
        )
        if existing and set(existing.state_ids.ids) == set(states.ids):
            _logger.info(
                "US Tax: certificate %s already on file; ignoring a repeat delivery.",
                existing.display_name,
            )
            return existing

        incomplete = not reason or not states
        if incomplete:
            _logger.warning(
                "US Tax: signed certificate for %s could not be fully read — "
                "%s. Saved as draft for review. reason=%r states=%r number=%r",
                partner.display_name,
                "no known exemption reason" if not reason else "no known covered state",
                reason_code,
                state_codes,
                certificate_number,
            )

        vals = {
            "partner_id": partner.id,
            "reason_id": reason.id if reason else False,
            "state_ids": [(6, 0, states.ids)],
            "certificate_number": certificate_number or False,
            "effective_date": signed_on,
            "expiry_date": self._expiry_for(signed_on, states[:1], reason, company),
            "state": "draft",
            "company_id": company.id,
            "renewal_requested_on": False,
        }
        if document:
            vals.update({"document": document, "document_filename": document_filename})
        certificate = self.create(vals)
        if not incomplete:
            certificate.action_mark_signed()
        return certificate

    # ── Supersession ────────────────────────────────────────────────────────

    def action_validate(self):
        """Expire whatever this certificate replaces, once it is accepted.

        Deliberately on approval rather than on capture: dropping a live
        exemption the moment a new form arrived would leave the customer
        taxable until somebody got round to approving the replacement.
        """
        res = super().action_validate()
        for rec in self:
            rec._supersede_replaced()
        return res

    def _supersede_replaced(self):
        """Expire the certificate this one replaces."""
        self.ensure_one()
        if self.state != "valid":
            return self.browse()
        replaced = self.search(
            [
                ("id", "!=", self.id),
                ("partner_id", "=", self.partner_id.id),
                ("reason_id", "=", self.reason_id.id),
                ("state", "=", "valid"),
                ("company_id", "in", [self.company_id.id, False]),
            ]
        ).filtered(lambda c: set(c.state_ids.ids) & set(self.state_ids.ids))
        if replaced:
            replaced.write({"state": "expired", "renewal_requested_on": False})
        return replaced
