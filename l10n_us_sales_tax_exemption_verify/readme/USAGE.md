Open a certificate and press **Verify**. The best verifier for the state is
chosen automatically — a state-specific source outranks the manual fallback.
A blanket certificate covers several states and therefore has no single
authority to ask, so pass the state you want checked.

Outcomes are listed under **Verification History** on the certificate, and
across all customers under *US Sales Tax → Certificate Verifications*.

**Texas** works with no credentials, against the state open-data portal. To
use the Comptroller API instead, set the system parameter
`l10n_us_tax.tx_cpa_api_key` to a key from the Comptroller's data portal.
Optionally set `l10n_us_tax.socrata_app_token` to raise the open-data rate
limit.

Adding a state means adding a verifier record and a service class; override
`us.tax.exemption.verifier._verifier_classes()` from your own addon and
update the dict returned by `super()`. No edit to this module is needed.
