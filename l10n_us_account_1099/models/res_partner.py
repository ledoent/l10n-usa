# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    us_1099_tax_classification = fields.Selection(
        [
            ("individual", "Individual / Sole proprietor"),
            ("c_corp", "C Corporation"),
            ("s_corp", "S Corporation"),
            ("partnership", "Partnership"),
            ("trust_estate", "Trust / Estate"),
            ("llc", "Limited Liability Company"),
            ("other", "Other"),
        ],
        string="W-9 Tax Classification",
        help="Federal tax classification from the payee's Form W-9 (line 3a). "
        "Drives 1099 reportability: corporations are generally exempt.",
    )
    us_1099_llc_tax_class = fields.Selection(
        [
            ("c", "C = C corporation"),
            ("s", "S = S corporation"),
            ("p", "P = Partnership"),
        ],
        string="LLC Tax Classification",
        help="For an LLC, the tax classification entered on the W-9. An LLC "
        "taxed as a partnership (P) is reportable; as a corporation (C/S) it "
        "is exempt.",
    )
    us_1099_tin_type = fields.Selection(
        [("ssn", "SSN"), ("ein", "EIN")], string="TIN Type"
    )
    us_1099_w9_received = fields.Boolean(string="W-9 on File")
    us_1099_w9_date = fields.Date(string="W-9 Date")
    us_1099_tin_match = fields.Selection(
        [
            ("not_checked", "Not checked"),
            ("matched", "Matched"),
            ("mismatch", "Mismatch"),
            ("invalid", "Invalid"),
        ],
        string="TIN Match Status",
        default="not_checked",
    )
    us_1099_backup_withholding = fields.Boolean(
        string="Subject to Backup Withholding",
        help="Apply 24% backup withholding (missing/invalid TIN or B-notice).",
    )
    us_1099_is_corporation = fields.Boolean(
        string="1099 Corporation (exempt)",
        compute="_compute_us_1099_is_corporation",
        store=True,
        help="Computed from the W-9 classification; corporations are generally "
        "exempt from 1099-NEC/MISC (with category-based exceptions).",
    )

    @api.depends("us_1099_tax_classification", "us_1099_llc_tax_class")
    def _compute_us_1099_is_corporation(self):
        for partner in self:
            classification = partner.us_1099_tax_classification
            partner.us_1099_is_corporation = classification in (
                "c_corp",
                "s_corp",
            ) or (
                classification == "llc"
                and partner.us_1099_llc_tax_class in ("c", "s")
            )
