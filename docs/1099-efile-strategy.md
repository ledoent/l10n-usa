# US 1099 E-Filing — Strategy & IRIS A2A Feasibility (Proposal)

**Status:** proposal for discussion · **Audience:** OCA `l10n-usa` maintainers / OCA US localization community · **Last updated:** 2026-06-18

This proposes how the OCA community should structure US 1099 information-return
**e-filing** — and answers the recurring question *"should the community pursue
IRS certification?"*

---

## TL;DR

1. **The reusable asset is software, not a certification.** Build a shared,
   filer-agnostic **determination engine** (done: `l10n_us_account_1099`) plus
   thin **transmission adapters**. Do not try to make OCA an IRS transmitter.
2. **Most deployers should e-file through a 3rd-party filer API** (Tax1099,
   Avalara/Track1099) or the free **IRIS Taxpayer Portal CSV** — both avoid
   owning IRS certification.
3. **A direct IRIS A2A adapter is feasible and worth documenting**, but the
   **TCC and ATS pass stay with each deploying company**, not OCA. OCA's value
   is a correct, maintained adapter that reliably passes ATS — not a shared
   credential.
4. **This document + the layered architecture is itself the proposal** to take
   to the community; a maintained engine + adapters + A2A reference is a high-
   value OCA-US deliverable because 1099 is universal and the existing module
   is stranded at 17.0.

---

## 1. Why this matters now

- 1099-NEC/MISC reporting is **universal** to US companies with contractors;
  nearly all cross the **10-return aggregate e-file mandate** (Treasury
  Decision 9972, returns filed on/after 2024-01-01 — all info-return types
  counted together), so e-file is effectively required.
- The legacy **FIRE** system is **retiring after TY2026**; TY2026 returns
  (filed in 2027) are **IRIS-only**. Any new e-file work must target **IRIS**.
- The existing OCA module (`l10n_us_form_1099`) is stranded at **17.0** and is
  a thin "flag vendor + MISC boxes" tool that predates the 1099-NEC split and
  the 2025–26 threshold changes. There is no maintained 18.0 OCA path today.

## 2. The filing landscape

| Path | What it is | Certification needed | Fit |
|---|---|---|---|
| **IRIS Taxpayer Portal** | Free IRS web app; manual key-in or **CSV upload (100 records/file)** | A **TCC** (lightweight, ~24h), **no API**, no ATS | Small/medium filers self-filing; the **v1 default** |
| **IRIS A2A** | Machine-to-machine **XML** API; large batches | **TCC + API Client ID + ATS + schemas (Pub 5718)** | High volume / full automation |
| **3rd-party filer API** (Tax1099, Avalara/Track1099, Sovos) | The filer is the certified transmitter; you call their API | None for you — the filer holds it | Most ERP deployers; adds e-file + **state filing** + TIN matching + W-9 + recipient e-delivery |

## 3. The certification question, answered precisely

**Can OCA hold a certification so members just "file through OCA"? No.**

- A **TCC (Transmitter Control Code)** is issued by the IRS to a **specific
  business** (EIN + named Responsible Officials) via the *IR Application for
  TCC*. The TCC holder is the **transmitter** — the legally responsible party
  sending data to the IRS. OCA is a non-profit association; becoming a
  transmitter that files on members' behalf would make it a **liable filing
  intermediary**, which is not its role and carries real compliance exposure.
- **ATS (Assurance Testing System)** is a communication/assurance test a
  transmitter completes **once** to move *their* TCC to production. It is tied
  to the TCC + the software in use — not a globally inheritable credential.

**What *can* be a shared community asset:** the **software**. OCA can publish
and maintain an A2A adapter that:
- speaks the IRIS A2A protocol correctly (Pub 5718 XML schemas, auth), and
- reliably **passes ATS** when a deployer runs it under **their own TCC**.

So the honest model for self-hosted self-filers is: **OCA ships the adapter;
each company gets its own TCC and does its own (one-time, light) ATS pass.**
The "vendor does ATS once and customers inherit it" pattern is the *commercial
filer* model (Tax1099 et al. *are* the software-developer/transmitter) — it
does not map to self-hosted self-filing.

## 4. Proposed architecture (layered, filer-agnostic)

```
                ┌─────────────────────────────────────────────┐
                │  l10n_us_account_1099  (determination engine) │  ← the moat (shipped)
                │  W-9 classification · account→box category ·  │
                │  payment-method exclusion · effective-dated   │
                │  thresholds · per-payee/box aggregation       │
                └───────────────┬─────────────────────────────┘
                                │ produces 1099 lines
        ┌───────────────────────┼───────────────────────┬───────────────────────┐
        ▼                       ▼                       ▼                       ▼
  CSV → IRIS Portal      filer adapter:          filer adapter:          IRIS A2A adapter
  (free, v1, no cert)    Tax1099 API             Avalara/Track1099 API   (TCC+ATS per deployer)
```

- **`l10n_us_account_1099`** — the engine + IRIS-Portal CSV. *(shipped, 100% tested)*
- **`l10n_us_account_1099_<filer>`** — one thin module per filer API; the
  realistic path for most deployers. Community-maintainable connectors.
- **`l10n_us_account_1099_iris_a2a`** — optional direct A2A; deployer supplies
  their own TCC and runs a one-time ATS pass. The hardest to maintain (yearly
  schema/ATS refresh), so it is **last** and **optional**.

The engine never depends on a transmission choice; adapters inherit the
`l10n.us.1099.filer` base. This keeps the universal/hard part shared and the
certification-bearing part per-deployer and swappable.

## 5. IRIS A2A — what building the adapter actually requires

For whoever takes on `_iris_a2a` (reference, so it isn't re-researched):
- **Enrollment:** IR Application for TCC → **IRIS A2A TCC** + **API Client ID**;
  Responsible Officials + e-Services accounts. TCC approval can take up to ~45
  days.
- **Specs:** **IRS Publication 5718** (IRIS A2A electronic-filing
  specifications) — the XML schema package, per processing year.
- **Transport:** authenticated A2A web service; batches up to ~100 MB.
- **ATS:** mandatory assurance test submissions must pass before production is
  enabled; **re-test when schemas change each processing year**.
- **Lifecycle:** corrections/replacements, acknowledgements, error handling.
- **Maintenance reality:** schemas + ATS recur **annually**; this is the main
  reason to keep A2A optional and prefer filer-API adapters for most users.

## 6. Risks & why filer-agnostic

- **Annual drift:** thresholds, box rules, and A2A schemas change yearly
  (e.g. OBBBA's $600→$2,000 for 2026). The engine models these as
  effective-dated **data**, not code; transmission is isolated in adapters.
- **Liability:** keep OCA out of the transmitter role; deployers own their TCC
  and filings.
- **State filing & CF/SF:** many states require separate filing (or participate
  in the Combined Federal/State Filing program). 3rd-party filers handle this;
  a direct-A2A path would need separate state work. Adapters make this a
  per-filer concern, not an engine concern.

## 7. Recommended community plan

- **Now:** contribute `l10n_us_account_1099` (engine + IRIS-Portal CSV) to
  OCA/l10n-usa on 18.0; retire/supersede the stranded 17.0 `l10n_us_form_1099`.
- **Next:** one filer-API adapter (Tax1099 **or** Avalara/Track1099) as the
  recommended e-file path; add backup-withholding + Form 945.
- **Later / optional:** a documented `_iris_a2a` adapter for high-volume
  self-filers, with a deployer runbook for TCC + ATS.
- **Governance:** raise this as a GitHub Discussion/issue on `OCA/l10n-usa`
  (and the OCA localization team) so the engine becomes the community standard
  and adapters are co-maintained.

## 8. Open questions for the community

- Which filer API to reference first (Tax1099 vs Avalara/Track1099)?
- Is there appetite to maintain a direct A2A adapter (annual ATS burden), or is
  "CSV + filer API" sufficient for OCA's user base?
- State filing / CF/SF: in-scope for OCA modules or left to filers?
- Versioning: 18.0 baseline + backport policy for older supported branches.

## 9. References

- [E-file information returns with IRIS](https://www.irs.gov/filing/e-file-information-returns-with-iris)
- [IRIS Application for TCC](https://www.irs.gov/tax-professionals/iris-application-for-tcc)
- [IRS Publication 5718 — IRIS A2A specifications](https://www.irs.gov/pub/irs-pdf/p5718.pdf)
- [Topic 801 — who must e-file information returns (10-return mandate, TD 9972)](https://www.irs.gov/taxtopics/tc801)
- FIRE → IRIS retirement (TY2026 cutover): IRS / Thomson Reuters / Sovos guidance
- 3rd-party filer APIs: [Tax1099 API](https://www.tax1099.com/tax1099-api-integration) · [Avalara/Track1099 API](https://www.avalara.com/us/en/products/1099/how-to-integrate-with-apis.html) · [Sovos](https://sovos.com/solutions/tax-information-reporting/)
- Companion: [`ROADMAP.md` §4.1](./ROADMAP.md) · module `l10n_us_account_1099` (PR on the fork)
