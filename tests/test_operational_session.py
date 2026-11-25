from __future__ import annotations

import os

from agriflight.operational.session import CACHE_KEY, clear, get_or_load
from operational_fixtures import build_package


def test_cache_reused_for_same_package(tmp_path):
    pkg = build_package(tmp_path)
    store: dict = {}
    first = get_or_load(store, pkg)
    assert get_or_load(store, pkg) is first


def test_cache_reloads_when_package_changes(tmp_path):
    pkg = build_package(tmp_path)
    store: dict = {}
    first = get_or_load(store, pkg)
    path = pkg / "data" / "clients.csv"
    path.write_text(path.read_text(encoding="utf-8") + "CLI_T3,Client 903\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    second = get_or_load(store, pkg)
    assert second is not first
    assert len(second.dataset.tables["clients"]) == 3


def test_cache_switches_between_packages_without_stale_results(tmp_path):
    pkg_a = build_package(tmp_path / "a")

    def relabel(rows, _cols):
        rows["clients"][0]["client_name"] = "Client 777"

    pkg_b = build_package(tmp_path / "b", relabel)
    store: dict = {}
    a = get_or_load(store, pkg_a)
    b = get_or_load(store, pkg_b)
    assert a.dataset.tables["clients"]["client_name"].iloc[0] == "Client 901"
    assert b.dataset.tables["clients"]["client_name"].iloc[0] == "Client 777"


def test_clear_removes_private_data_from_store(tmp_path):
    store: dict = {}
    get_or_load(store, build_package(tmp_path))
    clear(store)
    assert CACHE_KEY not in store
