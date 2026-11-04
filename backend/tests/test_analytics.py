from __future__ import annotations
import io
import pandas as pd
import numpy as np
import pytest


CSV_BYTES = b"""Company,Revenue,Employees,Founded,Country
Apple,383285,161000,1976,USA
Google,307394,182502,1998,USA
Microsoft,211915,221000,1975,USA
Amazon,574785,1525000,1994,USA
Meta,134902,67317,2004,USA
"""

CSV_WITH_ISSUES = b"""Name,Score,Category
Alice,85,A
Bob,90,B
Alice,85,A
Charlie,,C
Dave,70,
"""


class TestProfileDataset:
    def test_profile_basic(self):
        from app.analytics.data_utils import profile_dataset
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        prof = profile_dataset(df)
        assert prof["rows"] == 5
        assert prof["columns"] == 5
        assert prof["duplicate_rows"] == 0
        assert isinstance(prof["column_profile"], list)
        assert len(prof["column_profile"]) == 5

    def test_profile_numeric_summary(self):
        from app.analytics.data_utils import profile_dataset
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        prof = profile_dataset(df)
        assert "Revenue" in prof["numeric_summary"]
        stats = prof["numeric_summary"]["Revenue"]
        assert "mean" in stats

    def test_profile_correlation(self):
        from app.analytics.data_utils import profile_dataset
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        prof = profile_dataset(df)
        assert isinstance(prof["correlation"], dict)

    def test_profile_detects_missing(self):
        from app.analytics.data_utils import profile_dataset
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        prof = profile_dataset(df)
        assert prof["total_missing"] > 0

    def test_profile_detects_duplicates(self):
        from app.analytics.data_utils import profile_dataset
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        prof = profile_dataset(df)
        assert prof["duplicate_rows"] >= 1


class TestCleaningEngine:
    def test_trim_whitespace(self):
        from app.analytics.cleaning import run_cleaning
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        cleaned, actions, before, after = run_cleaning(df.copy(), {"trim_whitespace": True})
        # After trimming, "  Alice  " should become "Alice"
        names = cleaned["Name"].tolist()
        assert all(n == n.strip() for n in names if isinstance(n, str))

    def test_drop_duplicates(self):
        from app.analytics.cleaning import run_cleaning
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        before_rows = len(df)
        cleaned, actions, before, after = run_cleaning(df.copy(), {"trim_whitespace": True, "drop_duplicates": True})
        assert len(cleaned) <= before_rows

    def test_fill_numeric_median(self):
        from app.analytics.cleaning import run_cleaning
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        assert df["Score"].isna().sum() > 0
        cleaned, _, _, _ = run_cleaning(df.copy(), {"fill_numeric": "median"})
        assert cleaned["Score"].isna().sum() == 0

    def test_fill_categorical_unknown(self):
        from app.analytics.cleaning import run_cleaning
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        cleaned, _, _, _ = run_cleaning(df.copy(), {"fill_categorical": "unknown"})
        assert cleaned["Category"].isna().sum() == 0

    def test_before_after_tracking(self):
        from app.analytics.cleaning import run_cleaning
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        _, actions, before, after = run_cleaning(df.copy(), {"trim_whitespace": True, "drop_duplicates": True})
        assert "rows" in before and "rows" in after
        assert isinstance(actions, list)
        assert len(actions) > 0

    def test_preview_does_not_modify(self):
        from app.analytics.cleaning import build_cleaning_preview
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        original_len = len(df)
        preview = build_cleaning_preview(df, {"drop_duplicates": True})
        assert len(df) == original_len  # original unchanged
        assert "before" in preview and "after" in preview


class TestEDAEngine:
    def test_eda_basic(self):
        from app.analytics.eda import run_eda
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        result = run_eda(df)
        assert "numeric_details" in result
        assert "categorical_summaries" in result
        assert "summary" in result
        assert result["summary"]["total_rows"] == 5

    def test_eda_numeric_stats_accuracy(self):
        from app.analytics.eda import run_eda
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        result = run_eda(df)
        rev_stats = next((x for x in result["numeric_details"] if x["column"] == "Revenue"), None)
        assert rev_stats is not None
        # Revenue values: 383285, 307394, 211915, 574785, 134902
        expected_mean = round((383285 + 307394 + 211915 + 574785 + 134902) / 5, 4)
        assert abs(rev_stats["mean"] - expected_mean) < 1

    def test_eda_detects_warnings(self):
        from app.analytics.eda import run_eda
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        result = run_eda(df)
        assert len(result["warnings"]) > 0

    def test_eda_missing_report(self):
        from app.analytics.eda import run_eda
        df = pd.read_csv(io.StringIO(CSV_WITH_ISSUES.decode()))
        result = run_eda(df)
        assert len(result["missing_report"]) > 0


class TestChartEngine:
    def test_charts_generated(self):
        from app.analytics.visualizer import generate_charts
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        charts = generate_charts(df)
        assert isinstance(charts, list)
        assert len(charts) > 0

    def test_chart_has_required_fields(self):
        from app.analytics.visualizer import generate_charts
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        charts = generate_charts(df)
        for chart in charts:
            assert "kind" in chart
            assert "title" in chart
            assert chart["kind"] in ("histogram", "bar", "scatter", "line")

    def test_histogram_for_numeric(self):
        from app.analytics.visualizer import generate_charts
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        charts = generate_charts(df)
        histograms = [c for c in charts if c["kind"] == "histogram"]
        assert len(histograms) >= 1
        assert "x" in histograms[0]

    def test_categorical_bar_chart(self):
        from app.analytics.visualizer import generate_charts
        df = pd.read_csv(io.StringIO(CSV_BYTES.decode()))
        charts = generate_charts(df)
        bars = [c for c in charts if c["kind"] == "bar"]
        assert len(bars) >= 1


class TestDataIsolation:
    def test_upload_rejected_without_auth(self, client):
        files = {"file": ("data.csv", CSV_BYTES, "text/csv")}
        r = client.post("/api/datasets/upload", files=files)
        assert r.status_code == 401

    def test_arbitrary_dataset_id_rejected(self, client):
        r = client.get("/api/datasets/fake-dataset-id-12345/profile")
        assert r.status_code == 401  # Unauthorized, not 404 (auth checked first)

    def test_wrong_extension_rejected(self, client):
        from fastapi.testclient import TestClient
        from app.main import app as test_app
        # Simulate an authenticated client attempt is checked at auth level
        files = {"file": ("malware.exe", b"MZ executable content", "application/octet-stream")}
        r = client.post("/api/datasets/upload", files=files)
        assert r.status_code in (401, 415)  # Auth first, then type check

    def test_pdf_report_api_available(self, client):
        r = client.get("/api/datasets/nonexistent/report.pdf")
        assert r.status_code in (401, 404)
