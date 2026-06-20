This module adds **customer / entity sales-tax exemption certificates**
to the US Sales Tax Engine: resale, agricultural, government,
manufacturing, nonprofit, direct-pay and other exemptions.

A certificate records the customer, the reason, the states it covers, an
effective and (optional) expiry date, the signed document, and a
validity status. When a sale ships to a covered state on a date the
certificate is valid, the engine exempts the whole sale and records the
reason (visible in the calculation log). Each reason maps to an SST SER
`ExemptionDeductionBreakout` category so exempt sales can be reported
under the right heading.

## How exemptions map to the return and providers

Each exemption reason carries two mappings: `ser_breakout` places exempt
sales under the right SST SER `ExemptionDeductionBreakout` heading
(Agriculture / Direct Pay / Government-Exempt-Org / Manufacturing /
Resale / Other), and `entity_use_code` (e.g. G resale, H agriculture, A
government) is the Avatax/SST entity-use code for provider interop. So
the chain is: certificate → reason → `ser_breakout` → SER return line,
and reason → `entity_use_code` → external provider.

The model is provider-agnostic — it adapts the OCA
`account_avatax_exemption` shape without the Avatax coupling. v1 fully
exempts a covered sale; e-sign capture, per-state PDF forms and
product-conditional exemption are out of scope.
