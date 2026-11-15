# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # account_payment's install hook skips providers whose module is currently
    # "to upgrade". Register this provider after the dependency has installed.
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["payment.provider"]._setup_payment_method("zift")
