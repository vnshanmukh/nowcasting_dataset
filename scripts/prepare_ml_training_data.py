#!/usr/bin/env python3

from nowcasting_dataset.datamodule import NowcastingDataModule
from nowcasting_dataset.example import Example
from pathlib import Path
import numpy as np
import xarray as xr
import gcsfs
import torch
import os
import glob
from typing import List

from nowcasting_dataset.utils import get_netcdf_filename

import logging
logging.basicConfig()
_LOG = logging.getLogger('nowcasting_dataset')
_LOG.setLevel(logging.DEBUG)

BUCKET = Path('solar-pv-nowcasting-data')

# Solar PV data
PV_PATH = BUCKET / 'PV/PVOutput.org'
PV_DATA_FILENAME = PV_PATH / 'UK_PV_timeseries_batch.nc'
PV_METADATA_FILENAME = PV_PATH / 'UK_PV_metadata.csv'

SAT_FILENAME = BUCKET / 'satellite/EUMETSAT/SEVIRI_RSS/OSGB36/all_zarr_int16_single_timestep.zarr'

# Numerical weather predictions
NWP_BASE_PATH = BUCKET / 'NWP/UK_Met_Office/UKV__2018-01_to_2019-12__chunks__variable10__init_time1__step1__x548__y704__.zarr'


DST_NETCDF4_PATH = 'gs://solar-pv-nowcasting-data/prepared_ML_training_data/'
LOCAL_TEMP_PATH = Path('~/temp/').expanduser()


# Necessary to avoid "RuntimeError: receieved 0 items of ancdata".  See:
# https://discuss.pytorch.org/t/runtimeerror-received-0-items-of-ancdata/4999/2
torch.multiprocessing.set_sharing_strategy('file_system')


def get_data_module():
    data_module = NowcastingDataModule(
        batch_size=32,
        history_len=6,  #: Number of timesteps of history, not including t0.
        forecast_len=12,  #: Number of timesteps of forecast.
        image_size_pixels=32,
        nwp_channels=('t', 'dswrf', 'prate', 'r', 'sde', 'si10', 'vis', 'lcc', 'mcc', 'hcc'),
        sat_channels=(
            'HRV', 'IR_016', 'IR_039', 'IR_087', 'IR_097', 'IR_108', 'IR_120',
            'IR_134', 'VIS006', 'VIS008', 'WV_062', 'WV_073'),
        pv_power_filename=PV_DATA_FILENAME,
        pv_metadata_filename=f'gs://{PV_METADATA_FILENAME}',
        sat_filename=f'gs://{SAT_FILENAME}',
        nwp_base_path=f'gs://{NWP_BASE_PATH}',
        pin_memory=True,  #: Passed to DataLoader.
        num_workers=16,  #: Passed to DataLoader.
        prefetch_factor=8,  #: Passed to DataLoader.
        n_samples_per_timestep=8,  #: Passed to NowcastingDataset
        n_training_batches_per_epoch=25_000,
        n_validation_batches_per_epoch=1_000,
        collate_fn=lambda x: x,
        convert_to_numpy=False  #: Leave data as Pandas / Xarray for pre-preparing.
    )
    _LOG.info('prepare_data()')
    data_module.prepare_data()
    _LOG.info('setup()')
    data_module.setup()
    return data_module


def coord_to_range(da: xr.DataArray, dim: str, prefix: str, dtype=np.int32) -> xr.DataArray:
    coord = da[dim]
    da[dim] = np.arange(len(coord), dtype=dtype)
    da[f'{prefix}_{dim}_coords'] = xr.DataArray(coord, coords=[da[dim]], dims=[dim])
    return da


def batch_to_dataset(batch: List[Example]) -> xr.Dataset:
    """Concat all the individual fields in an Example into a single Dataset.

    Args:
      batch: List of Example objects, which together constitute a single batch.
    """
    datasets = []
    for i, example in enumerate(batch):
        individual_datasets = []
        example_dim = {'example': np.array([i], dtype=np.int32)}
        for name in ['sat_data', 'nwp']:
            ds = example[name].to_dataset(name=name)
            short_name = name.replace('_data', '')
            if name == 'nwp':
                ds = ds.rename({'target_time': 'time'})
            for dim in ['time', 'x', 'y']:
                ds = coord_to_range(ds, dim, prefix=short_name)
            ds = ds.rename({
                'variable': f'{short_name}_variable',
                'x': f'{short_name}_x',
                'y': f'{short_name}_y',
            })
            individual_datasets.append(ds)

        # Datetime features
        for name in ['hour_of_day_sin', 'hour_of_day_cos', 'day_of_year_sin', 'day_of_year_cos']:
            ds = example[name].rename(name).to_xarray().to_dataset()
            individual_datasets.append(ds)

        # PV
        pv_yield = example['pv_yield'].rename('pv_yield').to_xarray().rename({'datetime': 'time'}).to_dataset()
        pv_yield = coord_to_range(pv_yield, 'time', prefix='pv_yield')
        # This will expand all dataarrays to have an 'example' dim.
        for name in ['pv_system_id', 'pv_system_row_number']:
            pv_yield[name] = xr.DataArray([example[name]], coords=example_dim, dims=['example'])
        individual_datasets.append(pv_yield)

        # Merge
        merged_ds = xr.merge(individual_datasets)
        datasets.append(merged_ds)
    return xr.concat(datasets, dim='example')


def fix_dtypes(concat_ds):
    ds_dtypes = {
        'example': np.int32,
        'sat_x_coords': np.int32, 'sat_y_coords': np.int32,
        'nwp': np.float32,
        'nwp_x_coords': np.float32, 'nwp_y_coords': np.float32,
        'pv_system_id': np.int32, 'pv_system_row_number': np.int32}

    for name, dtype in ds_dtypes.items():
        concat_ds[name] = concat_ds[name].astype(dtype)
    return concat_ds


def write_batch_locally(batch: List[Example], batch_i: int):
    dataset = batch_to_dataset(batch)
    dataset = fix_dtypes(dataset)
    encoding = {name: {'compression': 'lzf'} for name in dataset.data_vars}
    filename = get_netcdf_filename(batch_i)
    local_filename = LOCAL_TEMP_PATH / filename
    dataset.to_netcdf(
        local_filename, engine='h5netcdf', mode='w', encoding=encoding)


def upload_and_delete_local_files(dst_path: str):
    _LOG.info('Uploading!')
    gcs = gcsfs.GCSFileSystem()
    gcs.put(str(LOCAL_TEMP_PATH), dst_path, recursive=True)
    # Delete local files
    files = glob.glob(str(LOCAL_TEMP_PATH / '*.nc'))
    for f in files:
        os.remove(f)


def iterate_over_dataloader_and_write_to_disk(
        dataloader: torch.utils.data.DataLoader, dst_path: str):
    UPLOAD_EVERY_N_BATCHES = 64
    _LOG.info('Getting first batch')
    for batch_i, batch in enumerate(dataloader):
        _LOG.info(f'Got batch {batch_i}')
        write_batch_locally(batch, batch_i)
        if batch_i > 0 and batch_i % UPLOAD_EVERY_N_BATCHES == 0:
            upload_and_delete_local_files(dst_path)
        _LOG.debug('getting next batch...')
    upload_and_delete_local_files(dst_path)


def main():
    datamodule = get_data_module()
    _LOG.info('Finished preparing datamodule!')
    _LOG.info('Preparing training data...')
    iterate_over_dataloader_and_write_to_disk(
        datamodule.train_dataloader(),
        os.path.join(DST_NETCDF4_PATH, 'train'))
    _LOG.info('Preparing validation data...')
    iterate_over_dataloader_and_write_to_disk(
        datamodule.val_dataloader(),
        os.path.join(DST_NETCDF4_PATH, 'validation'))
    _LOG.info('Done!')


if __name__ == '__main__':
    main()