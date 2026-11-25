import csv
import hashlib
import importlib.util

import pytest

from frameit.diagnostics.contracts import Centre, DiagnosticResult, Metric

HEADER = (
    "idswi;nom_cyc;dat;typa;lat;lon;precision;t;ci;ventmax;rafale;pression;rayon_ventmax;"
    "extension_28kt_ne;extension_28kt_se;extension_28kt_so;extension_28kt_no;"
    "extension_34kt_ne;extension_34kt_se;extension_34kt_so;extension_34kt_no;"
    "extension_48kt_ne;extension_48kt_se;extension_48kt_so;extension_48kt_no;"
    "extension_64kt_ne;extension_64kt_se;extension_64kt_so;extension_64kt_no"
).split(";")


def qualified(value, *, reasons=()):
    return Metric(value=value, comparability="qualified", reasons=reasons)


def example_row():
    return DiagnosticResult(
        Centre("2000-01-01T00:00:00.000000000", -20.0, 181.5),
        qualified(35.5 * 1852 / 3600),
        qualified(98550.0),
        Metric(value=44, comparability="model_native_proxy"),
        qualified(400.0),
        (qualified(1.0), qualified(0.0, reasons=("threshold_not_reached",))) + (Metric(),) * 14,
    )


def test_profile_order_units_rounding():
    assert importlib.util.find_spec("frameit.diagnostics.rsmc") is not None
    from frameit.diagnostics import rsmc

    result = rsmc.flag_projection_resolution(example_row())
    row = rsmc.project_row(result, reference=None)
    assert list(rsmc.COLUMNS) == list(row) == HEADER
    assert row["ventmax"] == 36 and row["pression"] == 986
    assert row["lon"] == -178.5 and row["dat"] == "2000-01-01 00:00:00"
    assert row["rafale"] is None
    assert row["precision"] is row["ci"] is row["idswi"] is None
    assert row["rayon_ventmax"] is None and row["extension_28kt_ne"] is None
    assert row["extension_28kt_se"] == 0
    assert result.rmw.reasons == ("below_export_resolution",) and result.rmw.value == 400
    assert rsmc.synoptic_date("2000-01-01T00:00:00.000000001") is None
    assert rsmc.synoptic_date("2000-01-01T01:00:00.000000000") is None


def test_reference_exact_join(tmp_path):
    assert importlib.util.find_spec("frameit.diagnostics.rsmc") is not None
    from frameit.diagnostics import rsmc

    path = tmp_path / "agency.csv"
    row = {
        "idswi": "02SWI2000",
        "nom_cyc": "Example",
        "dat": "2000-01-01 00:00:00",
        "typa": "producer_category_not_in_pdf",
        "ci": "75",
        "lat": "-20",
        "lon": "-178.5",
        "ventmax": "35",
        "pression": "985",
        "extension_28kt_ne": "",
    }
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER, delimiter=";")
        writer.writeheader()
        writer.writerow(row)
    times = (example_row().centre.time,)
    reference = rsmc.read_reference(path, idswi="02SWI2000", times=times)
    assert reference.facts["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    diff = rsmc.comparison_row(example_row(), reference=reference)
    assert diff["match_status"] == "matched"
    assert diff["observed_typa"] == "producer_category_not_in_pdf"
    assert diff["observed_ci"] == 75
    assert diff["difference_ventmax"] == pytest.approx(0.5)
    assert diff["track_separation_km"] == 0
    assert diff["difference_extension_28kt_ne"] is None
    with path.open("a", encoding="utf-8", newline="") as stream:
        csv.DictWriter(stream, fieldnames=HEADER, delimiter=";").writerow(row)
    with pytest.raises(ValueError, match="Duplicate"):
        rsmc.read_reference(path, idswi="02SWI2000", times=times)
