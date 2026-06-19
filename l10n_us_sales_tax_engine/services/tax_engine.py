# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging
from datetime import date as date_type

from odoo import api, models

from ..levels import LABEL_BY_LEVEL, RATE_COMPONENTS
from ..tools import ORIGIN_BASED_STATES
from .address_resolver import is_us_address, normalize_zip, resolve_shipping_address
from .cache_manager import CacheManager
from .provider_base import ProviderError

_logger = logging.getLogger(__name__)


class UsTaxEngineService(models.AbstractModel):
    """Main US Tax Engine orchestrator.

    Implements the full calculation flow:
    1. Resolve address
    2. Check nexus
    3. Check product category taxability
    4. Try cache
    5. Try local database
    6. Try external API fallback chain
    7. Apply result to Odoo document
    8. Write audit log
    """

    _name = "us.tax.engine.service"
    _description = "US Tax Engine Service"

    # ── Public entry points ───────────────────────────────────────────────────

    @api.model
    def calculate_for_sale_order(self, order):
        """Calculate and apply US Sales Tax for a sale.order record."""
        doc_date = order.date_order.date() if order.date_order else date_type.today()
        address = resolve_shipping_address(order)
        return self._process(
            res_model="sale.order",
            res_id=order.id,
            address=address,
            lines=order.order_line,
            doc_date=doc_date,
            company_id=order.company_id.id,
            currency_id=order.currency_id.id,
            partner_id=order.partner_id.commercial_partner_id.id,
            apply_fn=lambda result: self._apply_to_sale_order(order, result),
        )

    @api.model
    def calculate_for_invoice(self, move):
        """Calculate and apply US Sales Tax for an account.move record."""
        doc_date = move.invoice_date or date_type.today()
        address = resolve_shipping_address(move)
        return self._process(
            res_model="account.move",
            res_id=move.id,
            address=address,
            lines=move.invoice_line_ids,
            doc_date=doc_date,
            company_id=move.company_id.id,
            currency_id=move.currency_id.id,
            partner_id=move.partner_id.commercial_partner_id.id,
            apply_fn=lambda result: self._apply_to_invoice(move, result),
        )

    @api.model
    def _get_customer_exemption(self, partner_id, state, doc_date, company_id=False):
        """Hook: return an exemption reason code if the customer is exempt.

        No-op in the engine (returns a falsy value). The
        ``l10n_us_sales_tax_exemption`` addon overrides this to look up a valid
        exemption certificate for ``partner_id`` (in ``company_id``) covering
        ``state`` on ``doc_date`` and return its reason code.
        """
        return False

    @api.model
    def _is_interstate(self, company_id, state_code):
        """True when the seller is remote (out-of-state or non-US) relative to
        ``state_code`` - i.e. an interstate sale into that state."""
        partner = self.env["res.company"].browse(company_id).partner_id
        return partner.country_id.code != "US" or partner.state_id.code != state_code

    @api.model
    def _sourcing_zip(self, company_id, zip_code, state_code):
        """ZIP to rate from: the seller's ship-from for an intrastate sale in an
        origin-based state, else the customer's ship-to ZIP.

        Interstate sales, destination-based states, and a non-US/blank seller
        address all keep the destination ZIP. A misconfigured origin-based seller
        (no ship-from ZIP) logs a warning and falls back to destination.
        """
        if state_code not in ORIGIN_BASED_STATES:
            return zip_code
        if self._is_interstate(company_id, state_code):
            return zip_code  # interstate (or non-US seller) → destination
        partner = self.env["res.company"].browse(company_id).partner_id
        origin_zip = normalize_zip(partner.zip or "")
        if not origin_zip:
            _logger.warning(
                "US Tax: %s is origin-based but the seller has no ship-from ZIP; "
                "rating at the destination ZIP.",
                state_code,
            )
            return zip_code
        return origin_zip

    @api.model
    def _single_local_for(self, company_id, state, state_code):
        """Elected single local use rate for a remote (interstate) sale into
        ``state``, else None."""
        if not (state and self._is_interstate(company_id, state_code)):
            return None
        return self.env["us.tax.nexus"].get_single_local_rate(company_id, state.id)

    @api.model
    def _apply_single_local_rate(self, rate_result, single_local, state_code):
        """Collapse the resolved local rate into the elected single local use
        rate, keeping the state-level rate (and its jurisdiction tag)."""
        state_rate = rate_result.get("state_rate", 0.0)
        state_jur = next(
            (
                j
                for j in (rate_result.get("jurisdictions") or [])
                if j.get("level") == "state"
            ),
            {},
        )
        return {
            "state_rate": state_rate,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": single_local,
            "total_rate": round(state_rate + single_local, 6),
            "source": "single_local",
            "jurisdictions": [
                {
                    "jurisdiction_id": state_jur.get("jurisdiction_id", False),
                    "fips": state_jur.get("fips", ""),
                    "level": "state",
                    "rate": state_rate,
                    "label": state_jur.get("label") or state_code,
                },
                {
                    "jurisdiction_id": False,
                    "fips": "",
                    "level": "district",
                    "rate": single_local,
                    "label": f"{state_code} Single Local Use Rate",
                },
            ],
        }

    @api.model
    def _learn_address_jurisdiction(self, zip_code, state_code, address, rates, source):
        """Persist the rooftop jurisdiction an external provider resolved for an
        address, so subsequent lookups resolve locally (see
        ``us.tax.zip.mapping.learn_jurisdiction``)."""
        candidates = [
            j for j in (rates.get("jurisdictions") or []) if j.get("jurisdiction_id")
        ]
        if not candidates:
            return
        # Most specific place wins: city > county > district > state.
        priority = {"city": 0, "county": 1, "district": 2, "state": 3}
        best = min(candidates, key=lambda j: priority.get(j.get("level"), 9))
        jurisdiction = self.env["us.tax.jurisdiction"].browse(best["jurisdiction_id"])
        if not jurisdiction.exists():
            return
        self.env["us.tax.zip.mapping"].learn_jurisdiction(
            {
                "zip": zip_code,
                "state": state_code,
                "city": address.get("city", ""),
                "address": address.get("address", ""),
            },
            jurisdiction,
            source=source,
        )

    @api.model
    def _get_marketplace_collection(self, res_model, res_id):
        """Hook: return a truthy marketplace marker if a facilitator collects.

        No-op in the engine. ``l10n_us_sales_tax_marketplace`` overrides this to
        return the marketplace when the document is flagged as collected and
        remitted by a marketplace facilitator (so the seller must not collect).
        """
        return False

    # ── Core calculation flow ─────────────────────────────────────────────────

    @api.model
    def _process(
        self,
        res_model,
        res_id,
        address,
        lines,
        doc_date,
        company_id,
        currency_id,
        apply_fn,
        partner_id=False,
    ):
        """Orchestrate the full calculation flow."""
        ICP = self.env["ir.config_parameter"].sudo()

        if ICP.get_param("l10n_us_tax.engine_active", "False") != "True":
            return {"source": "disabled"}

        # Step 0: Marketplace-facilitator collection. If a marketplace collects
        # and remits for this document, we must NOT collect — regardless of nexus,
        # exemption, or even a resolvable ship-to address. No-op hook in core
        # (l10n_us_sales_tax_marketplace implements it).
        marketplace = self._get_marketplace_collection(res_model, res_id)
        if marketplace:
            result = {
                "source": "marketplace",
                "tax_amount": 0.0,
                "marketplace": marketplace,
            }
            try:
                apply_fn(result)
            except Exception as exc:
                _logger.error("Tax apply error on %s %s: %s", res_model, res_id, exc)
            self._log(
                res_model,
                res_id,
                address or {},
                "marketplace",
                taxable_amount=0,
                tax_amount=0,
                partner_id=partner_id,
            )
            return result

        # Step 1: Validate address is US
        if not address or not is_us_address(address):
            return {"source": "skip_non_us"}

        zip_code = address.get("zip", "")
        state_code = address.get("state", "")
        if not zip_code or not state_code:
            _logger.warning(
                "Tax engine: missing ZIP or state for %s %s", res_model, res_id
            )
            return {"source": "skip_no_address"}

        # Step 2: Resolve state record
        state = self.env["res.country.state"].search(
            [("code", "=", state_code), ("country_id.code", "=", "US")], limit=1
        )

        # Step 3: Check nexus
        has_nexus = self.env["us.tax.nexus"].has_nexus(
            company_id, state.id if state else False
        )
        if not has_nexus:
            result = {"source": "exempt_nexus", "tax_amount": 0.0}
            # Clear any pre-existing/default taxes — with the engine active and no
            # nexus in the ship-to state, no US sales tax is due.
            try:
                apply_fn(result)
            except Exception as exc:
                _logger.error("Tax apply error on %s %s: %s", res_model, res_id, exc)
            self._log(
                res_model,
                res_id,
                address,
                "exempt_nexus",
                taxable_amount=0,
                tax_amount=0,
                state_id=state.id if state else False,
                nexus_applied=False,
                partner_id=partner_id,
            )
            return result

        # Step 3b: Customer/entity exemption (resale, agriculture, government, …).
        # The hook is a no-op in the engine; l10n_us_sales_tax_exemption overrides
        # it to look up a valid certificate for this customer + state + date.
        exemption_reason = self._get_customer_exemption(
            partner_id, state, doc_date, company_id
        )
        if exemption_reason:
            result = {
                "source": "exempt_customer",
                "tax_amount": 0.0,
                "exemption_reason": exemption_reason,
            }
            try:
                apply_fn(result)
            except Exception as exc:
                _logger.error("Tax apply error on %s %s: %s", res_model, res_id, exc)
            self._log(
                res_model,
                res_id,
                address,
                "exempt_customer",
                taxable_amount=0,
                tax_amount=0,
                state_id=state.id if state else False,
                nexus_applied=True,
                partner_id=partner_id,
                exemption_reason=exemption_reason,
            )
            return result

        # Step 4: Initialize cache manager
        ttl = int(ICP.get_param("l10n_us_tax.cache_ttl_hours", "720"))
        cache = CacheManager(self.env, ttl_hours=ttl)

        # Step 4b: Sourcing — origin-based states rate an INTRASTATE sale from the
        # seller's ship-from; everything else keeps the ship-to ZIP. Only the rate
        # lookup ZIP changes; nexus/exemption stay on the destination.
        rate_zip = self._sourcing_zip(company_id, zip_code, state_code)

        # Step 4c: Texas-style single local use rate — a remote (interstate)
        # seller that has elected the state's single local rate collects a flat
        # state + single-local rate instead of the actual local rate at each
        # destination. Resolved once per document.
        single_local = self._single_local_for(company_id, state, state_code)

        # Step 5: Calculate per document line
        engine_mode = ICP.get_param("l10n_us_tax.engine_mode", "hybrid")
        fail_policy = ICP.get_param("l10n_us_tax.fail_policy", "warn")
        total_tax = 0.0
        results = []

        # Pre-load TANGIBLE category for fallback (no category = taxable goods)
        tangible_cat = self.env["us.tax.product.category"].search(
            [("code", "=", "TANGIBLE")], limit=1
        )

        for line in lines:
            if not hasattr(line, "price_subtotal") or line.price_subtotal == 0:
                continue
            product = getattr(line, "product_id", None)

            # Resolve product fiscal category — default to TANGIBLE if not set
            if product and product.us_tax_category_id:
                cat_code = product.us_tax_category_id.code
                cat_id = product.us_tax_category_id.id
            else:
                # No category set → assume TANGIBLE (standard physical goods)
                cat_code = "TANGIBLE"
                cat_id = tangible_cat.id if tangible_cat else False
                _logger.debug(
                    'Product "%s" has no US Tax Category — defaulting to TANGIBLE',
                    product.name if product else "unknown",
                )

            # Check taxability rule
            taxable, rate_override = self.env["us.tax.rule"].is_taxable(
                state.id if state else False, cat_id, date=doc_date
            )
            if not taxable:
                results.append(
                    {"line_id": line.id, "source": "exempt_rule", "tax": 0.0}
                )
                continue

            # Calculate rate for this line
            rate_result = self._get_rate(
                zip_code=rate_zip,
                state_code=state_code,
                state_id=state.id if state else False,
                product_category_code=cat_code,
                product_category_id=cat_id,
                doc_date=doc_date,
                address=address,
                cache=cache,
                engine_mode=engine_mode,
                fail_policy=fail_policy,
                rate_override=rate_override,
            )
            if single_local is not None and rate_result.get("total_rate"):
                rate_result = self._apply_single_local_rate(
                    rate_result, single_local, state_code
                )
            line_tax = round(line.price_subtotal * rate_result["total_rate"], 4)
            total_tax += line_tax
            results.append(
                {
                    "line_id": line.id,
                    "source": rate_result["source"],
                    "rate": rate_result["total_rate"],
                    "tax": line_tax,
                    "subtotal": line.price_subtotal,
                    "rate_detail": rate_result,
                }
            )

        # Step 6: Apply to document
        final_result = {
            "source": results[0]["source"] if results else "no_lines",
            "tax_amount": total_tax,
            "lines": results,
        }
        try:
            apply_fn(final_result)
        except Exception as exc:
            _logger.error("Tax apply error on %s %s: %s", res_model, res_id, exc)

        # Step 7: Audit log — include state, nexus, rate detail and provider
        best_rate = next(
            (r["rate_detail"] for r in results if r.get("rate_detail")), {}
        )
        # Extract provider_id from best rate result (set in _get_rate)
        used_provider_id = best_rate.get("provider_id", False)

        self._log(
            res_model,
            res_id,
            address,
            source=final_result["source"],
            taxable_amount=sum(r.get("subtotal", 0) for r in results),
            tax_amount=total_tax,
            state_id=state.id if state else False,
            nexus_applied=has_nexus,
            total_rate=best_rate.get("total_rate", 0),
            state_rate=best_rate.get("state_rate", 0),
            county_rate=best_rate.get("county_rate", 0),
            provider_id=used_provider_id,
        )
        return final_result

    @api.model
    def _get_rate(
        self,
        zip_code,
        state_code,
        state_id,
        product_category_code,
        product_category_id,
        doc_date,
        address,
        cache,
        engine_mode,
        fail_policy,
        rate_override=None,
    ):
        """Return rate dict from best available source."""

        if rate_override is not None:
            return {
                "total_rate": rate_override,
                "state_rate": rate_override,
                "county_rate": 0,
                "city_rate": 0,
                "district_rate": 0,
                "source": "manual",
            }

        payload = {
            "zip": zip_code,
            "state": state_code,
            "city": address.get("city", ""),
            "address": address.get("address", ""),
            "date": str(doc_date),
            "product_category": product_category_code,
        }

        # Cache check
        cache_hash = cache.build_hash(
            zip_code, state_code, product_category_code, doc_date
        )
        cached = cache.get(cache_hash)
        if cached:
            cached["source"] = "cache"
            return cached

        # Get ordered providers
        providers = self._get_active_providers(engine_mode)
        last_error = None

        skipped_providers = []

        for provider_rec in providers:
            # ── Pre-call limit check ─────────────────────────────────────────
            if provider_rec.code != "local" and provider_rec.is_limit_reached():
                _logger.info(
                    'US Tax: skipping provider "%s" — monthly limit reached '
                    "(%d/%d). Moving to next provider.",
                    provider_rec.name,
                    provider_rec.calls_this_month,
                    provider_rec.monthly_call_limit,
                )
                skipped_providers.append(provider_rec.name)
                last_error = ProviderError(
                    f"{provider_rec.name}: monthly limit reached "
                    f"({provider_rec.calls_this_month}/{provider_rec.monthly_call_limit})"
                )
                continue

            try:
                svc = provider_rec._get_provider_service()(provider_rec)
                rates = svc.get_rate(payload)
                rates["source"] = "api" if provider_rec.code != "local" else "local"
                rates["provider_id"] = (
                    provider_rec.id if provider_rec.code != "local" else False
                )
                # Save to cache only for external providers
                if provider_rec.code != "local":
                    cache.set(
                        cache_hash,
                        provider_rec.id,
                        rates,
                        zip_code=zip_code,
                        state_id=state_id,
                        request_payload=payload,
                        response_payload=rates.get("raw_response", {}),
                    )
                    # Learn the rooftop jurisdiction this authoritative provider
                    # resolved, so future lookups for the same address resolve
                    # locally and the provider is not called again.
                    self._learn_address_jurisdiction(
                        zip_code, state_code, address, rates, provider_rec.code
                    )
                return rates

            except ProviderError as exc:
                last_error = exc
                _logger.warning('Provider "%s" failed: %s', provider_rec.code, exc)
                continue

        # All providers exhausted — log which ones were skipped due to limits
        if skipped_providers:
            _logger.warning(
                "US Tax: providers skipped due to limits: %s",
                ", ".join(skipped_providers),
            )

        # Apply fail policy
        return self._handle_all_failed(fail_policy, cache_hash, last_error, address)

    @api.model
    def _get_active_providers(self, engine_mode):
        """Return ordered list of active provider records based on mode."""
        domain = [("active", "=", True)]
        if engine_mode == "local":
            domain.append(("code", "=", "local"))
        elif engine_mode == "api":
            domain.append(("code", "!=", "local"))
        # hybrid: all active, ordered by priority
        return self.env["us.tax.provider"].search(domain, order="priority, id")

    @api.model
    def _handle_all_failed(self, fail_policy, cache_hash, last_error, address):
        """Apply fail policy when all providers fail."""
        if fail_policy == "block":
            raise ProviderError(
                f"US Tax: all providers failed for ZIP={address.get('zip')}. "
                f"Last error: {last_error}"
            )
        if fail_policy == "last_cache":
            # Try expired cache
            entry = self.env["us.tax.api.cache"].search(
                [("address_hash", "=", cache_hash)], order="cached_at desc", limit=1
            )
            if entry:
                _logger.warning("Using expired cache for %s", cache_hash[:12])
                return {
                    "total_rate": entry.total_rate,
                    "state_rate": entry.state_rate,
                    "county_rate": entry.county_rate,
                    "city_rate": entry.city_rate,
                    "district_rate": entry.district_rate,
                    "source": "cache_expired",
                }
        # warn or manual → return 0 tax
        _logger.warning(
            "US Tax: all providers failed, applying 0 tax. Policy=%s", fail_policy
        )
        return {
            "total_rate": 0.0,
            "state_rate": 0.0,
            "county_rate": 0.0,
            "city_rate": 0.0,
            "district_rate": 0.0,
            "source": "error",
        }

    # ── Apply tax to Odoo documents ───────────────────────────────────────────

    # Sources that exempt the entire document → clear taxes on every line.
    _WHOLE_DOC_EXEMPT_SOURCES = (
        "exempt_nexus",
        "exempt_customer",
        "marketplace",
        "disabled",
        "skip_non_us",
        "skip_no_address",
    )

    @api.model
    def _apply_to_sale_order(self, order, result):
        """Apply calculated US tax to sale order lines.

        Always runs — even for $0 tax (exempt) to remove existing taxes.
        """
        order_source = result.get("source", "")
        lines_map = {r["line_id"]: r for r in result.get("lines", [])}
        state_code = (
            order.partner_shipping_id.state_id.code
            if order.partner_shipping_id and order.partner_shipping_id.state_id
            else order.partner_id.state_id.code
        )

        # If the whole order is exempt (no nexus / customer cert), clear all taxes
        if order_source in self._WHOLE_DOC_EXEMPT_SOURCES:
            order.order_line.write({"tax_id": [(5, 0, 0)]})
            return

        for line in order.order_line:
            line_result = lines_map.get(line.id, {})
            source = line_result.get("source", order_source)
            rate = line_result.get("rate", 0.0)

            if source in ("exempt_rule", "exempt_nexus"):
                line.write({"tax_id": [(5, 0, 0)]})
                continue

            if rate <= 0:
                continue

            tax = self._get_or_create_jurisdiction_tax(
                state_code, order.company_id, line_result.get("rate_detail", {})
            )
            if tax:
                line.write({"tax_id": [(6, 0, [tax.id])]})

    @api.model
    def _apply_to_invoice(self, move, result):
        """Apply calculated US tax to invoice lines — REPLACE existing taxes."""
        # Whole-invoice exemption (no nexus / customer cert) — clear all taxes.
        if result.get("source", "") in self._WHOLE_DOC_EXEMPT_SOURCES:
            move.invoice_line_ids.write({"tax_ids": [(5, 0, 0)]})
            return
        lines_map = {r["line_id"]: r for r in result.get("lines", [])}
        state_code = (
            move.partner_shipping_id.state_id.code
            if (
                hasattr(move, "partner_shipping_id")
                and move.partner_shipping_id
                and move.partner_shipping_id.state_id
            )
            else move.partner_id.state_id.code
        )
        for line in move.invoice_line_ids:
            line_result = lines_map.get(line.id, {})
            rate = line_result.get("rate", 0.0)
            source = line_result.get("source", result.get("source", ""))

            if source in ("exempt_rule", "exempt_nexus"):
                line.write({"tax_ids": [(5, 0, 0)]})
                continue
            if rate <= 0:
                continue

            tax = self._get_or_create_jurisdiction_tax(
                state_code, move.company_id, line_result.get("rate_detail", {})
            )
            if tax:
                line.write({"tax_ids": [(6, 0, [tax.id])]})

    # Per-level scalar components, in a fixed order, from the shared taxonomy.
    _JURISDICTION_LEVELS = RATE_COMPONENTS

    @api.model
    def _get_or_create_jurisdiction_tax(self, state_code, company, rate_detail):
        """Return an account.tax that books US Sales Tax per jurisdiction.

        Instead of one combined-rate tax per state (which erases the breakdown
        the GL needs for return filing), this builds one child tax per non-zero
        jurisdiction component — each tagged with its ``us_tax_level``,
        ``us_tax_state_id`` and (when resolved) ``us_tax_jurisdiction_id`` — and
        wraps them in a group tax so every posted move carries a tax line per
        jurisdiction.

        Two shapes of ``rate_detail`` are accepted (see ``_normalize_components``):
        a per-named-jurisdiction list (SST resolver) or the legacy
        state/county/city/district scalars (API providers). When only one
        component applies, that single child is returned directly (no needless
        group); a provider returning only a total rate yields one ``combined``
        child so the amount is still captured (flagged for manual allocation).
        """
        if not state_code:
            return False

        state = self.env["res.country.state"].search(
            [("code", "=", state_code), ("country_id.code", "=", "US")], limit=1
        )

        components = self._normalize_components(rate_detail)
        if not components:
            return False

        tax_group = self._get_us_tax_group(company)
        children = self.env["account.tax"]
        for comp in components:
            children |= self._get_or_create_component_tax(
                state_code, state, company, comp, tax_group
            )

        if len(children) == 1:
            return children

        total_pct = round(sum(c["pct"] for c in components), 4)
        return self._get_or_create_group_tax(
            state_code, company, total_pct, children, tax_group
        )

    @api.model
    def _normalize_components(self, rate_detail):
        """Flatten a rate result into a list of jurisdiction component dicts.

        Each dict is ``{level, label, pct, jurisdiction_id}``. A
        ``jurisdictions`` key (per-named-jurisdiction, from the SST resolver)
        takes precedence; otherwise the legacy level scalars are used, falling
        back to a single ``combined`` component for total-only providers.
        """
        jurisdictions = rate_detail.get("jurisdictions")
        if jurisdictions:
            comps = []
            for jur in jurisdictions:
                pct = round(float(jur.get("rate", 0.0)) * 100, 4)
                if pct <= 0:
                    continue
                level = jur.get("level", "combined")
                comps.append(
                    {
                        "level": level,
                        "label": jur.get("label") or level.title(),
                        "pct": pct,
                        "jurisdiction_id": jur.get("jurisdiction_id", False),
                    }
                )
            return comps

        comps = [
            {
                "level": level,
                "label": label,
                "pct": round(float(rate_detail.get(key, 0.0)) * 100, 4),
                "jurisdiction_id": False,
            }
            for level, label, key in self._JURISDICTION_LEVELS
        ]
        comps = [c for c in comps if c["pct"] > 0]
        if comps:
            return comps

        total_pct = round(float(rate_detail.get("total_rate", 0.0)) * 100, 4)
        if total_pct > 0:
            return [
                {
                    "level": "combined",
                    "label": LABEL_BY_LEVEL["combined"],
                    "pct": total_pct,
                    "jurisdiction_id": False,
                }
            ]
        return []

    @api.model
    def _get_us_tax_group(self, company):
        """Get/create the company-scoped 'US Sales Tax' account.tax.group.

        account.tax.group is company-bound in 18.0, so the lookup must be scoped
        to avoid a child tax referencing another company's group.
        """
        TaxGroup = self.env["account.tax.group"].sudo()
        domain = [("name", "=", "US Sales Tax"), ("company_id", "=", company.id)]
        tax_group = TaxGroup.search(domain, limit=1)
        if not tax_group:
            tax_group = TaxGroup.create(
                {
                    "name": "US Sales Tax",
                    "sequence": 10,
                    "company_id": company.id,
                }
            )
        return tax_group

    @api.model
    def _us_tax_country_id(self, company):
        """account.tax.country_id is required in 18.0; default to the company's
        fiscal country, then its country, then the US."""
        return (
            company.account_fiscal_country_id.id
            or company.country_id.id
            or self.env.ref("base.us").id
        )

    @api.model
    def _ensure_tax_account(self, tax, company):
        """Point the tax's repartition tax lines at the payable account.

        account.tax auto-creates repartition lines with no account, so the
        collected tax would fall back to the base line's (income) account. Book
        it to the company's sales-tax-payable liability instead (find-or-create),
        which also heals taxes created before this fix.
        """
        lines = (
            tax.invoice_repartition_line_ids | tax.refund_repartition_line_ids
        ).filtered(lambda r: r.repartition_type == "tax" and not r.account_id)
        if lines:
            account = company.get_us_tax_payable_account()
            lines.sudo().write({"account_id": account.id})

    @api.model
    def _get_or_create_component_tax(self, state_code, state, company, comp, tax_group):
        """Get/create the per-jurisdiction child tax for one rate component.

        ``comp`` is ``{level, label, pct, jurisdiction_id}``. A resolved named
        jurisdiction is keyed into both the name and the search domain so two
        distinct jurisdictions sharing a rate (e.g. two special districts) don't
        collide on one tax record.
        """
        Tax = self.env["account.tax"].sudo()
        level = comp["level"]
        label = comp["label"]
        pct = comp["pct"]
        jurisdiction_id = comp.get("jurisdiction_id") or False
        state_id = state.id if state else False
        name = f"US Sales Tax {state_code} {label} {pct:.4g}%"
        domain = [
            ("name", "=", name),
            ("type_tax_use", "=", "sale"),
            ("amount_type", "=", "percent"),
            ("company_id", "=", company.id),
        ]
        if jurisdiction_id:
            domain.append(("us_tax_jurisdiction_id", "=", jurisdiction_id))
        tax = Tax.search(domain, limit=1)
        if not tax:
            tax = Tax.create(
                {
                    "name": name,
                    "type_tax_use": "sale",
                    "amount_type": "percent",
                    "amount": pct,
                    "company_id": company.id,
                    "country_id": self._us_tax_country_id(company),
                    "tax_group_id": tax_group.id,
                    "us_tax_level": level,
                    "us_tax_state_id": state_id,
                    "us_tax_jurisdiction_id": jurisdiction_id,
                    "description": f"US Sales Tax — {state_code} {label} @ {pct:.4g}%",
                }
            )
            _logger.info('Created jurisdiction tax "%s" at %s%%', name, pct)
        elif (
            tax.us_tax_level != level
            or (state and tax.us_tax_state_id.id != state_id)
            or (jurisdiction_id and tax.us_tax_jurisdiction_id.id != jurisdiction_id)
        ):
            # Heal tags on a tax created before this version booked jurisdictions.
            tax.write(
                {
                    "us_tax_level": level,
                    "us_tax_state_id": state_id,
                    "us_tax_jurisdiction_id": jurisdiction_id,
                }
            )
        # Always book collected tax to the payable liability (heals old taxes).
        self._ensure_tax_account(tax, company)
        return tax

    @api.model
    def _get_or_create_group_tax(
        self, state_code, company, total_pct, children, tax_group
    ):
        """Get/create the parent group tax wrapping the jurisdiction children."""
        Tax = self.env["account.tax"].sudo()
        name = f"US Sales Tax {state_code} {total_pct:.4g}%"
        tax = Tax.search(
            [
                ("name", "=", name),
                ("type_tax_use", "=", "sale"),
                ("amount_type", "=", "group"),
                ("company_id", "=", company.id),
            ],
            limit=1,
        )
        if not tax:
            tax = Tax.create(
                {
                    "name": name,
                    "type_tax_use": "sale",
                    "amount_type": "group",
                    "children_tax_ids": [(6, 0, children.ids)],
                    "company_id": company.id,
                    "country_id": self._us_tax_country_id(company),
                    "tax_group_id": tax_group.id,
                    "description": f"US Sales Tax — {state_code} @ {total_pct:.4g}%",
                }
            )
            _logger.info('Created group tax "%s" at %s%%', name, total_pct)
        elif set(tax.children_tax_ids.ids) != set(children.ids):
            tax.write({"children_tax_ids": [(6, 0, children.ids)]})
        return tax

    # ── Audit log ─────────────────────────────────────────────────────────────

    @api.model
    def _log(
        self,
        res_model,
        res_id,
        address,
        source,
        taxable_amount=0,
        tax_amount=0,
        provider_id=None,
        state_id=None,
        nexus_applied=False,
        total_rate=0,
        state_rate=0,
        county_rate=0,
        partner_id=None,
        exemption_reason=None,
    ):
        # Resolve state_id from address if not provided
        if not state_id and address.get("state"):
            state = self.env["res.country.state"].search(
                [("code", "=", address["state"]), ("country_id.code", "=", "US")],
                limit=1,
            )
            state_id = state.id if state else False

        self.env["us.tax.calculation.log"].sudo().log_calculation(
            {
                "res_model": res_model,
                "res_id": res_id,
                "partner_id": partner_id,
                "shipping_zip": address.get("zip", ""),
                "shipping_city": address.get("city", ""),
                "shipping_state_id": state_id or False,
                "full_address": address.get("address", ""),
                "source": source,
                "provider_id": provider_id,
                "nexus_applied": nexus_applied,
                "total_rate": total_rate,
                "state_rate": state_rate,
                "county_rate": county_rate,
                "taxable_amount": taxable_amount,
                "tax_amount": tax_amount,
                "exemption_reason": exemption_reason or "",
                "calculated_by": self.env.user.id,
                "status": "success" if source not in ("error",) else "error",
            }
        )
