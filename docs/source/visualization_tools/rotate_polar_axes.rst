Rotate polar axes
=================

Function setup\_geodesic\_polar\_ax
-----------------------------------

Apply a compass-like layout to a polar plot: north faces up and angles
increase clockwise, matching standard map and geodesic conventions.

Accepts a single polar axis or an array of axes — useful when working
with multi-panel figures.

.. py:function:: setup_geodesic_polar_ax(ax, *, deg_ticks=True, step_deg=30)

   :param ax: A polar axis or an array of polar axes to configure.
   :param deg_ticks: Show degree labels on the angular axis. Defaults to ``True``.
   :param step_deg: Spacing between degree labels in degrees. Defaults to ``30``.
   :returns: ``None`` — axes are modified in place.

Cyclic plotting view
--------------------

Analytical polar outputs are endpoint-exclusive. Use a separate closed view
for contour plots that need the wraparound endpoint:

.. code-block:: python

   from frameit.viz import close_theta_for_plot, setup_geodesic_polar_ax

   plot_view = close_theta_for_plot(polar_dataset.isel(time=0, level=0))
   plot_view.vtan.plot.contourf(ax=ax, x="theta", y="rr")
   setup_geodesic_polar_ax(ax)

The helper appends the first angular column once, preserves non-angular
variables, and validates an existing endpoint before reusing it. Keep the
original open dataset for azimuthal means and Fourier analysis.
