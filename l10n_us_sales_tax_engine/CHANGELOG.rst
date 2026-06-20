Changelog
=========

18.0.1.5.0 (2026-06-18)
------------------------
* Origin/destination sourcing: an intrastate sale in an origin-based state
  (``ORIGIN_BASED_STATES``) is now rated from the seller's ship-from ZIP rather
  than the customer's; interstate and destination-based states are unchanged.
* Add an overridable ``_get_marketplace_collection`` hook (no-op in core, checked
  before nexus) so ``l10n_us_sales_tax_marketplace`` can mark a document as
  collected by a marketplace facilitator (source ``marketplace``; we don't collect).
* Fix: the no-nexus path now clears pre-existing/default taxes on the document
  (it previously returned without applying), so a sale into a state with no nexus
  is correctly untaxed even if the line carried a default tax.
* Add demo data (engine on, WY nexus, Cheyenne rate, taxable + exempt products,
  WY/CA customers and draft sale orders) for review.

18.0.1.4.0 (2026-06-18)
------------------------
* Add an overridable ``_get_customer_exemption`` hook to the calc flow (a no-op in
  the engine; ``l10n_us_sales_tax_exemption`` implements it) that short-circuits a
  document to ``exempt_customer`` with a reason; record the reason on the
  calculation log. Add an SST Taxability-Matrix import wizard (CSV → ``us.tax.rule``,
  closing superseded rules), and "Scheduled Changes" views listing future-effective
  rates/rules (which already activate on their effective date via calc-time filtering).

18.0.1.3.0 (2026-06-17)
------------------------
* Provider registry: ``_get_provider_service`` now consults an overridable
  ``_provider_service_classes()`` map, so an addon adds or swaps a provider by
  extending that method — no edit to the engine. Enrich the ZipTax / TaxJar /
  API Ninjas providers to resolve **named jurisdictions** (county/city) from
  their responses, so non-SST (big-state) tax books one line per named
  jurisdiction and returns aggregate by name, not just by level.

18.0.1.2.0 (2026-06-17)
------------------------
* Add FIPS identity (``fips_state``/``fips_county``/``fips_place``,
  ``jurisdiction_type``, ``composite_ser_code``) to ``us.tax.jurisdiction`` and
  a reduced food/drug rate to ``us.tax.rate`` — the data US tax returns are
  reported by. Generalise per-jurisdiction booking to accept a
  resolved named-jurisdiction list (one child tax per jurisdiction, tagged with
  ``us_tax_jurisdiction_id``), still falling back to the level scalars for
  providers that only return a state/county/city/district split. Groundwork for
  ``l10n_us_sales_tax_sst``.

18.0.1.1.0 (2026-06-17)
------------------------
* Book US Sales Tax per jurisdiction level instead of one combined-rate tax.
  Each non-zero state/county/city/district rate component is now booked as its
  own ``account.tax`` (tagged with ``us_tax_level`` and ``us_tax_state_id``),
  wrapped in a group tax, so every posted move carries a tax line per
  jurisdiction. This preserves the breakdown the GL needs for return filing
  (consumed by ``l10n_us_sales_tax_report``).

18.0.1.0.2 (2026-05-20)
------------------------
* Removed TaxCloud provider (not yet implemented — planned for Phase 2)

18.0.1.0.1 (2026-05-20)
------------------------
* First release
* Hybrid local DB + API fallback architecture
* Florida DOR seed data (67 counties)
* Providers: ZipTax, API Ninjas, TaxJar
* Sale Order and Invoice integration
* Nexus management per company/state
* Product fiscal categories
* Full immutable audit log
* Cache with configurable TTL
* REST API endpoints


18.0.1.0.0 (2026-05-20)
------------------------
* Initial release
