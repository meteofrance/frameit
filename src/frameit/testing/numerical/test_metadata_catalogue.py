"""Exercise bundled bytes and the disposable cache without using model inputs."""

import hashlib
import json
import lzma
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from importlib.resources import files

import pytest

from frameit.core import metadata_catalogue as catalogue_module


def test_packaged_release_preserves_records_and_reuses_read_only_cache(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    resources = files("frameit") / "catalogue"
    release = "frameit_metadata_catalogue-0.2.0"
    manifest = json.loads((resources / (release + ".manifest.json")).read_bytes())
    compressed = resources / (release + ".jsonl.xz")
    artifact = manifest["artifact"]
    with compressed.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == artifact["sha256"]
    with compressed.open("rb") as stream, lzma.open(stream, "rb") as body:
        whole = hashlib.sha256(body.readline())
        content = hashlib.sha256()
        examples = {}
        for line in body:
            whole.update(line)
            content.update(line)
            if line.startswith(b'{"completion":') and b'"id":10546,' in line:
                examples[10546] = line.decode()
            if b'"id":33200,' in line:
                examples[33200] = line.decode()
        assert whole.hexdigest() == artifact["uncompressed_sha256"]
        assert content.hexdigest() == artifact["content_sha256"]
    key = ("mesonh", "6.0.0", "THT", "mesonh_netcdf_variable")
    with catalogue_module.open_catalogue() as catalogue:
        assert catalogue.header["counts"] == manifest["counts"]
        assert catalogue.header["content_sha256"] == artifact["content_sha256"]
        by_type = catalogue.connection.execute("SELECT type, count(*) FROM records GROUP BY type")
        assert dict(by_type) == manifest["counts"]
        assert sum(manifest["counts"].values()) == 56_685
        assert set(examples) == {10546, 33200}
        for record_id, complete_line in examples.items():
            assert catalogue.connection.execute(
                "SELECT json FROM records WHERE id=?", (record_id,)).fetchone() == (complete_line,)
        assert [r["id"] for r in catalogue.lookup(*key)] == list(range(10540, 10548))
        assert not catalogue.lookup("mesonh", "6.0.0", "tht", key[-1])
        assert not catalogue.lookup("mesonh", "6.0.0", "THT", "netcdf_variable_name")
        assert catalogue.connection.execute("PRAGMA query_only").fetchone() == (1,)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            catalogue.connection.execute("DELETE FROM records")
        plan = catalogue.connection.execute(
            "EXPLAIN QUERY PLAN SELECT id, json FROM records WHERE type='field' "
            "AND name_kind='exact' AND producer=? AND version=? AND name=? AND namespace=? "
            "ORDER BY id", key,
        ).fetchall()
        assert any("USING INDEX field_lookup" in detail for _, _, _, detail in plan)
    cache, = tmp_path.rglob("*.sqlite3")
    before = cache.stat()
    with catalogue_module.open_catalogue() as catalogue:
        assert [r["id"] for r in catalogue.lookup(*key[:3])] == list(range(10540, 10548))
    assert (cache.stat().st_ino, cache.stat().st_mtime_ns) == (before.st_ino, before.st_mtime_ns)

    cache.write_bytes(b"not a usable SQLite index")
    with catalogue_module.open_catalogue() as catalogue:
        assert [r["completion"]["values"]["units"] for r in catalogue.lookup(*key)
                if r["completion"]["candidate"]] == ["K"]
    assert list(tmp_path.rglob("*.sqlite3")) == [cache]


def _mini_release(records, *, version=2, content=None, whole=None):
    body = b"".join(json.dumps(row).encode() + b"\n" for row in records)
    counts = {"change": len(records)}
    header = {
        "type": "catalogue", "format": "frameit.metadata.catalogue", "format_version": version,
        "catalogue_version": "0.2.0", "previous_version": "0.1.0", "cf_table_version": "95",
        "date": "2026-11-25", "record_ids": "version_scoped", "unknown_values": "not_imputed",
        "content_sha256": content or hashlib.sha256(body).hexdigest(), "counts": counts,
        "completion_attributes": ["units", "long_name", "standard_name"],
        "completeness": "bounded_source_audit",
    }
    raw = json.dumps(header).encode() + b"\n" + body
    compressed = lzma.compress(raw)
    return {
        "manifest_version": 1, "format": header["format"], "format_version": version,
        "catalogue_version": "0.2.0", "previous_catalogue_version": "0.1.0",
        "date": header["date"], "completeness": header["completeness"],
        "cf_table": {"version": "95"},
        "counts": counts, "body_records": len(records),
        "completion": {"allowed_attributes": header["completion_attributes"]},
        "artifact": {
            "bytes": len(compressed), "sha256": hashlib.sha256(compressed).hexdigest(),
            "uncompressed_bytes": len(raw),
            "uncompressed_sha256": whole or hashlib.sha256(raw).hexdigest(),
            "content_sha256": header["content_sha256"],
        },
    }, compressed, "synthetic-test-manifest"


@pytest.mark.parametrize(("rows", "options", "message"), [
    ([{"id": 1, "type": "change"}, {"id": 1, "type": "change"}], {}, "UNIQUE"),
    ([{"id": True, "type": "change"}], {}, "integer"),
    ([{"id": 1, "type": "unrecognized"}], {}, "record type"),
    ([{"id": 1, "type": "change"}], {"version": 9}, "format"),
    ([{"id": 1, "type": "change"}], {"content": "0" * 64}, "body"),
    ([{"id": 1, "type": "change"}], {"whole": "0" * 64}, "uncompressed"),
])
def test_rejects_invalid_release_before_any_cache_is_published(
    tmp_path, monkeypatch, rows, options, message,
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    release = _mini_release(rows, **options)
    monkeypatch.setattr(catalogue_module, "_load_release", lambda: release)
    with pytest.raises(catalogue_module.CatalogueError, match=message):
        with catalogue_module.open_catalogue():
            pytest.fail("A malformed release must not be usable")
    assert not [p for p in tmp_path.rglob("*") if p.is_file()]


def test_concurrent_readers_only_see_completed_snapshots(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    release = _mini_release([{"id": 1, "type": "change", "future": {"nested": ["unchanged"]}}])
    monkeypatch.setattr(catalogue_module, "_load_release", lambda: release)

    def read():
        with catalogue_module.open_catalogue() as catalogue:
            row, = catalogue.connection.execute("SELECT json FROM records WHERE id=1").fetchone()
            return json.loads(row)["future"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: read(), range(4))) == [{"nested": ["unchanged"]}] * 4
    assert len([p for p in tmp_path.rglob("*") if p.is_file()]) == 1


def test_bad_compressed_checksum_cannot_reuse_any_index(tmp_path, monkeypatch):
    name = "frameit_metadata_catalogue-0.2.0"
    original = files("frameit") / "catalogue"
    package = tmp_path / "package"
    bundle = package / "catalogue"
    bundle.mkdir(parents=True)
    (bundle / (name + ".manifest.json")).write_bytes(
        (original / (name + ".manifest.json")).read_bytes())
    asset = name + ".jsonl.xz"
    compressed = (original / asset).read_bytes()
    (bundle / asset).write_bytes(compressed[:-1] + bytes([compressed[-1] ^ 1]))
    monkeypatch.setattr(catalogue_module, "files", lambda _: package)
    cache = tmp_path / "cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    with pytest.raises(catalogue_module.CatalogueError, match="compressed catalogue checksum"):
        with catalogue_module.open_catalogue():
            pytest.fail("Corrupted bundle must not be queried")
    assert not cache.exists()
