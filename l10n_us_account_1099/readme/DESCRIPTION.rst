This module determines, aggregates and exports US **1099-NEC** and
**1099-MISC** information returns from vendor bills.

Its core is a **reportability determination engine**: whether a payment is
reportable is the intersection of

* the payee's **W-9 tax classification** (corporations are generally exempt;
  an LLC is reportable or exempt depending on its C/S/P sub-class),
* the **payment category** (driven by the expense account's 1099 box), with
  corporate-exemption overrides for attorney and medical payments,
* the **payment method** (bills paid by card / third-party network are
  excluded, as the processor reports them on 1099-K), and
* the **effective-dated threshold** for the box and year.

It produces per-payee, per-box report lines and exports a CSV suitable for
upload to the IRS **IRIS** Taxpayer Portal. Transmission is pluggable: a base
adapter is provided so a 3rd-party filer API (Tax1099, Avalara/Track1099) or
direct IRIS A2A can be added later.
