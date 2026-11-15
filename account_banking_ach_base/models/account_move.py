from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def create_account_payment_line(self):
        today = fields.Date.context_today(self)
        for invoice in self:
            mandate = invoice.mandate_id
            if (
                not mandate
                or invoice.payment_mode_id.payment_method_id.code != "ACH-In"
            ):
                continue
            invoice_date = fields.Date.from_string(invoice.invoice_date)
            delay_expired = invoice_date + timedelta(days=mandate.delay_days)
            if today < delay_expired:
                raise UserError(
                    self.env._(
                        "To satisfy payment mandate, cannot add "
                        "invoice %(name)s to Debit Order until %(delay_expired)s!",
                        name=invoice.name,
                        delay_expired=delay_expired.strftime("%Y-%m-%d"),
                    )
                )
        return super().create_account_payment_line()
