from stdnum.us import rtn

from odoo import api, models
from odoo.exceptions import ValidationError


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    @api.constrains("clearing_number", "clearing_label_id")
    def validate_clearing_number(self):
        for bank in self.filtered("clearing_number"):
            country_code = bank.clearing_label_id.country_code
            if country_code == "US" and not rtn.is_valid(bank.clearing_number):
                raise ValidationError(
                    self.env._(
                        "%s is not a valid US routing number!", bank.clearing_number
                    )
                )
