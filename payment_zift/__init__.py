# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo.addons.payment import reset_payment_provider, setup_provider

from . import controllers, models


def post_init_hook(env):
    setup_provider(env, "zift")


def uninstall_hook(env):
    reset_payment_provider(env, "zift")
