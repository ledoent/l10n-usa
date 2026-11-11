# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

# Mini SST rate file: WY (FIPS 56) state 4% (reduced food/drug 2%),
# Laramie county (021) 1%, one special district (55555) 0.5%.
# 9 positional columns, no header: state,jtype,fips,gen_intra,gen_inter,
# food_intra,food_inter,begin,end.
RATE_CSV = "\n".join(
    [
        "56,45,56,0.04,0.04,0.02,0.02,20200101,29991231",
        "56,00,021,0.01,0.01,0,0,20200101,29991231",
        "56,63,55555,0.005,0.005,0,0,20200101,29991231",
    ]
)

# Minnesota 2026Q3 as published: state 6.875% — finer than the 0.01% a
# 4-decimal Float can hold — plus the 0.5% Chisago County (025) transit tax.
MN_RATE_CSV = "\n".join(
    [
        "27,45,27,0.06875,0.06875,0,0,20200101,99991231",
        "27,00,025,0.005,0.005,0,0,20200101,99991231",
    ]
)


def boundary_row(
    zip5="82001",
    fips_state="56",
    fips_county="021",
    districts=("55555",),
    record_type="Z",
    zip_low=None,
    zip_high=None,
    zip4_low="",
    zip4_high="",
    street_name="",
    addr_low="",
    addr_high="",
    odd_even="",
    city="CHEYENNE",
):
    """Build one boundary row (≥29 fixed cols + N district triplets)."""
    row = [""] * 29
    row[0] = record_type
    row[1] = "20200101"
    row[2] = "29991231"
    row[3] = addr_low
    row[4] = addr_high
    row[5] = odd_even
    row[7] = street_name
    row[14] = city
    row[15] = zip5
    row[17] = zip5 if zip_low is None else zip_low  # zip_low
    row[18] = zip4_low
    row[19] = zip5 if zip_high is None else zip_high  # zip_high
    row[20] = zip4_high
    row[22] = fips_state
    row[23] = fips_state  # state indicator = state FIPS → state tax applies
    row[24] = fips_county
    row[25] = "00000"  # no place
    for district in districts:
        row += ["ST", district, "63"]  # special-district triplet(s)
    return ",".join(row)


BOUNDARY_CSV = boundary_row()

# The MN case a 5-digit-only lookup gets wrong: a published ZIP+4 range that
# spans two ZIPs (55012-0011 .. 55013-9746), which carries the county, plus the
# plain ZIP5 record for 55013, which cannot name one. An address at 55013-0001
# sits inside the range, so it is taxed at 7.375%, not the ZIP5 answer 6.875%.
MN_BOUNDARY_CSV = "\n".join(
    [
        boundary_row(
            zip5="",
            fips_state="27",
            fips_county="025",
            districts=(),
            record_type="4",
            zip_low="55012",
            zip4_low="0011",
            zip_high="55013",
            zip4_high="9746",
            city="LINDSTROM",
        ),
        boundary_row(
            zip5="55013",
            fips_state="27",
            fips_county="",
            districts=(),
            record_type="Z",
            city="LINDSTROM",
        ),
    ]
)
