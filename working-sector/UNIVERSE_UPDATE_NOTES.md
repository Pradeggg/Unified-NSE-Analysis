# Auto Components Universe – Update Notes

## Source for additional companies

Additional NSE-listed auto ancillary companies were identified from:

1. **Bajaj Broking – Auto Ancillaries sector**  
   https://www.bajajbroking.in/stock/sectors/auto-ancillaries  
   (Full list of companies by sector; company names mapped to NSE symbols.)

2. **NSE data cross-check**  
   Only symbols that appear in project data (`data/nse_sec_full_data.csv`) were included, so the universe is consistent with the pipeline.

3. **Definition**  
   Universe remains **component-only** (no OEMs). Vehicle manufacturers (e.g. Maruti, Tata Motors, M&M, Bajaj Auto, Hero, Eicher, Ashok Leyland, TVS Motor) are not included.

## Changes made

- **Original 10:** Nifty Auto constituents (component-only): BHARATFORG, UNOMINDA, BOSCHLTD, EXIDEIND, TMPV, MOTHERSON, TIINDIA, SONACOMS, APOLLOTYRE, MRF.
- **Added 40:** NSE/Bajaj Auto Ancillaries–sector names with symbols verified in NSE data (e.g. AMARAJABAT, ENDURANCE, SUNDRMFAST, SANSERA, VARROC, ZFCVINDIA, etc.).
- **Total:** 50 stocks.

## SOURCE column

- `Nifty Auto` = Part of NSE Nifty Auto index (ancillary names only).
- `NSE/Bajaj Auto Ancillaries` = From sector list (Bajaj Broking) and verified in NSE data.

## SUBSECTOR

Rough segment tags for analysis: Battery, Tyres, Forgings, Electrical, Gears, Axles, Engine/Parts, Suspension, Brakes, Lighting, Wheels, Seating, Bearings, Fasteners, Cables, Gaskets, Fuel Systems, Transmission, Castings, Other.

## NSE official classification

NSE’s industry classification (nseindia.com/products-services/industry-classification) uses categories such as “Auto Ancillaries - Auto, Truck & Motorcycle Parts” and sub-segments. This list is a practical union of Nifty Auto (component-only) and a broad auto-ancillary sector list; it is not an official NSE industry dump.
