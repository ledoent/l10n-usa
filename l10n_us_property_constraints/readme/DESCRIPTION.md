Derives US construction/regulatory **constraints** on a `property.record`
from data already gathered by other sources — **no extra API call, no cost**.

Currently flags the **EPA Renovation, Repair and Painting (RRP) lead rule**:
housing built before 1978 requires a certified renovator and lead-safe work
practices. A home-improvement contractor uses this to qualify a lead and price
in the compliance overhead before quoting.

It extends `property.record._derive_constraints()`, so it composes with the
free FEMA flood and NRHP historic-district connectors and any paid attribute
source (Realie, ATTOM) that supplies the `year_built` it reads.
