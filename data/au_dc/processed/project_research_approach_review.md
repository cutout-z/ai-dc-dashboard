# AU DC Project Research Approach Review

## Bottom Line

The current AU project table is not audit-grade and should not be treated as a source of truth. It is a useful lead list, but the research approach is too loose for capacity totals, project comparisons, or implied market share.

## Structural Issues

- The seed table stores source labels, not source URLs, page references, evidence text, source dates, or last-verified dates.
- The `facility_mw` field mixes IT capacity, gross power capacity, power consumption, campus full-build capacity, regional estimates, and sometimes grid/substation capacity.
- Hyperscaler rows are regional estimates with `Various` locations, so they are not comparable to named physical facilities.
- PUE/WUE values are often design targets or portfolio/global averages, but are displayed beside individual facilities.
- Under-construction projects receive a 100% risk weight even when `power_secured` is blank.
- CAPEX is mostly benchmark-modelled, not disclosed.

## Source Spot Checks Completed

- CDC aggregate guidance: the Infratil/CDC Investor Day deck dated 26 March 2026 supports aggregate ANZ total capacity of 2.7GW+ to FY2034, 18 operational data centres, and 5 data centres under construction. It does not support the removed Sydney/Melbourne/Canberra `Future Build` rows or their exact split. Source: https://infratil.com/news/cdc-investor-presentation-and-guidance-update/cdc-infratil-investor-day-presentation/
- NEXTDC S7: official NEXTDC release dated 17 October 2024 supports an Eastern Creek S7 site with approximately 550MW potential capacity, subject to development approval. Current row directionally matches, but should store the official URL, date, and "subject to Development Approval" qualifier. Source: https://www.nextdc.com/news/nextdc-acquires-new-sydney-data-centre-s7
- NEXTDC M4: official NEXTDC page states M4 targets 150MW IT capacity. Current seed row records 200MW, so this row appears overstated or using an undocumented basis. Source: https://www.nextdc.com/data-centres/melbourne-data-centres/m4-melbourne
- CDC Marsden Park: NSW Planning Portal states 504MW power consumption and a 720MW substation. Current seed row records 308MW, so its capacity basis is unclear and not comparable. Source: https://www.planningportal.nsw.gov.au/major-projects/projects/marsden-park-data-centre
- Keppel Morwell: official Keppel release supports up to 720MW gross power capacity, but describes a leased site/powerbank with pre-development work, planning approvals, and power/water contracting still to follow. It should be classified as pre-development gross power capacity, not a normal proposed project MW. Source: https://www.keppel.com/media/keppel-secures-720mw-powerbank-for-ai-data-centre-campus-near-melbourne-expanding-powerbank-to-over-1gw/
- AirTrunk MEL2: Data Center Dynamics reports, according to AirTrunk, more than 354MW capacity and more than A$5bn investment. Current row is directionally supported but needs primary AirTrunk URL if available. Source: https://www.datacenterdynamics.com/en/news/airtrunk-acquires-site-in-melbourne-australia-for-354mw-data-center/
- AirTrunk SYD3: Data Centre Magazine reports 320+MW IT load and an onsite 132kV substation. Current seed records 330MW; use 320+MW IT load unless a primary source supports 330MW. Source: https://datacentremagazine.com/data-centres/airtrunk-open-new-320mw-western-sydney-data-centre
- Macquarie IC3/IC2: official Macquarie pages support a 65MW Macquarie Park campus and IC3 Super West at 47MW IT load. The current `IC2 Bungarribee` 110MW row does not align with these official pages and needs full remediation. Sources: https://www.macquariedatacentres.com/data-centres/sydney/macquarie-park-campus/ic3-super-west/ and https://www.macquarietechnologygroup.com/our-data-centres/

## Remediation Rules

- Add mandatory fields before a row can be evidence grade A: `source_url`, `source_date`, `source_page_or_section`, `evidence_quote`, `capacity_basis`, `last_verified_at`.
- Split capacity into `it_load_mw`, `gross_power_mw`, `power_consumption_mw`, `grid_connection_mva`, and `campus_full_build_mw`.
- Move regional hyperscaler estimates to a separate market-sizing table.
- Keep D/E rows out of default capacity totals.
- Require explicit source evidence for `power_secured` before assigning 100% risk weight to under-construction rows.

## Remediation Batch 1

- Added source URL, evidence quote, capacity basis, last verified date, and split-capacity fields to the seed schema.
- Remediated these rows to grade A using primary/company/regulator sources: NEXTDC S7, NEXTDC M4, CDC Marsden Park, Keppel Morwell, STACK Sydney SYD01, Macquarie IC3 East, and Macquarie IC3 Super West.
- Remediated these rows to grade B using named secondary/press-release mirror sources pending primary-source replacement: AirTrunk SYD3 and AirTrunk MEL2.
- Corrected NEXTDC M4 from 200MW to 150MW IT capacity.
- Corrected NEXTDC S7 from under construction to proposed because the cited official release is explicitly subject to development approval.
- Corrected CDC Marsden Park from 308MW to 504MW power consumption, with `capacity_basis=power_consumption_mw`.
- Reclassified Keppel Morwell as 720MW `gross_power_mw`, not normal IT load.
- Corrected Macquarie rows: the operating row is IC3 East at approximately 12MW IT load; IC3 Super West is the separate 47MW IT-load project under construction.

## Remediation Batch 2-5

- Quarantined regional hyperscaler estimates and unsupported project estimates from capacity totals. Their prior values are retained in `unverified_capacity_mw`.
- Added `include_in_project_totals`, `remediation_status`, and `remediation_notes` so the dashboard can separate verified capacity from audit-trail rows.
- Updated Market Overview to use included rows only; Project Analysis now defaults to hiding quarantined rows with a toggle to inspect them.
- Remediated NEXTDC operating/proposed rows from the official NEXTDC location list where row-level MW is disclosed.
- Remediated AirTrunk SYD1/SYD2/SYD3/MEL1/MEL2 using the AirTrunk media-release mirror; these remain grade B pending a primary AirTrunk page.
- Remediated Vantage MEL1 to 64MW IT capacity from Vantage's official MEL1 page.
- Remediated Doma Minchinbury to 62MW IT load / 90MVA envelope from the PRNewswire Starwood-Doma-Telstra announcement.
- Remediated Equinix SY9x/SY10x using Equinix's official xScale press release.
- Remediated CDC campus rows using CDC official regional pages: Eastern Creek 200MW+, Brooklyn 350MW+, Laverton 400MW+, Hume Campus Two 51MW, Fyshwick 45MW, Beard 39MW, and Maddington 200MW+.
- Quarantined CDC legacy split rows that do not map to a current disclosed CDC campus/capacity.
- Final included project capacity now consists only of rows with row-level source URLs, evidence text, and capacity basis. All other rows are grade Q and excluded from project capacity totals pending source remediation.

## Useful External Alternatives

- Baxtel sells site-level global data centre datasets with power capacity and lifecycle status.
- Data Center Map offers data exports and publishes coverage statistics, but it remains a directory source that should be cross-checked against primary evidence.
- Cloudscene provides market/directory coverage rather than a full audit-grade project pipeline.
