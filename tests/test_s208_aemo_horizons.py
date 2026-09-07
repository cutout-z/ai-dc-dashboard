"""S2-08 (C10) verification: dynamic AEMO MMS archive horizons, vintage
recording in AU DC outputs, and publication-lag-aware incremental demand.

Review reproductions:
- registration queries must never be hard-coded to a fixed January/2026-04
  window again — a fixed-clock fixture with an available-month list resolves
  the latest available snapshot month, not January (never 2026-01);
- "no new release => no false freshness advance": when the newest candidate
  archive is not actually published (no data), the resolver steps back a
  bounded number of months and records the month that really produced data;
  when nothing in the window yields data the run fails loudly instead of
  silently re-serving an older snapshot; an unchanged dataset rewrites no
  file (parquet byte-identical, sidecar byte-identical);
- demand refreshes add complete missing months without replaying the entire
  history: the fetch window starts the month after the last month already in
  the output parquet and ends at the latest candidate archive month; only
  that window is requested; existing rows stay byte-for-byte untouched;
- outputs record their source vintage (archive month / registration snapshot
  date / workbook edition) in `<file>.parquet.vintage.json` sidecars, and the
  app captions label the series from them (falling back gracefully).
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.au_dc import aemo_horizon as hz  # noqa: E402
from etl.au_dc import fetch_aemo_nemosis as fetcher  # noqa: E402
from etl.au_dc import source_vintage as sv  # noqa: E402
from app.lib import au_dc_vintage as av  # noqa: E402

REGIONS = ["NSW1", "VIC1"]


# ────────────────────────────────────────────────────────────────────────────
# Fixtures / builders
# ────────────────────────────────────────────────────────────────────────────
def make_raw_dispatch(months, regions=REGIONS, intervals_per_month=6):
    """Synthetic DISPATCHREGIONSUM rows: one constant demand per region."""
    rows = []
    for (y, m) in months:
        ym = f"{y:04d}-{m:02d}"
        base_time = pd.Timestamp(f"{ym}-10 00:05:00")
        for r, region in enumerate(regions):
            value = 5000.0 + r * 1000.0
            for i in range(intervals_per_month):
                rows.append(
                    {
                        "REGIONID": region,
                        "TOTALDEMAND": value,
                        "SETTLEMENTDATE": base_time + pd.Timedelta(minutes=5 * i),
                    }
                )
    return pd.DataFrame(rows)


def make_demand_parquet(path: Path, last_month, regions=REGIONS):
    """Write a legacy-shaped demand parquet through ``last_month``."""
    months = hz.window_month_keys((2020, 1), last_month)
    rows = []
    for ym in months:
        for r, region in enumerate(regions):
            avg = 5000.0 + r * 1000.0
            intervals = 8640
            hours = intervals * 5 / 60
            rows.append(
                {
                    "nem_region": region,
                    "year_month": ym,
                    "avg_demand_mw": avg,
                    "max_demand_mw": avg,
                    "intervals": intervals,
                    "hours": hours,
                    "energy_twh": avg * hours / 1_000_000,
                }
            )
    df = pd.DataFrame(rows).sort_values(["nem_region", "year_month"]).reset_index(drop=True)
    df.to_parquet(path, index=False)
    return df


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ────────────────────────────────────────────────────────────────────────────
# 1. Horizon arithmetic (pure)
# ────────────────────────────────────────────────────────────────────────────
class TestHorizonMath:
    def test_latest_candidate_month_boundary_table(self):
        # Aug ends Aug 31; +10d lag => allowed from Sep 10.
        assert hz.latest_candidate_month(date(2026, 9, 7)) == (2026, 7)
        assert hz.latest_candidate_month(date(2026, 9, 9)) == (2026, 7)
        assert hz.latest_candidate_month(date(2026, 9, 10)) == (2026, 8)
        # Mid-month, well past the previous archive.
        assert hz.latest_candidate_month(date(2026, 7, 20)) == (2026, 6)
        # January: current + previous months are both unpublished by the model.
        assert hz.latest_candidate_month(date(2026, 1, 5)) == (2025, 11)
        assert hz.latest_candidate_month(date(2026, 2, 11)) == (2026, 1)

    def test_candidate_never_current_month(self):
        # Even on the 28th, the current month's archive is never a candidate.
        for day in (1, 10, 28):
            got = hz.latest_candidate_month(date(2026, 8, day))
            assert got < (2026, 8)

    def test_month_helpers(self):
        assert hz.add_months((2026, 1), -1) == (2025, 12)
        assert hz.add_months((2025, 12), 1) == (2026, 1)
        assert hz.add_months((2026, 8), 1) == (2026, 9)
        assert hz.month_label((2026, 3)) == "2026-03"
        assert hz.parse_month_label("2026-03") == (2026, 3)
        assert hz.parse_month_label("not-a-month") is None
        assert hz.first_instant((2026, 8)) == "2026/08/01 00:00:00"
        assert hz.day2_instant((2026, 8)) == "2026/08/02 00:00:00"
        assert hz.registration_snapshot_date((2026, 8)) == "2026-08-01"
        assert hz.month_end_date((2026, 8)) == date(2026, 8, 31)
        assert hz.month_end_date((2026, 2)) == date(2026, 2, 28)
        assert hz.window_month_keys((2026, 4), (2026, 7)) == [
            "2026-04", "2026-05", "2026-06", "2026-07",
        ]
        assert hz.max_month(["2026-03", "2026-11", "2026-04"]) == (2026, 11)
        assert hz.max_month([]) is None

    def test_instants_parse_in_nemosis_format(self):
        from datetime import datetime

        for inst in (hz.first_instant((2026, 8)), hz.day2_instant((2025, 1))):
            parsed = datetime.strptime(inst, "%Y/%m/%d %H:%M:%S")
            assert parsed is not None


# ────────────────────────────────────────────────────────────────────────────
# 2. Source-vintage sidecars (write/read/determinism)
# ────────────────────────────────────────────────────────────────────────────
class TestVintageSidecar:
    def test_roundtrip_and_naming(self, tmp_path):
        out = tmp_path / "nem_demand_actual.parquet"
        vintage = {
            "schema_version": 1,
            "output": out.name,
            "archive_month": "2026-07",
            "data_through_month": "2026-07",
            "fetch_mode": "incremental",
        }
        sidecar = sv.write_parquet_with_vintage(pd.DataFrame({"a": [1]}), out, vintage)
        assert sidecar.name == "nem_demand_actual.parquet.vintage.json"
        assert sv.read_vintage(out) == vintage
        assert sv.read_vintage(out.with_name("missing.parquet")) == {}

    def test_sidecar_not_rewritten_when_unchanged(self, tmp_path):
        out = tmp_path / "x.parquet"
        vintage = {"archive_month": "2026-07"}
        sv.write_parquet_with_vintage(pd.DataFrame({"a": [1]}), out, vintage)
        sidecar = sv.vintage_path_for(out)
        before = sidecar.stat().st_mtime_ns
        sv.write_parquet_with_vintage(pd.DataFrame({"a": [1]}), out, vintage)
        assert sidecar.stat().st_mtime_ns == before  # byte-identical => untouched
        assert sidecar.read_text(encoding="utf-8") == json.dumps(
            vintage, sort_keys=True, indent=2, default=str
        ) + "\n"

    def test_vintage_dict_content_only(self):
        v = sv.vintage_dict("g.parquet", source_tables=["DUDETAILSUMMARY"],
                            extra={"archive_month": "2026-08"}, row_count=5)
        assert v["schema_version"] == 1
        assert v["row_count"] == 5
        # content-derived only: no generated_at/run timestamp keys
        assert not any("time" in k or "date" in k for k in v)


# ────────────────────────────────────────────────────────────────────────────
# 3. Demand window planning + aggregation (no network)
# ────────────────────────────────────────────────────────────────────────────
class TestDemandWindowPlanning:
    def test_incremental_window_never_replays_history(self, tmp_path):
        path = tmp_path / "nem_demand_actual.parquet"
        make_demand_parquet(path, (2026, 3))
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=False)
        assert plan["mode"] == "incremental"
        assert plan["start_month"] == (2026, 4)
        assert plan["horizon"] == (2026, 7)
        assert hz.window_month_keys(plan["start_month"], plan["horizon"]) == [
            "2026-04", "2026-05", "2026-06", "2026-07",
        ]  # the ONLY months that may be requested

    def test_noop_when_series_already_through_horizon(self, tmp_path):
        path = tmp_path / "nem_demand_actual.parquet"
        make_demand_parquet(path, (2026, 7))
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=False)
        assert plan["mode"] == "noop"

    def test_full_backfill_starts_at_history_origin(self, tmp_path):
        path = tmp_path / "nem_demand_actual.parquet"
        make_demand_parquet(path, (2026, 7))
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=True)
        assert plan["mode"] == "full"
        assert plan["start_month"] == fetcher.DEMAND_HISTORY_START == (2020, 1)

    def test_missing_file_means_full_first_build(self, tmp_path):
        path = tmp_path / "nem_demand_actual.parquet"
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=False)
        assert plan["mode"] == "full"
        assert plan["start_month"] == (2020, 1)

    def test_unreadable_file_falls_back_to_full(self, tmp_path):
        path = tmp_path / "nem_demand_actual.parquet"
        path.write_bytes(b"not a parquet")
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=False)
        assert plan["mode"] == "full"

    def test_contiguous_last_month_helper(self):
        contig = fetcher._contiguous_last_month
        assert contig([(2020, 1), (2020, 2), (2020, 3)], (2020, 1)) == (2020, 3)
        # hole at 2020-03 -> contiguous run stops at 2020-02
        assert contig([(2020, 1), (2020, 2), (2020, 4)], (2020, 1)) == (2020, 2)
        assert contig([], (2020, 1)) is None
        # series starting after history origin is not contiguous from origin
        assert contig([(2021, 1)], (2020, 1)) is None

    def test_mid_series_hole_is_backfilled_not_skipped(self, tmp_path):
        # A transient partial download leaves a hole at 2026-05 (04 and 06
        # present). Incremental planning must re-request from the hole, not
        # declare the series whole at 06.
        path = tmp_path / "nem_demand_actual.parquet"
        df = make_demand_parquet(path, (2026, 6))
        df[df["year_month"] != "2026-05"].to_parquet(path, index=False)
        plan = fetcher._plan_demand_window(path, date(2026, 9, 7), full_backfill=False)
        assert plan["mode"] == "incremental"
        assert plan["start_month"] == (2026, 5)
        assert plan["horizon"] == (2026, 7)

    def test_aggregation_matches_legacy_formula(self):
        raw = make_raw_dispatch([(2026, 4), (2026, 5)], intervals_per_month=6)
        monthly = fetcher._aggregate_demand_rows(raw)
        assert len(monthly) == 2 * 2  # two regions x two months
        row = monthly[(monthly.nem_region == "NSW1") & (monthly.year_month == "2026-04")].iloc[0]
        assert row["intervals"] == 6
        assert row["avg_demand_mw"] == 5000.0
        assert row["max_demand_mw"] == 5000.0
        assert row["hours"] == pytest.approx(6 * 5 / 60)
        assert row["energy_twh"] == pytest.approx(5000.0 * row["hours"] / 1_000_000)

    def test_aggregation_empty_and_clean(self):
        empty = fetcher._aggregate_demand_rows(pd.DataFrame())
        assert empty.empty
        assert fetcher._aggregate_demand_rows(None).empty


# ────────────────────────────────────────────────────────────────────────────
# 4. fetch_regional_demand end-to-end (fake compiler; fixed clock)
# ────────────────────────────────────────────────────────────────────────────
class TestDemandFetchIncremental:
    def _run(self, monkeypatch, tmp_path, existing_last, today, full_backfill=False,
             available_months=None):
        demand_path = tmp_path / "nem_demand_actual.parquet"
        if existing_last is not None:
            make_demand_parquet(demand_path, existing_last)
        monkeypatch.setattr(fetcher, "DEMAND_PATH", demand_path)
        monkeypatch.setattr(fetcher, "CACHE_DIR", tmp_path / "cache")

        calls: list[tuple[str, str]] = []

        def fake_compiler(start_time, end_time, table_name, raw_data_location,
                          select_columns, fformat):
            calls.append((start_time, end_time))
            assert table_name == "DISPATCHREGIONSUM"
            assert fformat == "csv"
            start = pd.Timestamp(start_time)
            end = pd.Timestamp(end_time)
            # emulate nemosis month-archive behaviour: data for every archive
            # month in [start, end] (rows > start & <= end)
            months = []
            probe = start.normalize().replace(day=1)
            while probe < end:
                months.append((probe.year, probe.month))
                probe = (probe + pd.offsets.MonthEnd(1)).normalize() + pd.Timedelta(days=1)
            if available_months is not None:
                months = [m for m in months if m in available_months]
            return make_raw_dispatch(months)

        monkeypatch.setattr(fetcher, "dynamic_data_compiler", fake_compiler)
        vintage = fetcher.fetch_regional_demand(full_backfill=full_backfill, today=today)
        df = pd.read_parquet(demand_path)
        return calls, vintage, df, demand_path

    def test_incremental_appends_missing_months_only(self, monkeypatch, tmp_path):
        calls, vintage, df, path = self._run(
            monkeypatch, tmp_path, existing_last=(2026, 3),
            today=date(2026, 9, 7),
        )
        # Exactly one request, spanning 2026-04 .. 2026-07 only — never 2020+.
        assert len(calls) == 1
        assert calls[0][0] == "2026/04/01 00:00:00"
        assert calls[0][1] == "2026/08/01 00:00:00"
        # Series now extends through the candidate archive month.
        assert df["year_month"].min() == "2020-01"
        assert df["year_month"].max() == "2026-07"
        assert len(df) == 2 * len(hz.window_month_keys((2020, 1), (2026, 7)))
        assert vintage["fetch_mode"] == "incremental"
        assert vintage["data_through_month"] == "2026-07"
        assert vintage["archive_month"] == "2026-07"
        # Existing rows are byte-for-byte untouched (same values, same order).
        kept = df[df["year_month"] < "2026-04"].reset_index(drop=True)
        legacy = make_demand_parquet(tmp_path / "legacy.parquet", (2026, 3))
        pd.testing.assert_frame_equal(kept, legacy)

    def test_no_new_release_means_no_false_freshness_advance(self, monkeypatch, tmp_path):
        # Run twice on the same clock: second run is a no-op (no fetch, files
        # byte-identical) — a weekly re-run cannot fake an advance.
        calls, _, df1, path = self._run(
            monkeypatch, tmp_path, existing_last=(2026, 3),
            today=date(2026, 9, 7),
        )
        assert len(calls) == 1
        bytes1 = path.read_bytes()
        sidecar = sv.vintage_path_for(path)
        sc1 = sidecar.read_bytes()

        # second identical run
        calls2, vintage2, df2, _ = self._run(
            monkeypatch, tmp_path, existing_last=None,  # file already exists
            today=date(2026, 9, 7),
        )
        assert calls2 == []  # noop: nothing requested
        assert path.read_bytes() == bytes1
        assert sidecar.read_bytes() == sc1
        pd.testing.assert_frame_equal(df1, df2)

    def test_clock_advance_adds_only_newly_missing_months(self, monkeypatch, tmp_path):
        # Build the series to 2026-07 (as the Sep-7 run would), then run on
        # Oct-20: only Aug+Sep are fetched.
        calls, vintage, df, _ = self._run(
            monkeypatch, tmp_path, existing_last=(2026, 3),
            today=date(2026, 9, 7),
        )
        assert df["year_month"].max() == "2026-07"
        calls2, vintage2, df2, _ = self._run(
            monkeypatch, tmp_path, existing_last=None,
            today=date(2026, 10, 20),
        )
        assert len(calls2) == 1
        assert calls2[0][0] == "2026/08/01 00:00:00"
        assert calls2[0][1] == "2026/10/01 00:00:00"
        assert df2["year_month"].max() == "2026-09"
        assert vintage2["data_through_month"] == "2026-09"
        # Values of pre-existing months are untouched (indexes shift when the
        # NSW1 block grows — compare values, not positional index).
        pre = df[df["year_month"] < "2026-08"].reset_index(drop=True)
        pre2 = df2[df2["year_month"] < "2026-08"].reset_index(drop=True)
        assert pre2.equals(pre)
        assert len(pre2) == len(pre) == 158

    def test_full_backfill_replays_from_origin(self, monkeypatch, tmp_path):
        calls, vintage, df, _ = self._run(
            monkeypatch, tmp_path, existing_last=(2026, 3),
            today=date(2026, 9, 7), full_backfill=True,
        )
        assert len(calls) == 1
        assert calls[0][0] == "2020/01/01 00:00:00"
        assert vintage["fetch_mode"] == "full"

    def test_partial_publication_trails_honestly(self, monkeypatch, tmp_path):
        # Only 2026-04 exists beyond the existing series: data_through must
        # reflect April, never the candidate month.
        calls, vintage, df, _ = self._run(
            monkeypatch, tmp_path, existing_last=(2026, 3),
            today=date(2026, 9, 7),
            available_months={(2026, 4)},
        )
        assert df["year_month"].max() == "2026-04"
        assert vintage["data_through_month"] == "2026-04"
        assert vintage["archive_month"] == "2026-04"

    def test_failed_fetch_preserves_last_good(self, monkeypatch, tmp_path):
        demand_path = tmp_path / "nem_demand_actual.parquet"
        make_demand_parquet(demand_path, (2026, 3))
        monkeypatch.setattr(fetcher, "DEMAND_PATH", demand_path)
        monkeypatch.setattr(fetcher, "CACHE_DIR", tmp_path / "cache")

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(fetcher, "dynamic_data_compiler", boom)
        before = demand_path.read_bytes()
        out = fetcher.fetch_regional_demand(today=date(2026, 9, 7))
        assert out is None
        assert demand_path.read_bytes() == before  # last-good preserved

    def test_hole_self_heals_on_next_incremental_run(self, monkeypatch, tmp_path):
        # Series through 2026-06 with 2026-05 missing -> the run must request
        # 2026-05..2026-07 and restore contiguity through the horizon.
        demand_path = tmp_path / "nem_demand_actual.parquet"
        df = make_demand_parquet(demand_path, (2026, 6))
        df[df["year_month"] != "2026-05"].to_parquet(demand_path, index=False)
        monkeypatch.setattr(fetcher, "DEMAND_PATH", demand_path)
        monkeypatch.setattr(fetcher, "CACHE_DIR", tmp_path / "cache")

        calls: list[tuple[str, str]] = []

        def fake_compiler(start_time, end_time, table_name, raw_data_location,
                          select_columns, fformat):
            calls.append((start_time, end_time))
            start = pd.Timestamp(start_time)
            end = pd.Timestamp(end_time)
            months = []
            probe = start.normalize().replace(day=1)
            while probe < end:
                months.append((probe.year, probe.month))
                probe = (probe + pd.offsets.MonthEnd(1)).normalize() + pd.Timedelta(days=1)
            return make_raw_dispatch(months)

        monkeypatch.setattr(fetcher, "dynamic_data_compiler", fake_compiler)
        vintage = fetcher.fetch_regional_demand(today=date(2026, 9, 7))
        assert vintage is not None
        assert calls[0][0] == "2026/05/01 00:00:00"  # from the hole, not 06
        result = pd.read_parquet(demand_path)
        assert result["year_month"].max() == "2026-07"
        # every month 2020-01..2026-07 present for both regions (no gap at 05)
        expected_months = hz.window_month_keys((2020, 1), (2026, 7))
        present = result.groupby("year_month")["nem_region"].nunique()
        assert (present == 2).all()
        assert list(present.index) == expected_months


# ────────────────────────────────────────────────────────────────────────────
# 5. Registration snapshot resolution (fixed clock + available months)
# ────────────────────────────────────────────────────────────────────────────
class TestSnapshotResolution:
    def _resolver(self, monkeypatch, available):
        """Patch _fetch_summary_snapshot so only ``available`` months return data."""
        cache = Path("/tmp/irrelevant-cache")

        def fake_summary(month, cache_dir):
            assert cache_dir == cache
            if month in available:
                return pd.DataFrame({"DUID": ["G1"], "STATIONID": ["BAYSW1"],
                                     "REGIONID": ["NSW1"]})
            return pd.DataFrame({"DUID": []})

        monkeypatch.setattr(fetcher, "_fetch_summary_snapshot", fake_summary)
        return fetcher._resolve_snapshot_month(cache, today=date(2026, 9, 7))

    def test_selects_latest_available_snapshot_not_january(self, monkeypatch):
        # Verify criterion: fixed clock + available months -> latest available,
        # never the frozen 2026-01.
        month, df = self._resolver(monkeypatch, {(2026, 7)})
        assert month == (2026, 7)
        assert not df.empty
        assert month != (2026, 1)

    def test_stepping_back_when_newest_not_published(self, monkeypatch):
        # Candidate for Sep-7 is 2026-07; only June is actually published.
        month, _ = self._resolver(monkeypatch, {(2026, 6)})
        assert month == (2026, 6)

    def test_no_available_month_fails_loudly(self, monkeypatch):
        with pytest.raises(RuntimeError) as err:
            self._resolver(monkeypatch, set())
        msg = str(err.value)
        assert "No published AEMO MMS archive" in msg
        # Tried candidate (2026-07) plus bounded backstep (3) — not unbounded.
        for tried in ("2026-07", "2026-06", "2026-05", "2026-04"):
            assert tried in msg

    def test_fetch_error_steps_back(self, monkeypatch):
        cache = Path("/tmp/c")
        calls = []

        def flaky(month, cache_dir):
            calls.append(month)
            if month == (2026, 7):
                raise RuntimeError("boom")  # candidate unavailable (network/archive)
            return pd.DataFrame({"DUID": ["G1"]})

        monkeypatch.setattr(fetcher, "_fetch_summary_snapshot", flaky)
        month, df = fetcher._resolve_snapshot_month(cache, today=date(2026, 9, 7))
        assert month == (2026, 6)
        assert not df.empty


# ────────────────────────────────────────────────────────────────────────────
# 6. fetch_and_build end-to-end (registration snapshot + vintage sidecars)
# ────────────────────────────────────────────────────────────────────────────
def _summary_frame():
    return pd.DataFrame(
        {
            "DUID": ["G1", "G2"],
            "STATIONID": ["BAYSW1", "BAYSW1"],
            "REGIONID": ["NSW1", "NSW1"],
            "DISPATCHTYPE": ["GENERATOR", "GENERATOR"],
            "SCHEDULE_TYPE": ["GENERATING UNIT", "GENERATING UNIT"],
        }
    )


def _detail_frame():
    return pd.DataFrame(
        {
            "DUID": ["G1", "G2"],
            "EFFECTIVEDATE": ["2026-01-01 00:00:00", "2026-01-01 00:00:00"],
            "REGISTEREDCAPACITY": ["100.0", "200.0"],
            "MAXCAPACITY": ["100.0", "200.0"],
        }
    )


class TestFetchAndBuildRegistration:
    def _install(self, monkeypatch, tmp_path, available_months):
        processed = tmp_path / "processed"
        cache = tmp_path / "cache"
        cache.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(fetcher, "PROCESSED_DIR", processed)
        monkeypatch.setattr(fetcher, "CACHE_DIR", cache)
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path / "raw")  # no workbook/list
        monkeypatch.setattr(fetcher, "load_registration_fuel_lookup", lambda: {})

        def fake_compiler(start_time, end_time, table_name, raw_data_location,
                          select_columns, fformat):
            month = (int(start_time[:4]), int(start_time[5:7]))
            if table_name == "DUDETAILSUMMARY":
                return _summary_frame() if month in available_months else _summary_frame().iloc[0:0]
            if table_name == "DUDETAIL":
                return _detail_frame()
            raise AssertionError(f"unexpected table {table_name}")

        monkeypatch.setattr(fetcher, "dynamic_data_compiler", fake_compiler)
        monkeypatch.setattr(fetcher, "load_aemo_pipeline",
                            lambda: (pd.DataFrame(), None))
        return processed

    def test_registration_outputs_carry_dynamic_vintage(self, monkeypatch, tmp_path):
        processed = self._install(
            monkeypatch, tmp_path, available_months={(2026, 8), (2026, 7)}
        )
        # Clock says candidate = 2026-08 (Sep 10+); fixtures confirm it exists.
        fetcher.fetch_and_build(skip_demand=True, today=date(2026, 9, 10))
        gen_path = processed / "generation_info.parquet"
        grid_path = processed / "grid_capacity.parquet"
        assert gen_path.exists() and grid_path.exists()
        gen_v = sv.read_vintage(gen_path)
        grid_v = sv.read_vintage(grid_path)
        assert gen_v["registration_snapshot"] == "2026-08-01"
        assert gen_v["archive_month"] == "2026-08"
        assert gen_v["row_count"] == 2
        assert gen_v["pipeline_workbook"] is None
        assert grid_v["registration_snapshot"] == "2026-08-01"
        grid = pd.read_parquet(grid_path)
        assert grid["capacity_mw"].sum() == 300.0
        # No private/absolute paths in public artifacts
        blob = json.dumps(gen_v) + json.dumps(grid_v)
        assert "/Users" not in blob and "data/au_dc" not in blob

    def test_fixed_clock_selects_newest_available_and_is_deterministic(self, monkeypatch, tmp_path):
        # Only 2026-07 published even though today would allow 2026-08:
        # resolution must land on 2026-07 (never the old 2026-01 default).
        processed = self._install(monkeypatch, tmp_path, available_months={(2026, 7)})
        fetcher.fetch_and_build(skip_demand=True, today=date(2026, 9, 10))
        gen_v = sv.read_vintage(processed / "generation_info.parquet")
        assert gen_v["archive_month"] == "2026-07"
        assert gen_v["registration_snapshot"] == "2026-07-01"
        assert gen_v["archive_month"] != "2026-01"  # regression: never January again

        # Determinism: an identical second run rewrites nothing.
        gen_bytes = (processed / "generation_info.parquet").read_bytes()
        grid_bytes = (processed / "grid_capacity.parquet").read_bytes()
        sc = (processed / "generation_info.parquet.vintage.json").read_bytes()
        fetcher.fetch_and_build(skip_demand=True, today=date(2026, 9, 10))
        assert (processed / "generation_info.parquet").read_bytes() == gen_bytes
        assert (processed / "grid_capacity.parquet").read_bytes() == grid_bytes
        assert (processed / "generation_info.parquet.vintage.json").read_bytes() == sc

    def test_no_published_archive_fails_closed(self, monkeypatch, tmp_path):
        self._install(monkeypatch, tmp_path, available_months=set())
        with pytest.raises(RuntimeError):
            fetcher.fetch_and_build(skip_demand=True, today=date(2026, 9, 10))


# ────────────────────────────────────────────────────────────────────────────
# 7. Workbook edition recording
# ────────────────────────────────────────────────────────────────────────────
class TestWorkbookEdition:
    def test_edition_meta_records_file_identity(self, tmp_path):
        src = tmp_path / "nem-generation-information-latest.xlsx"
        src.write_bytes(b"fake workbook bytes")
        meta = fetcher._file_edition_meta(src)
        assert meta["file"] == src.name
        assert meta["sha256_prefix"]
        assert meta["file_mtime_utc"]

    def test_edition_meta_absent_file(self, tmp_path):
        assert fetcher._file_edition_meta(tmp_path / "missing.xlsx") is None

    def test_load_aemo_pipeline_without_workbook(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fetcher, "RAW_DIR", tmp_path)
        df, meta = fetcher.load_aemo_pipeline()
        assert df.empty
        assert meta is None


# ────────────────────────────────────────────────────────────────────────────
# 8. App caption helpers (graceful vintage labels)
# ────────────────────────────────────────────────────────────────────────────
class TestAppCaptions:
    def test_registration_caption_prefixes_snapshot(self):
        note = "AEMO/NEM view only."
        out = av.registration_caption(
            {"registration_snapshot": "2026-08-01", "archive_month": "2026-08"}, note
        )
        assert out.startswith("Registration roster as of 2026-08-01 (AEMO MMS monthly archive 2026-08). ")
        assert out.endswith(note)

    def test_registration_caption_fallback_without_vintage(self):
        note = "AEMO/NEM view only."
        assert av.registration_caption({}, note) == note

    def test_demand_caption_states_actuals_and_through(self):
        out = av.demand_caption({"archive_month": "2026-07"}, "2026-07")
        assert "historical actuals" in out
        assert "never projects" in out
        assert out.endswith("Series extends through 2026-07 (AEMO MMS monthly archive 2026-07).")

    def test_demand_caption_without_vintage_still_dates_series(self):
        out = av.demand_caption({}, "2026-03")
        assert out.endswith("Series extends through 2026-03.")
        assert av.demand_caption({}, None).endswith("never projects future demand.")

    def test_app_reader_matches_etl_writer(self, tmp_path):
        out = tmp_path / "grid_capacity.parquet"
        sv.write_parquet_with_vintage(
            pd.DataFrame({"a": [1]}), out,
            {"archive_month": "2026-08", "registration_snapshot": "2026-08-01"},
        )
        assert av.read_vintage(out) == sv.read_vintage(out)
        assert av.vintage_path_for(out) == sv.vintage_path_for(out)
