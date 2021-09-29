import os
from datetime import datetime

import pandas as pd

import nowcasting_dataset
from nowcasting_dataset.consts import T0_DT
from nowcasting_dataset.data_sources.gsp.gsp_data_source import GSPDataSource
from nowcasting_dataset.geospatial import osgb_to_lat_lon


def test_gsp_pv_data_source_init():
    local_path = os.path.dirname(nowcasting_dataset.__file__) + "/.."

    gsp = GSPDataSource(
        filename=f"{local_path}/tests/data/gsp/test.zarr",
        start_dt=datetime(2019, 1, 1),
        end_dt=datetime(2019, 1, 2),
        history_minutes=30,
        forecast_minutes=60,
        convert_to_numpy=True,
        image_size_pixels=64,
        meters_per_pixel=2000,
    )


def test_gsp_pv_data_source_get_locations_for_batch():
    local_path = os.path.dirname(nowcasting_dataset.__file__) + "/.."

    gsp = GSPDataSource(
        filename=f"{local_path}/tests/data/gsp/test.zarr",
        start_dt=datetime(2019, 1, 1),
        end_dt=datetime(2019, 1, 2),
        history_minutes=30,
        forecast_minutes=60,
        convert_to_numpy=True,
        image_size_pixels=64,
        meters_per_pixel=2000,
    )

    locations_x, locations_y = gsp.get_locations_for_batch(t0_datetimes=gsp.gsp_power.index[0:10])

    assert len(locations_x) == len(locations_y)
    # This makes sure it is not in lat/lon.
    # Note that OSGB could be <= than 90, but that would mean a location in the middle of the sea,
    # which is impossible for GSP data
    assert locations_x[0] > 90
    assert locations_y[0] > 90

    lat, lon = osgb_to_lat_lon(locations_x, locations_y)

    assert 0 < lat[0] < 90  # this makes sure it is in lat/lon
    assert -90 < lon[0] < 90  # this makes sure it is in lat/lon


def test_gsp_pv_data_source_get_example():
    local_path = os.path.dirname(nowcasting_dataset.__file__) + "/.."

    gsp = GSPDataSource(
        filename=f"{local_path}/tests/data/gsp/test.zarr",
        start_dt=datetime(2019, 1, 1),
        end_dt=datetime(2019, 1, 2),
        history_minutes=30,
        forecast_minutes=60,
        convert_to_numpy=True,
        image_size_pixels=64,
        meters_per_pixel=2000,
    )

    x_locations, y_locations = gsp.get_locations_for_batch(t0_datetimes=gsp.gsp_power.index[0:10])
    l = gsp.get_example(
        t0_dt=gsp.gsp_power.index[0], x_meters_center=x_locations[0], y_meters_center=y_locations[0]
    )

    assert len(l["gsp_id"]) == len(l["gsp_yield"][0])
    assert len(l["gsp_x_coords"]) == len(l["gsp_y_coords"])
    assert len(l["gsp_x_coords"]) > 0
    assert type(l[T0_DT]) == pd.Timestamp


def test_gsp_pv_data_source_get_batch():
    local_path = os.path.dirname(nowcasting_dataset.__file__) + "/.."

    gsp = GSPDataSource(
        filename=f"{local_path}/tests/data/gsp/test.zarr",
        start_dt=datetime(2019, 1, 1),
        end_dt=datetime(2019, 1, 2),
        history_minutes=30,
        forecast_minutes=60,
        sample_period_minutes=30,
        convert_to_numpy=True,
        image_size_pixels=64,
        meters_per_pixel=2000,
    )

    batch_size = 10

    x_locations, y_locations = gsp.get_locations_for_batch(
        t0_datetimes=gsp.gsp_power.index[0:batch_size]
    )

    batch = gsp.get_batch(
        t0_datetimes=gsp.gsp_power.index[batch_size : 2 * batch_size],
        x_locations=x_locations[0:batch_size],
        y_locations=y_locations[0:batch_size],
    )

    assert len(batch) == batch_size
    assert len(batch[0]["gsp_yield"]) == 4
    assert len(batch[0]["gsp_id"]) == len(batch[0]["gsp_x_coords"])
    assert len(batch[1]["gsp_x_coords"]) == len(batch[1]["gsp_y_coords"])
    assert len(batch[2]["gsp_x_coords"]) > 0
    assert T0_DT in batch[3].keys()