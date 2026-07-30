Collects US sales tax exemption certificates through
[DocuSeal](https://www.docuseal.com/), an open-source e-signature service.

When a certificate nears expiry the renewal cron sends the customer a DocuSeal
form. What comes back is read as data — covered states, exemption type and
certificate number — rather than only filed as a PDF, so the certificate on
record is usable without anybody retyping it.

A signed certificate is recorded as *Signed by Customer*. It does not exempt
anything until somebody approves it.
