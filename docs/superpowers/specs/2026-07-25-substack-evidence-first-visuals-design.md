# Substack Evidence-First Visuals Design

## Goal

Add four evidence-bearing, publication-ready visuals to the 24 July 2026 India market thesis without introducing stale market data, dashboard clutter, or investment calls.

## Editorial decision

The approved package is **A: evidence-first**. It makes the article’s central claim visually legible: the macro backdrop is resilient, but market participation is selective and financial confirmation is incomplete.

The article remains a long-form Substack post, not an interactive dashboard. Each visual must work in a mobile reading flow, include a visible as-of date, and retain enough direct labeling to be understood without hover or a detached legend.

## Visual inventory

| Order | Asset | Analytical question answered | Source | Placement |
|---:|---|---|---|---|
| 1 | `assets/01-market-pulse.svg` | Why is the market cautious despite economic resilience? | 24 July NSE close; 23 July local FII/DII cache | After “The short thesis” |
| 2 | `assets/02-broad-market-rrg.png` | Which market-cap segments are leading, improving, or weakening? | Current broad-market RRG in `reports/latest/market_breadth_rrg.html` | After “Reading the RRG” |
| 3 | `assets/03-sector-rrg.png` | Which sectors show confirmed versus mature or fading leadership? | Current sector RRG in `reports/latest/market_breadth_rrg.html` | After “Sector leadership” |
| 4 | `assets/04-breadth-participation.svg` | Is the market’s participation broad enough to confirm the index? | Current breadth table in `reports/latest/market_breadth_rrg.html` | After “What market breadth is really saying” |

## Figure specifications

### 1. Market pulse card

A static SVG with four direct-labeled metrics: Nifty 50 -0.43%, India VIX +4.11%, Nifty 500 constituents above 50D 48%, and 5-day FII cash flow -₹9,880.86 crore. A single sentence beneath the metrics reads: “Resilient macro, selective participation.” The card must identify the price cut as 24 July and the flow cut as 23 July.

### 2. Broad-market RRG

Export the current broad-market RRG view from the 24 July artifact rather than reusing the dated 10 July image. Preserve axis labels, quadrant labels, direct point labels, and the Nifty 500 benchmark statement. Do not combine current coordinates with the separate historical percentile-rank timeline.

### 3. Sector RRG

Export the current sector RRG view from the same 24 July artifact. Add a text caption in the article, rather than an overlaid callout, identifying Consumer Durables as the cleanest leader; Chemicals and Cement as constructive; Realty and Pharma as mature; IT as improving; and financials as non-confirming.

### 4. Breadth participation chart

A horizontal-bar SVG comparing four compact, directly labelled measures: Nifty 50 above 50D (44%), Nifty 50 above 200D (46%), Nifty 500 above 50D (48%), and Midcap Select Stage 2 (40%). The figure title must say “Participation is selective, not broken.” It must not imply that the four measures use identical denominators or definitions.

## Article integration

Modify only `reports/substack/india_market_thesis_20260724/substack_india_market_thesis_20260724.md` and add the four assets below `reports/substack/india_market_thesis_20260724/assets/`. Use Markdown images with meaningful alt text and one-sentence captions immediately below each image. The existing tables, source trail, cautionary language, and disclaimer remain intact.

## Quality and data rules

- Every visual carries “As of 24 Jul 2026”; the market-pulse figure separately identifies its 23 Jul flow data.
- RRG figures use current snapshot data only. Historical RRG timelines are not shown because their methodology differs.
- Use semantic colour roles: green for leading/constructive, amber for improving or maturing, red for weakening/lagging, and slate for neutral context. Labels—not colour alone—communicate status.
- Do not create stock-photo or AI-art imagery. Do not add a standalone dashboard, JavaScript, or an external publishing step.
- Keep figures legible at a 320 px mobile width. SVG text must remain readable and PNG exports must be at least 1,600 px wide.
- The stale/misdated local EOD narrative remains excluded.

## Verification

1. Confirm each linked asset exists and the Markdown paths resolve.
2. Confirm the SVG files parse as XML and contain the stated current-date labels.
3. Open the resulting article or render its images to check mobile-width legibility, alt text, captions, and contrast.
4. Compare each RRG figure against `reports/latest/market_breadth_rrg.html` and each pulse/breadth number against the verified source values before hand-off.
