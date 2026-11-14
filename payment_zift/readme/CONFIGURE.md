Go to *Invoicing → Configuration → Payment Providers*, open **Zift**, and fill
in the three credentials Zift issues for the merchant account:

- **User Name**
- **Password**
- **Account ID**

All three travel in the body of every request. Leave **Live Mode** disabled
until they have been proven against the sandbox. Odoo 20 uses `is_live`, not
the older provider State selector: sandbox traffic goes to
`sandbox-secure.zift.io`, and live traffic goes to `secure.zift.io`.

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

## Optional payer processing-fee pass-through

The setting **Pass gateway processing fees to the payer** is disabled by
default. Enable it only for a Zift merchant profile configured to collect and
retain its convenience fee separately from the merchant's payment principal.
This implementation adds no merchant-defined markup or fee income.

For interactive card and ACH payments, including saved methods, Odoo requests
`requestType=convenience-fee` using the tokenized instrument and principal in
cents. The payer sees principal, fee and total and must choose **Accept fee and
pay**. Cancel sends no financial request. Quotes expire after ten minutes and
are bound to the payer, instrument, merchant profile, currency and amount.
Changed inputs require a new quote. Validation transactions do not incur fees.
Off-session charging cannot bypass acceptance; fee mode requires automatic
capture. Keep fee mode disabled for charge-on-ship/manual-capture profiles.

The sale sends principal as `amount` and the accepted fee separately as
`feeAmount`. Transaction and invoice amounts stay at principal; the gateway's
retained fee does not become merchant revenue or tenant credit. This requires
`account_payment` so native invoice settlement uses the original principal.
Accepted amounts and time are retained on the transaction and payment status.
ACH acceptance remains pending; fee acceptance is not settlement confirmation.

Odoo refunds send a positive principal amount with `feeAmount=0`. Gateway fee
refunds require separate handling under the actual merchant policy; this is not
a statement that fees are legally nonrefundable. A timeout, incomplete response
or principal/fee/instrument mismatch leaves an error requiring gateway inquiry;
Odoo will not automatically retry a consumed quote. A database failure around
an external request still requires reconciliation, not blind resubmission.

Protocol basis: Zift's [Convenience Fee integration notes](https://docs.zift.io/processing-api/realtime/notes/integration-notes-provider-response-data)
and [fee policy fields](https://docs.zift.io/components/223). This is the
additional convenience-fee model, distinct from a service fee withheld out of
a remitted total. Merchant-profile eligibility, ACH/card permissions, exact
response amount semantics, fee refunds and settlement must be verified with
issued sandbox credentials before enabling this option in production. All
local acceptance traffic uses synthetic mocked responses.
