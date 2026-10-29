"""Small analytical and failure checks for the standalone coupled-output plots.

Run with the plotting dependencies installed:
python -m unittest discover -s example -p test_plot_coupled_outputs.py -v
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import numpy as np
import plot_coupled_outputs as plots
import xarray as xr


def wind_dataset():
    attrs = {"units": "m s-1", "grid_position": "mass_aligned", "wind_reference_frame": "earth"}
    return xr.Dataset(
        {
            "u": xr.DataArray([3.0, np.nan], dims="point", attrs=attrs),
            "v": xr.DataArray([4.0, 4.0], dims="point", attrs=attrs),
        }
    )


def polar_dataset():
    theta = np.arange(4) * np.pi / 2
    return xr.Dataset(
        {"t": (("time", "rr", "theta"), np.ones((2, 2, 4)))},
        coords={
            "time": np.array(["2026-01-01", "2026-01-02"], dtype="datetime64[ns]"),
            "rr": xr.DataArray([0.0, 10.0], dims="rr", attrs={"units": "km"}),
            "theta": theta,
            "latitude": (("time", "rr", "theta"), np.zeros((2, 2, 4))),
            "longitude": (("time", "rr", "theta"), np.ones((2, 2, 4))),
        },
        attrs={
            "common_polar_target_id": "synthetic",
            "theta_convention": "azimuth_clockwise_from_north",
        },
    )


class CoupledPlotTests(unittest.TestCase):
    def tearDown(self):
        plots.plt.close("all")

    def test_collocated_wind_known_solution_and_missing_value(self):
        values = plots.wind_speed(wind_dataset(), "u", "v").values
        self.assertEqual(values[0], 5.0)
        self.assertTrue(np.isnan(values[1]))

    def test_staggered_wind_is_rejected(self):
        ds = wind_dataset()
        ds.u.attrs["grid_position"] = "u_face"
        with self.assertRaisesRegex(ValueError, "collocation"):
            plots.wind_speed(ds, "u", "v")

    def test_grid_relative_wind_is_rejected(self):
        ds = wind_dataset()
        ds.v.attrs["wind_reference_frame"] = "grid"
        with self.assertRaisesRegex(ValueError, "Earth-relative"):
            plots.wind_speed(ds, "u", "v")

    def test_ambiguous_units_are_rejected(self):
        ds = wind_dataset()
        ds.u.attrs["units"] = "knots"
        with self.assertRaisesRegex(ValueError, "expected units"):
            plots.wind_speed(ds, "u", "v")

    def test_wrong_temperature_height_is_rejected(self):
        ds = xr.Dataset(
            {"t2m": (("heightAboveGround", "point"), [[300.0]])},
            coords={"heightAboveGround": [10.0]},
        )
        ds.t2m.attrs["units"] = "K"
        with self.assertRaisesRegex(ValueError, "2 m level"):
            plots.temperature_2m(ds, "t2m")

    def test_equal_angle_harmonic_rms(self):
        theta = np.arange(4) * np.pi / 2
        field = xr.DataArray(2 * np.cos(theta), dims="theta")
        self.assertAlmostEqual(float(plots.complete_ring_mean(field)), 0.0, places=14)
        rms = float(np.sqrt(plots.complete_ring_mean(field**2)))
        self.assertAlmostEqual(rms, np.sqrt(2.0), places=14)

    def test_incomplete_ring_is_not_renormalized(self):
        field = xr.DataArray([1.0, 2.0, np.nan, 4.0], dims="theta")
        self.assertTrue(np.isnan(plots.complete_ring_mean(field)))

    def test_sampling_flags_preserve_missingness(self):
        ds = polar_dataset()
        flags = np.ones((2, 2, 4), dtype=np.uint8)
        flags[0, 1, 2] = 0
        ds["t_valid"] = (("time", "rr", "theta"), flags)
        sampled = plots.valid_polar(ds, "t")
        self.assertTrue(np.isnan(sampled[0, 1, 2]))
        self.assertEqual(float(sampled[0, 0, 0]), 1.0)

    def test_shared_target_requires_exact_geolocation(self):
        first = polar_dataset()
        second = first.copy(deep=True)
        plots.verify_shared_target(first, second)
        second.longitude.values[0, 1, 1] += 1e-12
        with self.assertRaisesRegex(ValueError, "longitude differs"):
            plots.verify_shared_target(first, second)

    def test_shared_target_identifier_is_required(self):
        first, second = polar_dataset(), polar_dataset()
        second.attrs.pop("common_polar_target_id")
        with self.assertRaisesRegex(ValueError, "same shared target"):
            plots.verify_shared_target(first, second)

    def test_nonuniform_azimuths_are_rejected(self):
        ds = polar_dataset().assign_coords(theta=[0, 1, 3, 5])
        with self.assertRaisesRegex(ValueError, "uniform periodic"):
            plots.verify_shared_target(ds, ds)

    def test_off_grid_centres_are_rejected(self):
        profiles = xr.Dataset(
            {"t": (("time", "y_box", "x_box"), [[[1.0, 2.0], [3.0, 4.0]]])},
            coords={
                "time": [0],
                "latitude": (("time", "y_box"), [[-15.0, -15.1]]),
                "longitude": (("time", "x_box"), [[35.0, 35.1]]),
            },
        )
        track = xr.Dataset({"lat": ("time", [-15.1]), "lon": ("time", [35.0])})
        self.assertEqual(float(plots.tracked_columns(profiles, track).t[0]), 3.0)
        track.lat.values[0] += 0.001
        with self.assertRaisesRegex(ValueError, "off-grid"):
            plots.tracked_columns(profiles, track)

    def test_existing_outputs_are_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            root = Path(directory)
            config = root / "case.yaml"
            config.write_text("run: {name: case}\n", encoding="utf-8")
            output = root / "plots"
            output.mkdir()
            sentinel = output / f"{plots.STEMS[0]}.png"
            sentinel.write_bytes(b"keep")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                plots.main(["--input-dir", str(root), "--config", str(config)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_overlapping_contour_labels_are_removed(self):
        fig, ax = plots.plt.subplots()
        first = ax.text(0.5, 0.5, "first", gid="contour-label")
        second = ax.text(0.5, 0.5, "second", gid="contour-label")
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            with contextlib.redirect_stdout(io.StringIO()):
                plots.save_figure(fig, Path(directory), "layout", 72)
            self.assertTrue((Path(directory) / "layout.png").is_file())
            self.assertTrue((Path(directory) / "layout.pdf").is_file())
        self.assertTrue(first.get_visible())
        self.assertFalse(second.get_visible())

    def test_outside_text_is_rejected(self):
        fig, _ = plots.plt.subplots()
        fig.text(1.1, 0.5, "outside")
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            with self.assertRaisesRegex(RuntimeError, "outside the figure"):
                plots.save_figure(fig, Path(directory), "bad-layout", 72)

    def test_overlapping_essential_text_is_rejected(self):
        fig, ax = plots.plt.subplots()
        ax.text(0.5, 0.5, "essential")
        ax.text(0.5, 0.5, "also essential")
        with tempfile.TemporaryDirectory(dir="/tmp/opencode") as directory:
            with self.assertRaisesRegex(RuntimeError, "Overlapping figure text"):
                plots.save_figure(fig, Path(directory), "bad-layout", 72)


if __name__ == "__main__":
    unittest.main()
