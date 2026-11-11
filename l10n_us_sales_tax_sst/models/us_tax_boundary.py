# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class UsTaxBoundary(models.Model):
    _name = "us.tax.boundary"
    _description = "SST Address/ZIP Boundary Record"
    _order = "record_type, zip, id"
    _rec_name = "zip"

    # Record type from the SST boundary file: A=address range, 4=ZIP+4, Z=ZIP5.
    record_type = fields.Selection(
        [("A", "Address"), ("4", "ZIP+4"), ("Z", "ZIP5")],
        required=True,
        index=True,
    )
    begin_date = fields.Date(index=True)
    end_date = fields.Date(index=True, help="Empty / 2999-12-31 means open-ended.")
    # Address-range fields (record type A). Kept as strings (may be alpha PO box).
    addr_low = fields.Char()
    addr_high = fields.Char()
    odd_even = fields.Selection([("O", "Odd"), ("E", "Even"), ("B", "Both")])
    street_pre_dir = fields.Char()
    street_name = fields.Char(index=True)
    street_suffix = fields.Char()
    street_post_dir = fields.Char()
    city = fields.Char(index=True)
    # ZIP fields — strings to preserve leading zeros.
    zip = fields.Char(string="ZIP", size=5, index=True)
    zip4 = fields.Char(string="ZIP+4", size=4)
    zip_low = fields.Char(size=5, index=True)
    zip4_low = fields.Char(size=4)
    zip_high = fields.Char(size=5, index=True)
    zip4_high = fields.Char(size=4)
    zip9_low = fields.Char(
        string="ZIP+4 Range Low",
        size=9,
        compute="_compute_zip9_range",
        store=True,
        index=True,
    )
    zip9_high = fields.Char(
        string="ZIP+4 Range High",
        size=9,
        compute="_compute_zip9_range",
        store=True,
        index=True,
    )
    fips_state = fields.Char(string="FIPS State", size=2, index=True)
    fips_county = fields.Char(string="FIPS County", size=3)
    fips_place = fields.Char(string="FIPS Place", size=5)
    state_id = fields.Many2one(
        "res.country.state",
        domain=[("country_id.code", "=", "US")],
        index=True,
    )
    # The state + county + place + special-district jurisdictions this row
    # resolves to (linked at import from the FIPS codes via the rate file).
    jurisdiction_ids = fields.Many2many(
        "us.tax.jurisdiction",
        string="Jurisdictions",
    )
    county_undetermined = fields.Boolean(
        help="This record resolves no county although the state publishes "
        "county jurisdictions — the local tax it carries is booked to a "
        "placeholder district and cannot be reported as a county.",
    )
    source = fields.Char(default="sst")
    import_batch_id = fields.Many2one("us.tax.import.batch")

    @api.depends("zip", "zip4", "zip_low", "zip4_low", "zip_high", "zip4_high")
    def _compute_zip9_range(self):
        """Pack each ZIP bound with its own +4 bound into one sortable value.

        A published range may span two ZIPs (``55012-0011 .. 55013-9746``), so
        comparing the +4 independently of the ZIP excludes 55013-0001.
        """
        for rec in self:
            low_zip = rec.zip_low or rec.zip
            high_zip = rec.zip_high or rec.zip
            low_4 = rec.zip4_low or rec.zip4 or "0000"
            high_4 = rec.zip4_high or rec.zip4 or "9999"
            rec.zip9_low = low_zip.zfill(5) + low_4.zfill(4) if low_zip else False
            rec.zip9_high = high_zip.zfill(5) + high_4.zfill(4) if high_zip else False
