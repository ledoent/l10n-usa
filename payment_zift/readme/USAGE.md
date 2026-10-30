Once the provider is enabled, Zift appears as a payment option wherever Odoo
offers one — the customer portal's *Pay Now* on an invoice, the eCommerce
checkout, and a payment link.

The customer chooses **Card** or **ACH Direct Debit** and fills the fields
inline. Saving the method for later is offered when *Allow Saving Payment
Methods* is enabled on the provider; storing one runs Zift's `$0`
`account-verification`, which places no hold.

What to expect afterwards:

| Method | Transaction state | Invoice |
|---|---|---|
| Card | **Confirmed** (or *Authorized* if manual capture is on) | Reconciled |
| ACH Direct Debit | **Pending** | **Not** reconciled |

A pending ACH transaction is not a failure and should not be retried. The debit
has been accepted into the ACH network and takes one to three business days to
settle. Confirm it against the bank before treating the invoice as paid — see
CONFIGURE for why this is manual today.

Refunds are issued from the transaction, full or partial, and go through Zift's
`credit` operation. Cards additionally support a manual capture of a prior
authorisation, and voiding one before settlement.
