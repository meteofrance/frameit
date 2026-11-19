"""Compare the exported wind locations and directions."""
import xarray as xr

native_path = (
    "results/staggered-winds-native/products/"
    "staggered-winds-native.atmosphere.model_grid.nc"
)
with xr.open_dataset(native_path) as native:
    print("Native UT x (m):", native.ni_u_source_coordinate.isel(time=0).values.tolist())
    print("Native VT y (m):", native.nj_v_source_coordinate.isel(time=0).values.tolist())

earth_path = (
    "results/staggered-winds-earth/products/"
    "staggered-winds-earth.atmosphere.model_grid.nc"
)
with xr.open_dataset(earth_path) as earth:
    print("Mass x (m):", earth.ni_source_coordinate.isel(time=0).values.tolist())
    print("Mass y (m):", earth.nj_source_coordinate.isel(time=0).values.tolist())
    wind = earth[["UT", "VT"]].isel(time=0, level=0, y=1, x=[1, 2])
    print("Eastward (m/s):", wind.UT.values.round(9).tolist())
    print("Northward (m/s):", wind.VT.values.round(9).tolist())
