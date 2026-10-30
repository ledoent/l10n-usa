Go to *Invoicing → Configuration → Payment Providers*, open **Zift**, and fill
in the three credentials Zift issues for the merchant account:

- **User Name**
- **Password**
- **Account ID**

All three travel in the body of every request. Leave *State* on **Test** until
they have been proven against the sandbox; the module points at
`sandbox-secure.zift.io` in test and `secure.zift.io` when the provider is
enabled.

Zift settles in **USD** only, and ACH Direct Debit is restricted to the United
States and Puerto Rico.

## PCI scope — read before enabling this in production

Zift documents two ways to collect a card and **neither is an iframe**:

1. **Hosted Payment Pages** — a redirect to Zift's own page.
2. **proxynization.js** — in Zift's words, "create your own payment page and
   utilize our proxynization API to help reduce your PCI scope".

**This module implements the second.** The card and bank fields are rendered on
the Odoo payment page and read by a script served into that page. No card
number or account number reaches an Odoo server — but under the PCI SSC's own
division, what decides the Self-Assessment Questionnaire is *whose code runs on
the capture page*, not where the data is posted. A redirect or a third-party
iframe is SAQ A eligible; a merchant script or Direct Post implementation is
**SAQ A-EP**, which carries roughly 140–190 requirements against SAQ A's
twenty-odd, plus quarterly ASV scanning.

Zift's claim to "reduce PCI scope" is accurate. It is a different claim from
SAQ A eligibility. Choosing this module over the redirect is a compliance
decision for whoever signs the attestation. **Nobody who wrote this module is a
QSA**, and nothing here is compliance advice.

## ACH behaves differently from card, by design

An accepted ACH debit is recorded as **pending**, not confirmed, and the
invoice is left unreconciled. That is correct: the debit has entered the ACH
network and settles in one to three business days, and it can be returned after
that.

**Nothing currently resolves a pending debit automatically.** Zift sends
asynchronous settlement notifications, but how it authenticates a callback is
not published, so this module ships no notification endpoint (see ROADMAP).
Until that is answered, ACH payments must be confirmed against the bank by a
person. Plan for that before enabling ACH, or enable card only.
