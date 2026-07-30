Set the default term and lead time under *Accounting → Configuration →
Settings → US Sales Tax Engine*.

Where a state or an exemption reason carries its own term, add a row under
*US Sales Tax → Configuration → Certificate Validity*. A rule naming both a
state and a reason wins over one naming either.

The daily cron requests a replacement for certificates inside the lead
window. On its own this module only logs that a renewal is due — install a
signature bridge for it to actually send anything.
