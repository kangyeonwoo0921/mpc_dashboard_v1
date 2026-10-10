"""Dataset version records for processed field data (reproducible training inputs).

``dataset_id`` identifies the processed data by what determines it:

    pipeline name + pipeline version + sha256 of every input file + config fingerprint

It deliberately excludes the git commit and library versions, so unrelated commits do not create
a new dataset id; those are recorded as provenance next to it. A model trained later stores the
``dataset_id`` (and the manifest) it was trained on; re-running the pipeline with the listed input
files, config and pipeline version reproduces the same data.
"""

import hashlib
import json
import platform
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

METADATA_KEY = b"greenhouse_mpc.dataset_version"
LIBRARIES = ("numpy", "pandas", "pvlib", "pyarrow", "yaml")


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json_sha256(content):
    text = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inputs_fingerprint(metas):
    """sha256 over the sorted (file name, content sha256) pairs; independent of folder location."""
    return _json_sha256(sorted([meta["file"], meta["sha256"]] for meta in metas))


def git_state(path):
    """(commit, dirty) for the code under ``path``; (None, None) outside a git checkout."""
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True,
                                text=True, check=True, timeout=10).stdout.strip()
        changes = subprocess.run(["git", "status", "--porcelain", "--", "src", "config"], cwd=path,
                                 capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        return commit, bool(changes)
    except (OSError, subprocess.SubprocessError):
        return None, None


def library_versions():
    import importlib
    versions = {"python": platform.python_version()}
    for name in LIBRARIES:
        try:
            versions[name] = getattr(importlib.import_module(name), "__version__", "unknown")
        except ImportError:
            versions[name] = None
    return versions


def build_version(pipeline, pipeline_version, metas, config_sha256, code_dir):
    inputs_sha = inputs_fingerprint(metas)
    dataset_id = _json_sha256({"pipeline": pipeline, "pipeline_version": pipeline_version,
                               "inputs_sha256": inputs_sha, "config_sha256": config_sha256})[:16]
    commit, dirty = git_state(code_dir)
    return {
        "dataset_id": dataset_id,
        "pipeline": pipeline,
        "pipeline_version": pipeline_version,
        "config_sha256": config_sha256,
        "inputs_sha256": inputs_sha,
        "inputs": [{"file": m["file"], "sha256": m["sha256"], "data_rows": m["data_rows"]}
                   for m in sorted(metas, key=lambda m: m["file"])],
        "provenance": {"git_commit": commit, "git_dirty": dirty, "libraries": library_versions()},
    }


def write_parquet(frame, path, version):
    """Write ``frame`` with the dataset version embedded in the Parquet schema metadata."""
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[METADATA_KEY] = json.dumps({k: version[k] for k in ("dataset_id", "pipeline", "pipeline_version",
                                                                  "config_sha256", "inputs_sha256")},
                                        sort_keys=True).encode("utf-8")
    pq.write_table(table.replace_schema_metadata(metadata), path)


def read_parquet_version(path):
    """The embedded dataset version of a Parquet file written by ``write_parquet`` (None if absent)."""
    metadata = pq.read_schema(path).metadata or {}
    raw = metadata.get(METADATA_KEY)
    return None if raw is None else json.loads(raw)
