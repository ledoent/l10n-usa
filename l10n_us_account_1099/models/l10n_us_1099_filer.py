# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import models


class L10nUs1099Filer(models.AbstractModel):
    """Base for 1099 transmission adapters.

    v1 ships the free IRIS Taxpayer Portal CSV export only (see
    ``l10n.us.1099.line._build_csv``). Future adapters -- a 3rd-party filer API
    (Tax1099, Avalara/Track1099) or direct IRIS A2A (TCC + ATS + XML per IRS
    Pub 5718) -- should inherit this model and implement ``transmit``.
    """

    _name = "l10n.us.1099.filer"
    _description = "1099 Transmission Adapter (base)"

    def transmit(self, lines):
        raise NotImplementedError(
            "No 1099 e-file adapter is configured. v1 supports IRIS Portal CSV "
            "export; install/define a transmission adapter to e-file."
        )
