Gives exemption certificates a **term** and a **renewal path**, and provides
the single entry point a signature integration writes back through.

The base exemption module records a certificate and expires it when its date
passes. That leaves two gaps: nothing says how long a certificate should run
in the first place, and expiry is a dead end — the certificate lapses and
sales start being taxed, with no prompt to collect a replacement.

**Validity** is resolved most-specific-first: a rule for a state and reason,
then either alone, then the reason's own term, then the company default.
States genuinely differ — some issue certificates that never expire at all,
which is why `never expires` is a setting rather than a very large number.

**Renewal** requests a replacement a configurable period before expiry, so a
signed certificate is on file before the old one lapses rather than after.

This module deliberately knows nothing about signatures. It exposes
`_request_renewal()` as a no-op hook and `_record_signed_certificate()` as the
way back in; a bridge module supplies the signature stack. Keeping that seam
means the fiscal rules do not drag an e-signature vendor — or an Enterprise
dependency — behind them.
