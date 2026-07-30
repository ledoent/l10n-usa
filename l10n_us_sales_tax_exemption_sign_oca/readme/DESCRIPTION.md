Collects US sales tax exemption certificates through
[sign_oca](https://github.com/OCA/sign), which signs documents in the Odoo
portal rather than through an external service.

When a certificate nears expiry the renewal cron sends the customer a signature
request. What comes back is read as data — covered states, exemption type and
certificate number — rather than only filed as a PDF.

A signed certificate is recorded as *Signed by Customer*. It does not exempt
anything until somebody approves it.

This is the same seam the DocuSeal bridge plugs into, and both can be installed
at once: each company picks its backend.
