""" Model for output of Optical Flow data """
from __future__ import annotations

from xarray.ufuncs import isinf, isnan

from nowcasting_dataset.data_sources.datasource_output import DataSourceOutput


class OpticalFlow(DataSourceOutput):
    """ Class to store optical flow data as a xr.Dataset with some validation """

    __slots__ = ()
    _expected_dimensions = ("time", "x", "y", "channels")

    @classmethod
    def model_validation(cls, v):
        """ Check that all values are not NaN, Infinite, or -1."""
        assert (~isnan(v.data)).all(), "Some optical flow data values are NaNs"
        assert (~isinf(v.data)).all(), "Some optical flow data values are Infinite"
        assert (v.data != -1).all(), "Some optical flow data values are -1's"
        return v