"""Independent analytical fields for cyclone-centred point-sampling qualification.

Wind formulas deliberately do not import frameit's component rotation or
interpolation helpers. Planar-chart fixtures and geodesic fixtures have distinct
physical definitions; planar vorticity is not claimed to be ellipsoidal vorticity.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import xarray as xr
from pyproj import Geod


@dataclass(frozen=True)
class AnalyticVortex:
    kind: str = "geodesic"
    longitude: float = 60.
    latitude: float = -20.
    radius_m: float = 40000.
    tangential_max_ms: float = 50.
    inflow_max_ms: float = 0.
    gaussian_vorticity_s: float = 1.5e-3
    gaussian_width_m: float = 45000.
    streamfunction_amplitude_m2s: float = 80000.
    streamfunction_width_m: float = 15000.
    streamfunction_mode: int = 2
    streamfunction_peak_math_rad: float = .4
    regularization_inner_m: float = 5000.
    regularization_outer_m: float = 15000.
    earth_model: str = "WGS84"

    def parameters(self):
        return asdict(self)

    def polar_geometry(self, longitude, latitude):
        longitude, latitude = np.broadcast_arrays(longitude, latitude)
        geod = Geod(ellps=self.earth_model)
        initial, back, radius = geod.inv(
            np.full(longitude.shape, self.longitude), np.full(latitude.shape, self.latitude),
            longitude, latitude,
        )
        return radius, np.deg2rad(initial), np.deg2rad(back + 180)

    def evaluate(self, longitude, latitude):
        """Evaluate earth-relative u/v and scalar quantities directly at points."""
        radius, initial, terminal = self.polar_geometry(longitude, latitude)
        if self.kind == "geodesic":
            profile = radius / self.radius_m * np.exp((1 - (radius / self.radius_m)**2) / 2)
            radial = -self.inflow_max_ms * profile
            tangential = self.tangential_max_ms * profile
            u = radial * np.sin(terminal) + tangential * np.cos(terminal)
            v = radial * np.cos(terminal) - tangential * np.sin(terminal)
        else:
            # Azimuthal-equidistant x/y chart; these prescribed Cartesian
            # components are interpreted as local east/north field values.
            x, y = radius * np.sin(initial), radius * np.cos(initial)
            gamma = np.arctan2(y, x)
            if self.kind == "gaussian_vorticity":
                strength = self.gaussian_vorticity_s * self.gaussian_width_m**2 / 2
                factor = np.divide(
                    strength * -np.expm1(-(radius / self.gaussian_width_m)**2), radius**2,
                    out=np.full_like(radius, self.gaussian_vorticity_s / 2), where=radius > 0,
                )
                u, v = -factor * y, factor * x
            elif self.kind == "streamfunction":
                envelope, derivative = self.streamfunction_envelope(radius)
                mode = self.streamfunction_mode
                angle = mode * (gamma - self.streamfunction_peak_math_rad)
                radial = np.divide(mode * envelope * np.sin(angle), radius,
                                   out=np.zeros_like(radius), where=radius > 0)
                ccw = derivative * np.cos(angle)
                u = radial * np.cos(gamma) - ccw * np.sin(gamma)
                v = radial * np.sin(gamma) + ccw * np.cos(gamma)
            else:
                raise ValueError(f"Unknown analytical vortex {self.kind!r}")
        lon_rad, lat_rad = np.deg2rad(longitude), np.deg2rad(latitude)
        fields = {"u": u, "v": v, "constant": np.ones_like(radius),
                  "smooth_scalar": 2 + np.cos(lat_rad)**2 * np.sin(2 * lon_rad)}
        for mode in (1, 2, 3):
            envelope = (radius / self.radius_m)**mode * np.exp(
                (1 - (radius / self.radius_m)**2) / 2
            )
            fields[f"harmonic_{mode}"] = envelope * np.cos(mode * (initial - .37))
        return fields

    def streamfunction_envelope(self, radius):
        """Zhao et al. (2019), Eq. (4), with explicit C2 inner regularization.

        The unmodified radial Gaussian is used outside regularization_outer_m.
        A quintic switch makes the angular disturbance exactly zero in the
        inner disk; g' includes the derivative of that switch.
        """
        base = self.streamfunction_amplitude_m2s * np.exp(
            -(radius - self.radius_m)**2 / (2 * self.streamfunction_width_m**2)
        )
        derivative = -(radius - self.radius_m) * base / self.streamfunction_width_m**2
        width = self.regularization_outer_m - self.regularization_inner_m
        z = np.clip((radius - self.regularization_inner_m) / width, 0, 1)
        switch = z**3 * (10 - 15 * z + 6 * z**2)
        slope = 30 * z**2 * (1 - z)**2 / width
        return base * switch, derivative * switch + base * slope


def displaced_centre(vortex, distance_m, bearing_deg):
    lon, lat, _ = Geod(ellps=vortex.earth_model).fwd(
        vortex.longitude, vortex.latitude, bearing_deg, distance_m
    )
    return float(lon), float(lat)


def sampled_truth(vortex, target, analysis_centre):
    """Direct field/basis evaluation about the actual analysis centre."""
    lon, lat = target.longitude.values, target.latitude.values
    fields = vortex.evaluate(lon, lat)
    geod = Geod(ellps=vortex.earth_model)
    _, back, distance = geod.inv(np.full(lon.shape, analysis_centre[0]),
                                  np.full(lat.shape, analysis_centre[1]), lon, lat)
    bearing = np.deg2rad(back + 180)
    fields["vrad"] = fields["u"] * np.sin(bearing) + fields["v"] * np.cos(bearing)
    fields["vtan"] = fields["u"] * np.cos(bearing) - fields["v"] * np.sin(bearing)
    fields["wind_speed"] = np.hypot(fields["u"], fields["v"])
    # Use target radius labels for the intentional origin singularity rather
    # than an inverse-geodesic near-zero floating distance.
    origin = np.broadcast_to((target.rr.values == 0)[None, :, None], distance.shape)
    for name in ("vrad", "vtan"):
        fields[name] = np.where(origin, np.nan, fields[name])
    return fields


def analytic_source(
    vortex: AnalyticVortex, spacing_m: float, *, grid_kind="rectilinear", extent_m=120000.,
    grid_centre=None, alignment=(0., 0.), times=(0,),
):
    """Build independent geographic/curvilinear source samples on a fixed chart."""
    centre = grid_centre or (vortex.longitude, vortex.latitude)
    half = int(np.ceil(extent_m / spacing_m))
    indices = np.arange(-half, half + 1)
    x, y = np.meshgrid((indices + alignment[0]) * spacing_m,
                        (indices + alignment[1]) * spacing_m)
    geod = Geod(ellps=vortex.earth_model)
    if grid_kind == "rectilinear":
        _, _, east_m = geod.inv(centre[0], centre[1], centre[0] + 1, centre[1])
        _, _, north_m = geod.inv(centre[0], centre[1], centre[0], centre[1] + 1)
        lon, lat = centre[0] + x / east_m, centre[1] + y / north_m
    elif grid_kind == "curvilinear":
        x = x + 1500 * np.sin(y / 60000)
        y = y + 1200 * np.sin(x / 60000)
        distance = np.hypot(x, y)
        lon, lat, _ = geod.fwd(np.full(x.shape, centre[0]), np.full(y.shape, centre[1]),
                               np.rad2deg(np.arctan2(x, y)), distance)
    else:
        raise ValueError("grid_kind must be rectilinear or curvilinear")
    fields = vortex.evaluate(lon, lat)
    shape = (len(times), 1, *x.shape)
    source = xr.Dataset(
        {name: (("time", "heightAboveGround", "y_box", "x_box"),
                np.broadcast_to(value[None, None], shape).copy())
         for name, value in fields.items()},
        coords={"time": list(times), "heightAboveGround": [2000.], "y_box": indices,
                "x_box": indices, "longitude": (("y_box", "x_box"), (lon + 180) % 360 - 180),
                "latitude": (("y_box", "x_box"), lat)},
        attrs={"analytical_fixture": vortex.kind, "source_grid_kind": grid_kind,
               "nominal_source_spacing_m": spacing_m},
    )
    for name in ("u", "v"):
        source[name].attrs.update(units="m s-1", wind_reference_frame="earth")
    source.heightAboveGround.attrs["units"] = "m"
    return source
