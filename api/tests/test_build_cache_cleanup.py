import pytest

from scripts.prune_ui_build_cache import MARKER, cache_bytes, select_records


def record(identifier, size, created, **overrides):
    return dict(ID=identifier, Size=size, CreatedAt=created, Description=MARKER,
                Reclaimable=True, Shared=False) | overrides


def test_cache_selection_keeps_recent_builds_and_excludes_other_sites_and_images():
    records = [record('old', '3GB', '2026-10-13'), record('new', '3GB', '2026-10-15'),
               record('other', '50GB', '2026-10-12', Description='npm run build'),
               record('image', '50GB', '2026-10-12', Shared=True),
               record('busy', '50GB', '2026-10-12', Reclaimable=False)]
    assert select_records(records, 4_000_000_000) == ['old']
    assert select_records(records, 8_000_000_000) == []


def test_unknown_size_aborts_selection_instead_of_over_pruning():
    with pytest.raises(ValueError):
        select_records([record('unknown', 'unknown', '2026-10-13')], 1)


def test_size_units_use_docker_decimal_bytes():
    assert cache_bytes('2.214GB') == 2_214_000_000
    assert cache_bytes('8.192kB') == 8192
