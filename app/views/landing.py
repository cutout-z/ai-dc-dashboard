"""Landing page — dashboard overview."""

import streamlit as st

st.title("AI & DC Dashboard")
st.caption("Supply chain intelligence, investment prospecting, LLM & GPU tracking")
st.markdown(
    """
### Financial Analysis

Tracks the underlying financial health and capital allocation of the companies at the centre of the AI trade.
CAPEX guidance revisions are a leading indicator of whether hyperscaler conviction is holding or retreating.
Equity metrics and consensus estimates set the context for whether current valuations price in the growth or leave room.
The Other Signals page captures cross-cutting risk signals — semi demand, GPU lease rates, frontier lab burn — that don't fit neatly into a single company view.

### LLM & GPU Performance

The capability and cost trajectory of models is central to whether the AI monetisation thesis plays out.
Rapidly falling inference costs compress margins across the stack; improving open-weight models commoditise closed API providers; shifts in human preference rankings change which labs win developer mindshare.
This section tracks the signals that would show those dynamics shifting — benchmark trajectories, pricing curves, hardware supply, and lab revenue against valuation.

### Supply Chain

Maps where value accumulates — and erodes — across the AI infrastructure stack.
Power constraints, input cost inflation, and commodity cycles all affect which parts of the chain can sustain margins.
Useful for identifying crowded vs. overlooked segments, tracking structural bottlenecks (interconnection queue depth, cooling materials, power procurement), and monitoring whether the build-out thesis is running into physical limits.

### Australian Market

Analysis of the ANZ data centre market: capacity additions, operator financials, grid constraints, and project pipeline.
Relevant for assessing AU-listed DC operators and infrastructure plays with local exposure, and for stress-testing demand scenarios against NEM grid capacity and ESOO projections.

### Other

Supporting layers: a curated news feed for event-driven risk (earnings surprises, CAPEX announcements, model releases, regulatory shifts),
source health to verify data freshness before drawing conclusions, and a glossary for shared terminology.
"""
)
