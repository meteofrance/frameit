"""Approved starter requests: minimal selections, comments, and safe generation."""

import shlex
import subprocess
import sys

import pytest
import xarray as xr
import yaml

from frameit.cli import _build_parser, main
from frameit.core.configuration import resolve_schema, write_template


B = set("schema_version model run.name input.directory input.pattern input.format "
        "tracking.method domain.width_km.x domain.width_km.y polar.enabled "
        "output.directory output.overwrite".split())
F = {"tracking.fixed_box.center.latitude", "tracking.fixed_box.center.longitude"}
A = {"input.wind_pairs", "variables.surface.names", "output.cartesian.horizontal_vectors"}
N = {"variables.deptht.names", "variables.deptht.levels.indices"}
C = {"variables.s_rho.names", "variables.s_rho.levels.indices", "variables.surface.names"}
K = (B - {"input.directory", "input.pattern", "input.format"}
     | {"input.time_alignment", "tracking.source"})

NAMED = {
    "arome-pressure-wind": ("arome", "*.grib", "grib", 500, B | A,
                            ("source wind basis", "pressure", "velocity")),
    "mesonh-pressure-wind": ("mesonh", "*.nc", "netcdf", 500, B | A,
                             ("UM10/VM10", "000", "source wind basis")),
    "arome-fixed-scalar": ("arome", "first-run.nc", "netcdf", 4,
                            B | F | {"variables.surface.names"},
                            ("instructional", "not an AROME producer file", "zero", "missing")),
    "nemo-native": ("nemo", "*.nc", "netcdf", 100, B | F | N,
                    ("potential temperature", "zero-based stored index", "depth", "native")),
    "croco-native": ("croco", "*_his.nc", "netcdf", 100, B | F | C,
                     ("Vtransform=2", "sigma", "metres", "masks")),
    "arome-nemo": ("arome", None, None, 100, K | F,
                   ("independent grids", "masks", "means", "snapshots", "exact")),
    "mesonh-croco": ("mesonh", None, None, 100, K | F,
                     ("FRAC_SEA", "999", "units", "sigma", "independent")),
}

COMMANDS = [
    (name, name, None) for name in NAMED
] + [
    ("arome", "arome-pressure-wind", "pressure_wind"),
    ("arome --tracking pressure_wind", "arome-pressure-wind", "pressure_wind"),
    ("mesonh", "mesonh-pressure-wind", "pressure_wind"),
    ("mesonh --tracking pressure_wind", "mesonh-pressure-wind", "pressure_wind"),
    ("arome --tracking fixed_box", "arome-fixed-scalar", "fixed_box"),
    ("mesonh --tracking fixed_box", "mesonh-fixed-scalar", "fixed_box"),
    ("nemo", "nemo-native", "fixed_box"), ("croco", "croco-native", "fixed_box"),
    ("nemo --tracking fixed_box", "nemo-native", "fixed_box"),
    ("croco --tracking fixed_box", "croco-native", "fixed_box"),
    ("arome --coupling nemo", "arome-nemo", "fixed_box"),
    ("arome --coupling nemo --tracking fixed_box", "arome-nemo", "fixed_box"),
    ("mesonh --coupling croco", "mesonh-croco", "fixed_box"),
    ("mesonh --coupling croco --tracking fixed_box", "mesonh-croco", "fixed_box"),
    ("arome --tracking prescribed_track", "arome-fixed-scalar", "prescribed_track"),
    ("mesonh --tracking prescribed_track", "mesonh-fixed-scalar", "prescribed_track"),
    ("nemo --tracking prescribed_track", "nemo-native", "prescribed_track"),
    ("croco --tracking prescribed_track", "croco-native", "prescribed_track"),
    ("arome --tracking pressure_centroid", "arome-pressure-wind", "pressure_centroid"),
    ("mesonh --tracking pressure_centroid", "mesonh-pressure-wind", "pressure_centroid"),
    ("arome --coupling nemo --tracking prescribed_track", "arome-nemo", "prescribed_track"),
    ("mesonh --coupling croco --tracking prescribed_track", "mesonh-croco", "prescribed_track"),
    ("mesonh --coupling croco --tracking pressure_wind", "mesonh-croco", "pressure_wind"),
]


def leaves(value, prefix=""):
    return set().union(*(leaves(v, f"{prefix}.{k}" if prefix else k) if isinstance(v, dict)
                         else {f"{prefix}.{k}" if prefix else k} for k, v in value.items()))


@pytest.mark.parametrize("command,workflow,method", COMMANDS, ids=[c[0] for c in COMMANDS])
def test_every_advertised_command_is_minimal_and_commented(tmp_path, monkeypatch, command, workflow, method):
    from frameit.io import loader

    def forbidden(*args, **kwargs):
        pytest.fail("Starter generation accessed a dataset or worker")

    monkeypatch.setattr(xr, "open_dataset", forbidden)
    monkeypatch.setattr(loader, "discover_input_files", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    path = tmp_path / "frameit.yaml"
    with pytest.raises(SystemExit) as result:
        main(["init", *shlex.split(command), "--output", str(path)])
    assert result.value.code == 0
    text = path.read_text()
    raw = yaml.safe_load(text)
    resolve_schema(raw, base_dir=tmp_path)
    model, pattern, fmt, width, expected, comments = NAMED.get(workflow, (
        "mesonh", "*.nc", "netcdf", 100, B | F | {"variables.surface.names"}, ("MSLP",)))
    expected = set(expected)
    method = method or ("pressure_wind" if workflow.endswith("pressure-wind") else "fixed_box")
    if method != "fixed_box":
        expected -= F
    if method == "prescribed_track":
        expected.add("tracking.prescribed_track.file")
        assert raw["tracking"]["prescribed_track"]["file"] == "./track.nc"
        assert "exact" in text.lower() and "track" in text.lower()
    if pattern is None:
        assert raw["tracking"]["source"] == "atmosphere"
        assert raw["input"]["time_alignment"] == "common"
        assert set(raw["input"]["sources"]) == {"atmosphere", "ocean"}
        for source in ("atmosphere", "ocean"):
            expected |= {f"input.sources.{source}.{p}" for p in (
                "model", "input.directory", "input.pattern", "input.format")}
        atmosphere = raw["input"]["sources"]["atmosphere"]
        ocean = raw["input"]["sources"]["ocean"]
        expected.add("input.sources.atmosphere.variables.surface.names")
        if model == "arome":
            expected |= {f"input.sources.ocean.{p}" for p in N}
            assert atmosphere["variables"] == {"surface": {"names": ["prmsl"]}}
            assert ocean["variables"] == {"deptht": {"names": ["votemper"], "levels": {"indices": [0]}}}
        else:
            expected |= {"input.sources.atmosphere.input.netcdf.surfex_fields",
                         "input.sources.ocean.variables.s_rho.names",
                         "input.sources.ocean.variables.s_rho.levels.indices"}
            assert atmosphere["input"]["netcdf"]["surfex_fields"] == ["SST", "SSS"]
            assert ocean["variables"] == {"s_rho": {"names": ["temp", "salt"], "levels": {"indices": [0]}}}
            fields = ["SST", "SSS"]
            if method == "pressure_wind":
                fields += ["UM10", "VM10", "MSLP"]
                expected |= {"input.sources.atmosphere.input.wind_pairs",
                             "output.cartesian.horizontal_vectors"}
                assert atmosphere["input"]["wind_pairs"] == [
                    {"group": "surface", "u": "UM10", "v": "VM10", "reference_frame": "earth"}]
            assert atmosphere["variables"]["surface"]["names"] == fields
        assert atmosphere["model"] == model
        assert atmosphere["input"]["directory"] == f"./data/{model}"
        assert ocean["input"]["directory"] == f"./data/{ocean['model']}"
    else:
        assert raw["input"]["pattern"] == pattern and raw["input"]["format"] == fmt
        if workflow.endswith("pressure-wind"):
            fields = ["u10", "v10", "prmsl"] if model == "arome" else ["UM10", "VM10", "MSLP"]
            assert raw["variables"] == {"surface": {"names": fields}}
            pairs = [{"group": "surface", "u": fields[0], "v": fields[1], "reference_frame": "earth"}]
            if method == "pressure_centroid":
                pairs.append({"group": "isobaricInhPa" if model == "arome" else "level",
                              "u": "u" if model == "arome" else "UT_ZM",
                              "v": "v" if model == "arome" else "VT_ZM", "reference_frame": "earth"})
                assert "500-km" in text and "bracket" in text.lower() and "ASL" in text
            assert raw["input"]["wind_pairs"] == pairs
        elif model == "arome":
            assert raw["variables"] == {"surface": {"names": ["instructional_scalar"]}}
        elif workflow == "mesonh-fixed-scalar":
            assert raw["variables"] == {"surface": {"names": ["MSLP"]}}
        elif model == "nemo":
            assert raw["variables"] == {"deptht": {"names": ["votemper"], "levels": {"indices": [0]}}}
        else:
            assert raw["variables"] == {"s_rho": {"names": ["temp", "salt"], "levels": {"indices": [0]}},
                                        "surface": {"names": ["zeta"]}}
    assert leaves(raw) == expected
    assert raw["model"] == model and raw["schema_version"] == "2.1"
    assert raw["tracking"]["method"] == method
    assert raw["domain"]["width_km"] == {"x": width, "y": width}
    assert raw["polar"] == {"enabled": False}
    assert raw["output"]["directory"] == "./output" and raw["output"]["overwrite"] is False
    if method == "fixed_box":
        assert raw["tracking"]["fixed_box"]["center"] == {"latitude": -20., "longitude": 60.}
    if "output.cartesian.horizontal_vectors" in expected:
        assert raw["output"]["cartesian"] == {"horizontal_vectors": "earth_centered"}
    for comment in ("relative", "full widths", "polar", *comments):
        assert comment.lower() in "\n".join(line for line in text.splitlines() if line.lstrip().startswith("#")).lower()
    if workflow in NAMED and (method == "fixed_box" or method == "pressure_wind" and "--coupling" not in command):
        assert raw["run"]["name"] == workflow


@pytest.mark.parametrize("named,composed", [
    ("arome-pressure-wind", {"name": "arome"}),
    ("mesonh-pressure-wind", {"name": "mesonh"}),
    ("arome-fixed-scalar", {"name": "arome", "tracking": "fixed_box"}),
    ("nemo-native", {"name": "nemo"}), ("croco-native", {"name": "croco"}),
    ("arome-nemo", {"name": "arome", "coupling": "nemo"}),
    ("mesonh-croco", {"name": "mesonh", "coupling": "croco"}),
])
def test_named_and_composed_are_the_same_request(tmp_path, named, composed):
    a = write_template(named, tmp_path / "a.yaml")
    b = write_template(path=tmp_path / "b.yaml", **composed)
    assert resolve_schema(yaml.safe_load(a.read_text()), base_dir=tmp_path) == resolve_schema(
        yaml.safe_load(b.read_text()), base_dir=tmp_path)


@pytest.mark.parametrize("name,options", [
    *((n, {"tracking": "fixed_box"}) for n in NAMED),
    *((n, {"coupling": "nemo"}) for n in NAMED),
    ("arome", {"coupling": "croco"}), ("mesonh", {"coupling": "nemo"}),
    ("nemo", {"coupling": "arome"}), ("croco", {"coupling": "mesonh"}),
    ("nemo", {"tracking": "pressure_wind"}), ("croco", {"tracking": "pressure_centroid"}),
    ("arome", {"coupling": "nemo", "tracking": "pressure_wind"}),
    ("mesonh", {"coupling": "croco", "tracking": "pressure_centroid"}),
    ("arome", {"tracking": "multifield_vortex"}), ("mesonh", {"tracking": "utrack"}),
    ("arome", {"tracking": "wind_pressure"}), ("unknown", {}), ("../arome", {}),
])
def test_invalid_compositions_never_create_a_file(tmp_path, name, options):
    path = tmp_path / "frameit.yaml"
    with pytest.raises(ValueError):
        write_template(name, path, **options)
    assert not path.exists()


def test_refusal_force_and_no_input_overwrite(tmp_path):
    source = tmp_path / "source.nc"
    source.write_bytes(b"source data")
    path = tmp_path / "frameit.yaml"
    path.write_bytes(b"researcher's configuration")
    with pytest.raises(FileExistsError):
        write_template("arome", path)
    assert path.read_bytes() == b"researcher's configuration"
    write_template("nemo", path, force=True)
    assert yaml.safe_load(path.read_text())["model"] == "nemo"
    path.unlink()
    path.symlink_to(source)
    write_template("arome", path, force=True)
    assert not path.is_symlink() and source.read_bytes() == b"source data"


def test_no_full_starter_but_complete_inspection(tmp_path, capsys):
    with pytest.raises(SystemExit) as result:
        _build_parser().parse_args(["init", "arome", "--full"])
    assert result.value.code == 2
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["init", "--help"])
    help_text = capsys.readouterr().out
    assert "--full" not in help_text and "--coupling" in help_text
    path = write_template("arome", tmp_path / "frameit.yaml")
    with pytest.raises(SystemExit) as result:
        main(["config", "show", str(path)])
    assert result.value.code == 0
    resolved = yaml.safe_load(capsys.readouterr().out)
    assert resolved["tracking"]["pressure_centroid"]["motion"]["solver"] == "aitken"
    assert resolved["output"]["backend"] == "netcdf4"


def test_generation_does_not_import_optional_stacks(tmp_path):
    subprocess.run([sys.executable, "-c", """
import sys
from frameit.core.configuration import write_template
write_template('arome-fixed-scalar', sys.argv[1])
assert not {'cfgrib', 'epygram', 'xesmf', 'esmpy', 'torch', 'zarr'} & sys.modules.keys()
""", str(tmp_path / "frameit.yaml")], check=True)
