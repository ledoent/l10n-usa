# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Payment Provider: Zift",
    "version": "20.0.1.0.0",
    "category": "Accounting/Payment Providers",
    "sequence": 350,
    "summary": (
        "Pay invoices and orders by card or ACH bank transfer through the Zift "
        "gateway, with tokenization and charge-on-ship."
    ),
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "countries": ["us"],
    "depends": ["account_payment"],
    # Order matters, and it differs from an in-tree provider's on purpose.
    # Core providers list the methods before the provider because `payment`
    # has already created their provider record; Zift's is created below, by
    # this module, so the methods that reference it have to come after. The
    # templates stay first either way — the provider record refs the inline
    # form view.
    "data": [
        "views/payment_zift_templates.xml",
        "views/payment_provider_views.xml",
        "views/payment_transaction_views.xml",
        "data/payment_provider_data.xml",
        "data/payment_method_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "payment_zift/static/src/interactions/payment_form.esm.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}
