# US Localization (`l10n-usa`) — Roadmap

**Status:** working draft · **Target Odoo:** 18.0 (primary), 16.0 noted where prod needs it · **Last updated:** 2026-06-18

This is a planning document for expanding the US localization beyond the current
seven modules into a usable US accounting/compliance suite. It covers five
workstreams the business has asked for — **1099**, **US GAAP reporting**,
**bank loan / lender reports**, **tariffs & customs**, and **sales tax** — plus
the shared foundations they depend on.

---

## 1. Guiding principles

1. **Reuse before build.** Where a maintained OCA/core module exists on 18.0, depend on it; don't reinvent. Build only the genuine gaps.
2. **Generic in `l10n-usa`, proprietary in `ken/`.** OCA modules may not depend on Avalara/AvaTax or other proprietary engines. Anything coupled to AvaTax, a specific bank, or Kencove process lives in the private `ken/` addons and *depends on* the generic `l10n-usa` module.
3. **Effective-dated rules.** US thresholds and tariff rates change yearly (and mid-year in 2025–26). Model rates/thresholds as data with effective dates, not constants.
4. **Statement mappings are data, not code.** Report line→account groupings must be configurable (MIS Builder / templates), never hard-coded.
5. **Each module ships tested + documented** (OCA standard: `readme/` fragments, generated `README.rst`, ≥ meaningful unit coverage). See the `l10n_us_sales_tax_docuseal` PR as the quality bar.

---

## 2. What already exists (reuse — do **not** rebuild)

| Need | Reuse | Repo (18.0) | Notes |
|---|---|---|---|
| US Chart of Accounts | `l10n_us` | **Odoo core** | Base CoA + taxes; not in OCA |
| Financial statements engine | `mis_builder`, `mis_builder_budget` | OCA/mis-builder | KPI matrix; flagship, very mature |
| US P&L / Balance Sheet templates | `l10n_us_mis_financial_report` | OCA/l10n-usa | Already in our repo |
| GL / TB / aging / open items | `account_financial_report` | OCA/account-financial-reporting | GL, Trial Balance, Aged Partner Balance, Journal Ledger |
| Loan tracking & amortization | `account_loan` | OCA/account-financial-tools | Amortization, P/I split, current↔long-term reclass, balloon, 4 methods |
| Sales tax calc + exemptions (Avalara) | `account_avatax_oca`, `account_avatax_sale_oca`, `account_avatax_exemption[_base]` | OCA/account-fiscal-rule | Proprietary engine; the supported OCA path for accurate US rates |
| HS/HTS code on products | `product_harmonized_system` (+ `_data`) | OCA/intrastat-extrastat | Field + data import only; **no duty-rate lookup** |
| Landed cost allocation | `stock_landed_costs` | **Odoo core** | Foundation for duty/MPF/HMF allocation |
| ACH / routing / legal number | `account_banking_ach_*`, `l10n_us_account_routing`, `l10n_us_partner_legal_number` | OCA/l10n-usa | Already in our repo |

**Migrate-forward candidates (exist ≤17.0, not on 18.0):**
- `l10n_us_form_1099` — last seen on **17.0**, not migrated to 18.0. Port-forward rather than reinvent (but it predates the 1099-NEC split — needs box rework; see §4.1).
- `l10n_us_gaap` / GAAP CoA+MIS — stuck at **12.0**; superseded by `l10n_us_mis_financial_report`. Treat as a fresh template effort, not a migration.

**In-flight in our fork (not yet merged to OCA):**
- `l10n_us_sales_tax_report` (+ dep `l10n_us_sales_tax_engine`) on branch `18.0-add-l10n_us_sales_tax_report` — jurisdiction sales-tax returns. *Not* on OCA 18.0 yet; verify scope before depending on it.
- `l10n_us_sales_tax_docuseal` on branch `18.0-add-l10n_us_sales_tax_docuseal` (PR #2) — DocuSeal-backed exemption certificates.

---

## 3. Gap summary (build / extend)

| Gap | Module(s) to build | Home | Effort |
|---|---|---|---|
| 1099 on 18.0 + NEC + IRIS e-file + card/TPN exclusion | `l10n_us_account_1099*` (migrate+extend) | l10n-usa | L |
| US GAAP cash-flow + equity statements | `l10n_us_mis_cash_flow`, `_equity` (MIS templates) | l10n-usa | M |
| Borrowing base certificate | `account_borrowing_base` | l10n-usa (or account-financial-tools) | L |
| Covenant compliance certificate | `account_loan_covenant` | l10n-usa | M |
| Debt maturity / amortization report | `account_loan_report` | extend `account_loan` | S |
| HTS duty-stack + landed-cost automation | `l10n_us_customs_duty` | l10n-usa | L |
| Duty-by-HTS/origin reporting + drawback | `l10n_us_customs_report` | l10n-usa | M |
| Non-Avalara US rate lookup (optional) | `l10n_us_sales_tax_engine` (review in-flight) | l10n-usa | L |

---

## 4. Workstreams

### 4.1 — 1099 Information Returns  *(priority: HIGH)*

**Why:** every US company with contractors files these; the OCA module is stranded on 17.0 and predates the 1099-NEC split and the 2025–26 rule changes.

**Reuse / migrate:** port `l10n_us_form_1099` (17.0 → 18.0) as the base; extend heavily.

**Build / extend:**
- **Form & box model** covering **1099-NEC** (Box 1, Box 4 backup withholding) and **1099-MISC** (Rents, Royalties, Other, Medical, Gross proceeds to attorney), with room for INT/DIV/K/S. Box mapping at the **expense/payment line**, not just the vendor (one vendor can split boxes).
- **Payment aggregation by box per payee per calendar year**, cash-basis (payment date).
- **Card/third-party-network exclusion (critical):** payments by credit/debit card or TPN (PayPal/Stripe) must be **excluded** from NEC/MISC totals — the processor reports them on 1099-K. Tag payment method; net these out automatically.
- **Payee data:** TIN/EIN/SSN, W-9 on file (status/date), TIN-match status, **24% backup withholding** accrual + **Form 945** reconciliation.
- **Effective-dated thresholds:** $600 (≤2025) → **$2,000 (2026+, inflation-indexed)** for NEC/MISC; **1099-K reverted to $20,000 AND 200 txns**. Per-payment-year logic; support per-state thresholds (many states stay at $600).
- **E-file:** target **IRIS** (FIRE retires after TY2026); generate recipient copies (PDF/e-delivery); 1096 for paper; **10-return aggregate e-file mandate**; corrections workflow.
- **Deadlines** surfaced in UI: NEC Jan 31 (recipient + IRS); others Jan 31 recipient / Feb 28 paper / Mar 31 e-file.

**Proposed split:** `l10n_us_account_1099` (data model + tagging + report) → `l10n_us_account_1099_iris` (e-file) → `l10n_us_account_1099_withholding` (backup withholding/945). Keep generic; no AvaTax dependency.

---

### 4.2 — US GAAP Financial Reporting  *(priority: HIGH, mostly templates)*

**Why:** the core statements + monthly close package; mostly configuration on MIS Builder + `account_financial_report`, not new engines.

**Reuse:** `mis_builder`, `l10n_us_mis_financial_report` (P&L/BS), `account_financial_report` (GL, TB, agings), `account_asset`/depreciation for FA schedules.

**Build (MIS templates + small glue):**
- **Statement of Cash Flows (indirect method)** — period-over-period balance deltas + net income + non-cash add-backs; classify accounts operating/investing/financing. The dominant method (~99% of filers). Ship as a configurable MIS template (`l10n_us_mis_cash_flow`).
- **Statement of Stockholders' Equity** — roll-forward of each equity component (`l10n_us_mis_equity`).
- **Comparative presentation** (current vs prior period/year) baked into templates.
- **Monthly close package** preset bundling BS, IS, Cash Flow, AR/AP aging, FA/depreciation schedule, trial balance into one report set / printable pack.
- **CoA roll-up tags** (current vs non-current; operating/investing/financing) to drive cash-flow classification — may need a small data module if `l10n_us` lacks them.

**Out of scope (note explicitly):** note disclosures and audit-grade footnotes are document-prep, not ERP-generated; leave to the accountants.

---

### 4.3 — Bank Loan / Lender Reports  *(priority: MEDIUM-HIGH)*

**Why:** any company with bank debt owes the lender a monthly/quarterly package; ERP already tracks loans via `account_loan` but produces none of the certificates.

**Reuse:** `account_loan` (principal, rate, amortization method, P/I split, current/long-term reclass, balloon). Confirmed model: `account.loan` + `account.loan.line` with reclassification fields.

**Build:**
- **`account_loan_report`** *(S)* — per-loan amortization schedule export + aggregated **debt maturity schedule** (due by Year 1/2/3/4/5/thereafter) for footnotes and lender packages. Extends `account_loan`.
- **`account_loan_covenant`** *(M)* — covenant definitions with **GL-mapped numerator/denominator** (not hard-coded), threshold + operator, pass/fail + headroom. Ship standard ratios: **DSCR**, **FCCR**, **Leverage (Debt/EBITDA)**, **Current Ratio**, **Debt-to-Equity**, **Interest Coverage**. EBITDA build-up with configurable add-backs. Quarterly compliance certificate output.
- **`account_borrowing_base`** *(L)* — borrowing base certificate: `BB = (Eligible AR × AR advance) + (Eligible Inventory × Inv advance) − Reserves`. AR eligibility engine (past-due >90, cross-aging, concentration caps, intercompany/foreign/government/contra exclusions) off AR aging; inventory eligibility by category/status; configurable advance rates + reserves; as-of-date certificate.

**Note:** these consume GL + `account_loan` + AR aging; keep generic (no specific-bank coupling — bank-specific certificate formats go in `ken/`).

---

### 4.4 — Tariffs & Customs / Import Duties  *(priority: MEDIUM — high business relevance in 2025–26)*

**Why:** the 2025–26 tariff stack (base MFN + Section 301 + Section 232 + IEEPA/reciprocal + AD/CVD) materially changes landed cost; standard Odoo only allocates a manually-entered duty.

**Reuse:** `stock_landed_costs` (allocation), `product_harmonized_system` (HTS field + data).

**Build:**
- **`l10n_us_customs_duty`** *(L)* — model duty as a **stack of components** (base, Sec 301, Sec 232, AD, CVD, MPF, HMF), each **effective-dated** and keyed off **HTS code × country of origin**. Auto-generate the landed-cost lines on receipt. MPF (0.3464%, FY2026 min $33.58 / max $651.50), HMF (0.125%, ocean only). Store customs value, entry number, broker, bond.
- **`l10n_us_customs_report`** *(M)* — duty paid **by HTS code** and **by country of origin** (pivot-able move-line analytics); **duty drawback** tracking (up to 99%, MPF/HMF eligible).
- **Data:** HTS→rate is volatile and not freely bulk-available; design for manual/CSV rate maintenance per HTS line with effective dates (optionally a paid feed later). Do **not** assume an OCA duty-rate dataset exists.

**Reality check:** the only turnkey option today is a commercial app (`import_fees`). This is a real build; scope an MVP (single ad-valorem + 301/232 stack + MPF/HMF) before AD/CVD and drawback.

---

### 4.5 — Sales Tax  *(priority: MEDIUM — partly in flight)*

**Why:** US sales tax = nexus + rooftop rates + exemption certs + filing. Accurate rates realistically mean Avalara; the OCA-generic pieces are exemptions, returns, and certificate collection.

**Reuse:** `account_avatax_oca` + `account_avatax_exemption[_base]` (proprietary, in `ken/` territory).

**In-flight / build (generic, in `l10n-usa`):**
- **`l10n_us_sales_tax_docuseal`** (PR #2) — DocuSeal-backed exemption-certificate collection + validity tracking. *Done, in review.*
- **`l10n_us_sales_tax_report`** (+ `l10n_us_sales_tax_engine`) — review the in-flight fork branch; jurisdiction-level (state/county/city/special-district) returns from collected tax. Decide: adopt, or supersede.
- **Optional `l10n_us_sales_tax_engine`** — non-Avalara rooftop rate lookup. Large effort; only if avoiding Avalara is a goal. Otherwise document "use AvaTax."
- **Nexus tracking** *(M)* — economic-nexus thresholds per state (sales $ / transaction count, effective-dated) with alerts when a state threshold is crossed. Genuine gap; high value.

---

## 5. Cross-cutting foundations

- **Effective-dated rate/threshold framework** — shared pattern (model with `date_from`/`date_to`) reused by 1099 thresholds, tariff rates, and nexus thresholds. Build once.
- **W-9 / TIN capture** on partners — reused by 1099 and (potentially) vendor onboarding.
- **CoA classification tags** (current/non-current, operating/investing/financing) — reused by GAAP cash flow and covenant ratios.
- **Statement-mapping layer** — MIS templates reused across GAAP package and covenant EBITDA build-up.

---

## 6. Phasing

**P0 — start here (highest value / clearest scope):**
1. `l10n_us_account_1099` — migrate 17.0 → 18.0, add NEC + box-at-line + card/TPN exclusion + effective-dated thresholds. *(HIGH demand, well-defined.)*
2. `account_loan_report` — debt maturity / amortization schedule (small, immediate lender value).
3. GAAP **cash-flow (indirect)** + **equity** MIS templates + monthly-close pack.

**P1:**
4. `account_loan_covenant` (DSCR/FCCR/leverage/current/D-E/ICR).
5. `l10n_us_account_1099_iris` (IRIS e-file) + backup withholding/945.
6. Sales-tax: finalize exemption (PR #2), evaluate `l10n_us_sales_tax_report`, add nexus tracking.

**P2:**
7. `account_borrowing_base` (ABL certificate).
8. `l10n_us_customs_duty` MVP → `l10n_us_customs_report` + drawback.
9. Optional non-Avalara `l10n_us_sales_tax_engine`.

---

## 7. Open decisions

- **Odoo version:** prod is **16.0**; this roadmap targets **18.0** (OCA-current). Which modules need a 16.0 backport for prod vs. ride the 18/19 upgrade? (1099 is the likeliest "need it on prod now.")
- **AvaTax vs build:** keep Avalara as the rate engine (recommended) or invest in a generic US rate engine?
- **Tariffs build vs buy:** build `l10n_us_customs_duty` vs. license the commercial `import_fees` add-on?
- **Contribution target:** upstream these to OCA/l10n-usa, or keep in the `ledoent` fork + `ken/`?
- **1099 e-file:** integrate IRIS directly, or export to a 3rd-party filer (Tax1099/Track1099)?

---

## 8. References

- OCA: [l10n-usa](https://github.com/OCA/l10n-usa/tree/18.0) · [account-fiscal-rule (AvaTax)](https://github.com/OCA/account-fiscal-rule/tree/18.0) · [account-financial-tools (account_loan)](https://github.com/OCA/account-financial-tools/tree/18.0/account_loan) · [account-financial-reporting](https://github.com/OCA/account-financial-reporting/tree/18.0) · [mis-builder](https://github.com/OCA/mis-builder) · [intrastat-extrastat (HS code)](https://github.com/OCA/intrastat-extrastat)
- IRS: [1099 General Instructions](https://www.irs.gov/pub/irs-pdf/i1099gi.pdf) · [1099-MISC/NEC instructions](https://www.irs.gov/instructions/i1099mec) · [Backup withholding](https://www.irs.gov/businesses/small-businesses-self-employed/backup-withholding) · OBBBA threshold changes (NEC/MISC $2,000 from 2026; 1099-K reverted to $20k/200) · FIRE→IRIS transition (TY2026)
- US GAAP: ASC 205/210/220/225/230/235; cash flow indirect method (EY/PwC/SEC guidance)
- Lending: borrowing base & advance rates; covenant ratios (DSCR/FCCR/leverage/current/D-E/ICR)
- Customs: HTS (USITC/CBP); Section 301 / 232 / AD-CVD; MPF (FY2026 $33.58–$651.50) / HMF; duty drawback; `stock_landed_costs`
