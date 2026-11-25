"""Verified, offline access to FrameIt's release-scoped reference catalogue."""

import hashlib
import io
import json
import lzma
import os
import sqlite3
import tempfile
from collections import Counter
from contextlib import closing, contextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

VERSION = "0.2.0"
CONTENT_SHA256 = "ff7b1e735ff50370addda7c5a4308ff6457d960ab0c50fdd841dcbef598b41ec"
_MANIFEST_SHA256 = "63201541711c7c363f1b06865f6b552587aabd71029fb6fb5c978c11fb15e1b9"
_ARTIFACT = f"frameit_metadata_catalogue-{VERSION}.jsonl.xz"
_FORMAT = "frameit.metadata.catalogue"
_FORMAT_VERSION = 2
_CACHE_SCHEMA = 2
COMPLETION_KEYS = ("units", "long_name", "standard_name")
_TYPES = {
    "attribute", "cf_name", "change", "field", "metadata_key", "metadata_key_census",
    "source", "writer_contract",
}
_EXACT = ("SELECT id, json FROM records WHERE type = 'field' AND name_kind = 'exact'"
          " AND producer = ? AND version = ? AND name = ?")
_RECORDS_DDL = (
    "CREATE TABLE records (id INTEGER NOT NULL UNIQUE, type TEXT NOT NULL,"
    " producer TEXT COLLATE BINARY, version TEXT COLLATE BINARY, name TEXT COLLATE BINARY,"
    " name_kind TEXT, namespace TEXT COLLATE BINARY, json TEXT NOT NULL)"
)
_INDEX_DDL = (
    "CREATE INDEX field_lookup ON records(producer, version, name, namespace)"
    " WHERE type = 'field' AND name_kind = 'exact'"
)


class CatalogueError(ValueError):
    """Optional reference data could not be used."""


@dataclass
class CatalogueIndex:
    connection: sqlite3.Connection
    header: dict

    def lookup(self, producer, version, name, namespace=None):
        query, parameters = _EXACT, (producer, version, name)
        if namespace is not None:
            query += " AND namespace = ?"
            parameters += (namespace,)
        try:
            return [_json(line) for _, line in self.connection.execute(
                query + " ORDER BY id", parameters)]
        except (sqlite3.DatabaseError, ValueError) as exc:
            raise CatalogueError(f"Cannot read the local index: {exc}") from exc


def _reject_constant(value):
    raise CatalogueError(f"Nonfinite JSON constant {value}")


def _json(line):
    result = json.loads(line, parse_constant=_reject_constant)
    if not isinstance(result, dict):
        raise CatalogueError("Expected a JSON object in the catalogue")
    return result


def _load_release():
    bundle = files("frameit") / "catalogue"
    raw = (bundle / f"frameit_metadata_catalogue-{VERSION}.manifest.json").read_bytes()
    manifest_hash = hashlib.sha256(raw).hexdigest()
    if manifest_hash != _MANIFEST_SHA256:
        raise CatalogueError("Packaged catalogue manifest checksum mismatch")
    manifest = _json(raw)
    artifact = manifest["artifact"]
    if artifact["filename"] != _ARTIFACT or artifact["content_sha256"] != CONTENT_SHA256:
        raise CatalogueError("Unexpected packaged catalogue release")
    with (bundle / _ARTIFACT).open("rb") as stream:
        compressed = stream.read(artifact["bytes"] + 1)
    if (len(compressed) != artifact["bytes"]
            or hashlib.sha256(compressed).hexdigest() != artifact["sha256"]):
        raise CatalogueError("Packaged compressed catalogue checksum mismatch")
    return manifest, compressed, manifest_hash


def _read_header(stream, manifest):
    line = stream.readline()
    header = _json(line.decode("utf-8"))
    if not (manifest["manifest_version"] == 1
            and header["type"] == "catalogue" and "id" not in header
            and header["format"] == manifest["format"] == _FORMAT
            and header["format_version"] == manifest["format_version"] == _FORMAT_VERSION):
        raise CatalogueError("Unsupported catalogue format or header")
    expected = {
        "catalogue_version": VERSION,
        "previous_version": manifest["previous_catalogue_version"],
        "date": manifest["date"],
        "cf_table_version": manifest["cf_table"]["version"],
        "content_sha256": manifest["artifact"]["content_sha256"],
        "counts": manifest["counts"],
        "completeness": manifest["completeness"],
        "completion_attributes": list(COMPLETION_KEYS),
        "record_ids": "version_scoped",
        "unknown_values": "not_imputed",
    }
    if (not line.endswith(b"\n") or manifest["catalogue_version"] != VERSION
            or manifest["completion"]["allowed_attributes"] != list(COMPLETION_KEYS)
            or expected["counts"].keys() - _TYPES
            or any(header.get(key) != value for key, value in expected.items())):
        raise CatalogueError("Catalogue header and manifest identity disagree")
    return header, line


def _record_columns(row):
    record_id, kind = row.get("id"), row.get("type")
    if type(record_id) is not int:
        raise CatalogueError("Catalogue record IDs must be integers")
    if not isinstance(kind, str) or kind not in _TYPES:
        raise CatalogueError("Unsupported catalogue record type")
    keys = ("producer", "version", "name", "name_kind", "namespace")
    if kind == "field":
        if (any(not isinstance(row.get(key), str) or not row[key]
                for key in (*keys, "role", "introduced_in"))
                or not isinstance(row.get("source"), dict)):
            raise CatalogueError(f"Invalid catalogue field record {record_id}")
        source = row["source"]
        if any(source.get(key) is not None and not isinstance(source[key], dict)
               for key in ("metadata", "context")):
            raise CatalogueError(f"Invalid source field metadata for record {record_id}")
        completion = row.get("completion")
        if (not isinstance(completion, dict) or type(completion.get("candidate")) is not bool
                or any(not isinstance(completion.get(key), dict)
                       for key in ("values", "requires", "identity", "withheld"))):
            raise CatalogueError(f"Invalid completion contract for record {record_id}")
        values = completion["values"]
        if (values.keys() - set(COMPLETION_KEYS)
                or any(not isinstance(value, str) or not value.strip() for value in values.values())
                or not completion["candidate"] and values):
            raise CatalogueError(f"Invalid completion values for record {record_id}")
    return (record_id, kind, *(row.get(key) if isinstance(row.get(key), str) else None
                               for key in keys))


def _write_cache(path, stream, first_line, manifest, cache_info):
    whole, body = hashlib.sha256(first_line), hashlib.sha256()
    counts, size = Counter(), len(first_line)

    def records():
        nonlocal size
        for line in stream:
            size += len(line)
            whole.update(line)
            body.update(line)
            if not line.endswith(b"\n"):
                raise CatalogueError("Catalogue body records must end in LF")
            text = line.decode("utf-8")
            columns = _record_columns(_json(text))
            counts[columns[1]] += 1
            yield (*columns, text)

    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TABLE cache_info (key TEXT PRIMARY KEY, value TEXT NOT NULL) "
                   "WITHOUT ROWID")
        db.execute(_RECORDS_DDL)
        db.executemany("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?)", records())
        artifact = manifest["artifact"]
        if body.hexdigest() != artifact["content_sha256"]:
            raise CatalogueError("Catalogue body checksum mismatch")
        if size != artifact["uncompressed_bytes"] or whole.hexdigest() != artifact[
            "uncompressed_sha256"
        ]:
            raise CatalogueError("Catalogue uncompressed checksum or size mismatch")
        if counts != manifest["counts"] or counts.total() != manifest["body_records"]:
            raise CatalogueError("Catalogue row counts do not match the manifest")
        db.execute(_INDEX_DDL)
        db.executemany("INSERT INTO cache_info VALUES (?, ?)", cache_info.items())
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise CatalogueError("New catalogue index failed its integrity check")


def _matches_contents(db, content_sha256):
    body = hashlib.sha256()
    # rowid preserves package order even when release-scoped IDs are not sorted.
    for *columns, line in db.execute(
        "SELECT id, type, producer, version, name, name_kind, namespace, CAST(json AS BLOB)"
        " FROM records ORDER BY rowid"
    ):
        if _record_columns(_json(line)) != tuple(columns):
            return False
        body.update(line)
    return body.hexdigest() == content_sha256


def _read_cache(path, cache_info, content_sha256):
    if not path.is_file():
        return None
    db = None
    try:
        db = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True)
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")  # Verify and query the same snapshot.
        if (dict(db.execute("SELECT key, value FROM cache_info")) == cache_info
                and dict(db.execute("SELECT name, sql FROM sqlite_schema "
                                    "WHERE name IN ('records', 'field_lookup')"))
                == {"records": _RECORDS_DDL, "field_lookup": _INDEX_DDL}
                and db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
                and _matches_contents(db, content_sha256)):
            return db
    except (sqlite3.DatabaseError, ValueError):
        pass  # The only recovery is rebuilding from the verified packaged bytes.
    if db is not None:
        db.close()
    return None


def _cache_directory():
    root = Path(os.environ.get("XDG_CACHE_HOME", ""))
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "frameit" / "metadata-catalogue"


def _open_index():
    manifest, compressed, manifest_hash = _load_release()
    with lzma.open(io.BytesIO(compressed), "rb") as stream:
        header, first_line = _read_header(stream, manifest)
        cache_info = {"header": first_line.decode("utf-8"), "manifest_sha256": manifest_hash,
                      "schema": str(_CACHE_SCHEMA)}
        directory = _cache_directory()
        content = header["content_sha256"]
        path = directory / f"{content}-v{_CACHE_SCHEMA}.sqlite3"
        if db := _read_cache(path, cache_info, content):
            return CatalogueIndex(db, header)
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=".building-", suffix=".sqlite3")
        os.close(fd)
        temporary = Path(temporary)
        try:
            _write_cache(temporary, stream, first_line, manifest, cache_info)
            # Replace, never open or update a cache another validator is reading.
            temporary.replace(path)
        except (OSError, sqlite3.OperationalError):
            if db := _read_cache(path, cache_info, content):
                return CatalogueIndex(db, header)
            raise
        finally:
            temporary.unlink(missing_ok=True)
        if db := _read_cache(path, cache_info, content):
            return CatalogueIndex(db, header)
        raise CatalogueError("Cannot reopen the built catalogue index")


@contextmanager
def open_catalogue():
    """Verify the bundled snapshot and open a read-only local index on demand."""
    try:
        index = _open_index()
    except CatalogueError:
        raise
    except OSError as exc:
        raise CatalogueError(exc.strerror or "Cannot read the packaged catalogue") from exc
    except (sqlite3.DatabaseError, ValueError, KeyError, TypeError,
            OverflowError, EOFError, lzma.LZMAError) as exc:
        raise CatalogueError(str(exc)) from exc
    with closing(index.connection):
        yield index
