Records **how an exemption certificate was verified**, and checks it against
the issuing state where that is possible at all.

Without this, a certificate is marked valid because somebody clicked a
button. Nothing records who checked it, when, against what, or what the
authority actually said — which is the first thing asked for when a zero-tax
line is questioned.

States differ enormously in what they expose, so a verifier declares one of
three modes:

- **Real-time API** — the source answers over the wire. Texas is the
  worked example: a certificate carries the purchaser's 11-digit taxpayer
  number, and the Comptroller publishes active sales tax permit holders.
- **Batch** — the source accepts a request and replies out of band, so the
  verification stays pending until the reply is reconciled. Florida's resale
  certificate verification works this way.
- **Manual** — a person checked and recorded what they saw, with a
  screenshot or letter attached. This is the honest answer for most of the
  country, including Georgia's GATE programme, whose only route is a web
  portal.

Every attempt is recorded, including the ones that come back negative or
that could not be completed. A source being unreachable is deliberately kept
distinct from a certificate being invalid: the first means we know nothing
and the certificate is left alone, the second is an answer.
