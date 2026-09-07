"""AEMO MMS monthly-archive horizon helpers (pure; no network, no nemosis).

AEMO publishes MMSDM *monthly* archives (nemweb.com.au) for calendar month M
only after M's settlement data is final — the archive for M appears some days
into M+1, never during M itself. Requests against the monthly archives must
therefore target a month whose archive is actually published: the registration
snapshot tables (DUDETAILSUMMARY / DUDETAIL) and the dynamic dispatch tables
are fetched month-by-month, and a request for an unpublished month silently
yields no data (nemosis logs "not downloaded" and returns nothing).

This module centralises the horizon arithmetic used by the AU DC ETL so the
fetch code never hard-codes a month again:

- ``latest_candidate_month`` — the newest archive month a publication-lag
  model will allow *by the clock*. It is a candidate, not a claim: the fetch
  layer still has to observe the archive (data present) before recording it
  as the source vintage, and steps back a bounded number of months when the
  newest candidate is not actually published yet ("no new release ⇒ no false
  freshness advance").
- month arithmetic/formatting helpers that speak nemosis's
  ``%Y/%m/%d %H:%M:%S`` request-window language.

All functions take/return ``(year, month)`` tuples (1-based month) and accept
an injectable ``today`` so fixed-clock fixtures can freeze time.

Example (today = 2026-09-07, lag 10 days after month end):

    Aug 31 + 10d = 2026-09-10 > today  ->  August's archive is not allowed yet
    Jul 31 + 10d = 2026-08-10 <= today  ->  July is the latest candidate month
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, List, Optional, Sequence, Tuple, Union

#: A calendar month as (year, month) with 1-based month.
Month = Tuple[int, int]

#: Publication-lag model: an archive for month M is only *candidate* once
#: M's last day is at least this many days in the past. AEMO publishes the
#: monthly MMSDM release a few days into the following month; the constant is
#: deliberately conservative (a stale-by-a-week snapshot is fine, a request
#: for an unpublished archive is not). The fetch layer still requires actual
#: data before recording a vintage.
PUBLICATION_LAG_DAYS = 10

_NEMOSIS_FMT = "%Y/%m/%d %H:%M:%S"


def _month_dt(m: Month) -> datetime:
    """First instant of month ``m`` as a datetime."""
    return datetime(m[0], m[1], 1)


def add_months(m: Month, delta: int) -> Month:
    """Shift a month by ``delta`` (negative goes back); handles year wrap."""
    total = m[0] * 12 + (m[1] - 1) + delta
    return (total // 12, total % 12 + 1)


def month_label(m: Month) -> str:
    """'YYYY-MM' label (matches the ``year_month`` column convention)."""
    return f"{m[0]:04d}-{m[1]:02d}"


def parse_month_label(label: str) -> Optional[Month]:
    """Parse 'YYYY-MM' back to a Month; None when malformed."""
    try:
        parts = label.split("-")
        if len(parts) != 2:
            return None
        return (int(parts[0]), int(parts[1]))
    except (TypeError, ValueError):
        return None


def month_end_date(m: Month) -> date:
    """The last calendar day of month ``m``."""
    nxt = _month_dt(add_months(m, 1))
    return (nxt - timedelta(days=1)).date()


def first_instant(m: Month) -> str:
    """First instant of month ``m`` in nemosis's request format."""
    return _month_dt(m).strftime(_NEMOSIS_FMT)


def day2_instant(m: Month) -> str:
    """Day-2 00:00 of month ``m`` — the registration snapshot window end.

    The original snapshot query used ``start = 01/01 00:00``,
    ``end = 01/02 00:00`` (state as of the first instant of the requested
    month, DUDETAIL EFFECTIVEDATE < end). day2_instant reproduces that exact
    window for an arbitrary month.
    """
    return (_month_dt(m) + timedelta(days=1)).strftime(_NEMOSIS_FMT)


def registration_snapshot_date(m: Month) -> str:
    """ISO date ('2026-08-01') the registration roster is captured as of."""
    return f"{m[0]:04d}-{m[1]:02d}-01"


def latest_candidate_month(today: date, lag_days: int = PUBLICATION_LAG_DAYS) -> Month:
    """Newest archive month the publication-lag model allows for ``today``.

    Walks back from the current calendar month until ``month_end + lag_days
    <= today``. Never returns the current (still-unpublished) month.
    """
    m = (today.year, today.month)
    while month_end_date(m) + timedelta(days=lag_days) > today:
        m = add_months(m, -1)
    return m


def window_month_keys(start: Month, end: Month) -> List[str]:
    """'YYYY-MM' labels for every month in [start, end], inclusive, ascending."""
    months: List[str] = []
    m = start
    while m <= end:
        months.append(month_label(m))
        m = add_months(m, 1)
    return months


def max_month(months: Iterable[Union[Month, str]]) -> Optional[Month]:
    """Largest month in an iterable of Months or 'YYYY-MM' labels; None if empty."""
    best: Optional[Month] = None
    for item in months:
        m = item if isinstance(item, tuple) else parse_month_label(str(item))
        if m is None:
            continue
        if best is None or m > best:
            best = m
    return best
