These are gaps in Zift's published documentation, not decisions deferred for
convenience. Each one is a thing this module declines to invent.

- **No notification endpoint.** Zift sends asynchronous notifications for ACH
  settlements, returns, and Notices of Change — the NACHA C01–C06 corrections
  that replace a stored account's token, routing number, holder name or
  account type. Handling them needs an HTTP endpoint, and an endpoint that
  rewrites stored payment credentials has to authenticate its caller. How Zift
  signs or authenticates a callback is not in the public documentation, so the
  route is absent rather than guessed at.

- **ACH settlement is therefore manual.** A pending debit stays pending until
  somebody confirms it against the bank. Resolving it automatically depends on
  the point above.

- **Response-code semantics are coarse.** Which `responseCode` values are an
  acceptance, a soft decline and a hard decline is not documented. Anything
  this module does not recognise is treated as an error, which is safe and
  blunt: a retryable decline currently looks the same as a permanent one.

- **No Level II / Level III data for cards.** The mapping is well understood
  and deliberately omitted here. `commodityCode` is `String(4)` and
  acquirer-designated, and nothing says which values a given acquirer expects —
  an unrecognised code can fail the record outright, where an absent optional
  field simply degrades. Sending it needs an answer from the acquirer first.

- **The buyer's PO number has no obvious home.** Zift's `orderCode` is the
  merchant's identifier, which this module fills with the transaction
  reference. The number a purchasing-card holder reconciles against is the
  buyer's own PO, and no published field is clearly for it.

- **Untested against the live gateway.** Every test here runs against mocked
  responses. Nothing has been proven against Zift because no sandbox
  credential has been issued; the gateway rejects on credentials and nothing
  else, so the whole integration is provable the day one arrives.
