"""Check one missing wind sample and one valid category."""
import numpy as np
import xarray as xr

with xr.open_dataset("strict-results/products/analytic-missing.atmosphere.polar.nc") as data:
    bad = (data.u_geometry_mapped == 1) & (data.u_valid == 0)
    t, r, a = np.argwhere(bad.values)[0]
    sample = data.isel(time=int(t), radius=int(r), azimuth=int(a))
    print("Wind at a mapped point is missing:", sample.u.isnull().item())
    print("Interpolation status:", sample.u_interpolation_status.item())
    print("Valid-weight fraction:", sample.u_support_fraction.item())
    print("Full ring is valid:", bool(sample.u_full_ring_valid.item()))
    water = (data.surface_type == 0) & (data.surface_type_valid == 1)
    print("Valid water code 0 is present:", water.any().item())
