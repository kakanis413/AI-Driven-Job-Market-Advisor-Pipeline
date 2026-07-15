import pytest

from data_pipeline import load_to_gcs, sync_to_bigquery


def test_load_to_gcs_not_yet_implemented():
    """Sprint 2 work — this pipeline isn't wired in yet. This test just
    documents that intentionally. Replace with real coverage once
    load_to_gcs is implemented in Sprint 2."""
    with pytest.raises(NotImplementedError):
        load_to_gcs()


def test_sync_to_bigquery_not_yet_implemented():
    with pytest.raises(NotImplementedError):
        sync_to_bigquery()