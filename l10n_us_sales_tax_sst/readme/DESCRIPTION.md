This module integrates the free **Streamlined Sales Tax (SST)** Rate &
Boundary databases into the US Sales Tax Engine.

It imports a member state's published Rate and Boundary files, creating
FIPS-coded jurisdictions (state, county, city, special districts) with
their rates, and resolves a US address to its full set of jurisdictions
using the SST mandatory `A` (address) → `4` (ZIP+4) → `Z` (ZIP5)
fallback. The engine then books one tax line per jurisdiction, carrying
the FIPS codes that US sales tax returns (including the SST Simplified
Electronic Return) are reported by.

Which tier a calculation resolved at is recorded on the stored provider
response, so a ZIP5 answer can be told from an address-level one.

Where no SST data covers an address (e.g. a non-member state), the
engine falls back to its existing ZIP-mapping / API provider chain.

> [!NOTE]
> A state's ZIP5 records cannot name a county for a ZIP that spans two of
> them, and carry the state's "county undetermined" district instead. Those
> boundary records are flagged `county_undetermined`, and the flag is passed
> through on the provider response, because the local tax they carry cannot
> be reported as a county. Supplying a ZIP+4 resolves such an address on a
> record that does name the county.
