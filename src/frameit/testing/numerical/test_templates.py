"""Approved starter requests: minimal selections, comments, and safe generation."""

import shlex
import subprocess
import sys

import pytest
import xarray as xr
import yaml

from frameit.cli import _build_parser, main
from frameit.core.configuration import resolve_schema, write_template


B = set("schema_version run.name region.width_km.x region.width_km.y "
        "products.model_grid output.directory output.overwrite".split())
F = {"region.center.latitude", "region.center.longitude"}
A = {"sources.atmosphere.wind_pairs", "sources.atmosphere.variables.2d",
     "sources.atmosphere.transforms"}
N = {"sources.ocean.variables.3d", "sources.ocean.variables.levels.indices"}
C = N | {"sources.ocean.variables.2d"}
K = B | {"region.sources_coupling_time_association"}

NAMED = {
    "arome-pressure-wind": ("arome", "*.grib", "grib", 500, B | A,
                            ("source wind basis", "pressure", "velocity")),
    "mesonh-pressure-wind": ("mesonh", "*.nc", "netcdf", 500, B | A,
                             ("UM10/VM10", "000", "source wind basis")),
    "arome-fixed-scalar": ("arome", "first-run.nc", "netcdf", 4,
                            B | F | {"sources.atmosphere.variables.2d"},
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
    ("arome --coupling nemo --tracking pressure_wind", "arome-nemo", "pressure_wind"),
    ("arome --coupling nemo --tracking pressure_centroid", "arome-nemo", "pressure_centroid"),
    ("mesonh --coupling croco --tracking pressure_centroid", "mesonh-croco", "pressure_centroid"),
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
        "mesonh", "*.nc", "netcdf", 100, B | F | {"sources.atmosphere.variables.2d"}, ("MSLP",)))
    expected = set(expected)
    method = method or ("pressure_wind" if workflow.endswith("pressure-wind") else "fixed_box")
    if method != "fixed_box":
        expected -= F
    if method == "prescribed_track":
        expected.add("region.track.file")
        assert raw["region"]["track"]["file"] == "./track.nc"
        assert "exact" in text.lower() and "track" in text.lower()
    if method in {"pressure_wind", "pressure_centroid"}:
        expected.add("region.tracker.method")
        assert raw["region"]["tracker"]["method"] == method
    if pattern is None:
        assert raw["region"]["sources_coupling_time_association"] == "common"
        assert set(raw["sources"]) == {"atmosphere", "ocean"}
        for source in ("atmosphere", "ocean"):
            expected |= {f"sources.{source}.{p}" for p in ("model", "files", "format")}
        atmosphere = raw["sources"]["atmosphere"]
        ocean = raw["sources"]["ocean"]
        expected.add("sources.atmosphere.variables.2d")
        if method in {"pressure_wind", "pressure_centroid"}:
            expected.add("sources.atmosphere.wind_pairs")
            u, v = ("u10", "v10") if model == "arome" else ("UM10", "VM10")
            pairs = [{"u": u, "v": v, "basis": "earth"}]
            if method == "pressure_centroid":
                pairs.append({"u": "u" if model == "arome" else "UT_ZM",
                              "v": "v" if model == "arome" else "VT_ZM", "basis": "earth"})
                assert "500-km" in text and "bracket" in text.lower() and "ASL" in text
                assert "two exact common times" in text
            assert atmosphere["wind_pairs"] == pairs
            assert "wind_pairs" not in ocean
            assert "No polar/shared target, winds" not in text
        if model == "arome":
            expected |= N
            assert atmosphere["variables"] == {"2d": ["prmsl"]}
            assert ocean["variables"] == {"3d": ["votemper"], "levels": {"indices": [0]}}
        else:
            expected |= {"sources.atmosphere.interpretation"} | N
            assert atmosphere["interpretation"] == "mesonh_surfex_sea"
            assert ocean["variables"] == {"3d": ["temp", "salt"], "levels": {"indices": [0]}}
            fields = ["SST", "SSS"]
            if method == "pressure_wind":
                fields += ["UM10", "VM10", "MSLP"]
                expected.add("sources.atmosphere.transforms")
            assert atmosphere["variables"]["2d"] == fields
        assert atmosphere["model"] == model
        assert atmosphere["files"] == f"./data/{model}/{'*.nc' if model == 'arome' else '*diag.nc'}"
        ocean_pattern = "*.nc" if model == "arome" else "*_his.nc"
        assert ocean["files"] == f"./data/{ocean['model']}/{ocean_pattern}"
    else:
        source_name = "atmosphere" if model in {"arome", "mesonh"} else "ocean"
        source = raw["sources"][source_name]
        expected |= {f"sources.{source_name}.{p}" for p in ("model", "files", "format")}
        assert source["files"] == f"./data/{pattern}" and source["format"] == fmt
        assert source["model"] == model
        if workflow.endswith("pressure-wind"):
            fields = ["u10", "v10", "prmsl"] if model == "arome" else ["UM10", "VM10", "MSLP"]
            assert source["variables"] == {"2d": fields}
            pairs = [{"u": fields[0], "v": fields[1], "basis": "earth"}]
            if method == "pressure_centroid":
                pairs.append({"u": "u" if model == "arome" else "UT_ZM",
                              "v": "v" if model == "arome" else "VT_ZM", "basis": "earth"})
                assert "500-km" in text and "bracket" in text.lower() and "ASL" in text
            assert source["wind_pairs"] == pairs
        elif model == "arome":
            assert source["variables"] == {"2d": ["instructional_scalar"]}
        elif workflow == "mesonh-fixed-scalar":
            assert source["variables"] == {"2d": ["MSLP"]}
        elif model == "nemo":
            assert source["variables"] == {"3d": ["votemper"], "levels": {"indices": [0]}}
        else:
            assert source["variables"] == {"3d": ["temp", "salt"], "levels": {"indices": [0]},
                                          "2d": ["zeta"]}
    assert leaves(raw) == expected
    assert type(raw["schema_version"]) is int and raw["schema_version"] == 3
    assert raw["region"]["width_km"] == {"x": width, "y": width}
    assert raw["products"] == {"model_grid": True}
    assert raw["output"]["directory"] == "./output" and raw["output"]["overwrite"] is False
    if method == "fixed_box":
        assert raw["region"]["center"] == {"latitude": -20., "longitude": 60.}
    if "sources.atmosphere.transforms" in expected:
        fields = ["u10", "v10"] if model == "arome" else ["UM10", "VM10"]
        assert raw["sources"]["atmosphere"]["transforms"] == [
            {"fields": fields, "sampling": "mass", "basis": "earth"}]
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
    ("arome-nemo", {"tracking": "pressure_centroid"}),
    ("arome", {"coupling": "nemo", "tracking": "multifield_vortex"}),
    ("mesonh", {"coupling": "croco", "tracking": "utrack"}),
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
    assert yaml.safe_load(path.read_text())["sources"]["ocean"]["model"] == "nemo"
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
    authored = yaml.safe_load(capsys.readouterr().out)
    assert authored == yaml.safe_load(path.read_text())
    resolved = resolve_schema(authored, base_dir=tmp_path)[0]
    assert resolved["region"]["tracker"]["method"] == "pressure_wind"
    assert resolved["output"]["writer"]["engine"] == "netcdf4"


@pytest.mark.parametrize("name,coupling,tracking", [
    ("arome-fixed-scalar", None, None),
    ("arome", "nemo", "pressure_wind"),
    ("arome", "nemo", "pressure_centroid"),
    ("mesonh", "croco", "pressure_centroid"),
])
def test_generation_does_not_import_optional_stacks(tmp_path, name, coupling, tracking):
    subprocess.run([sys.executable, "-c", """
import sys
from frameit.core.configuration import write_template
write_template(sys.argv[2], sys.argv[1],
               coupling=None if sys.argv[3] == 'None' else sys.argv[3],
               tracking=None if sys.argv[4] == 'None' else sys.argv[4])
assert not {'cfgrib', 'epygram', 'xesmf', 'esmpy', 'torch', 'zarr'} & sys.modules.keys()
""", str(tmp_path / "frameit.yaml"), name, str(coupling), str(tracking)], check=True)
