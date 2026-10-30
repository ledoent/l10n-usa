Adds **Zift** as a payment provider, so customers can pay invoices and orders
by card or by ACH bank transfer.

Zift exposes a single form-encoded gateway endpoint where a `requestType` field
selects the operation. This module implements the direct (inline) flow: the
payment details are tokenized in the browser and the server charges the token,
so no card number or bank account number ever reaches Odoo.

Both methods are supported and they behave differently on purpose:

- **Card** — an approval is an issuer guaranteeing the funds, so the payment is
  confirmed immediately. Manual capture is available.
- **ACH direct debit** — an accepted debit has only entered the ACH network. It
  settles in one to three business days and can be returned after that, so the
  transaction is recorded as **pending** and the invoice is *not* reconciled
  until settlement is confirmed.

Tokenization uses Zift's `account-verification`, a genuine $0 operation that
places no hold on the customer's account and returns a durable token. For bank
accounts it runs with `verificationMode=PF`, so a failed verification declines
the tokenization rather than storing an account that cannot be debited.
