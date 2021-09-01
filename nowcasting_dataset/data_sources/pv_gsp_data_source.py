import pandas as pd
from typing import List

import urllib
import json
import pandas as pd
import logging

from pvlive_api import PVLive
from datetime import datetime, timedelta

_LOG = logging.getLogger(__name__)


def get_pv_gsp_metadata_from_eso() -> pd.DataFrame:
    """
    Get the metadata for the pv gsp, from ESO.
    @return:
    """

    # call ESO website
    url = (
        "https://data.nationalgrideso.com/api/3/action/datastore_search?"
        "resource_id=bbe2cc72-a6c6-46e6-8f4e-48b879467368&limit=400"
    )
    fileobj = urllib.request.urlopen(url)
    d = json.loads(fileobj.read())

    # make dataframe
    results = d["result"]["records"]
    return pd.DataFrame(results)


def get_list_of_gsp_ids(maximum_number_of_gsp: int) -> List[int]:
    """
    Get list of gsp ids from ESO metadata
    @param maximum_number_of_gsp: clib list by this amount.
    @return: list of gsp ids
    """
    # get a lit of gsp ids
    metadata = get_pv_gsp_metadata_from_eso()

    # get rid of nans, and duplicates
    metadata = metadata[~metadata['gsp_id'].isna()]
    metadata.drop_duplicates(subset=['gsp_id'], inplace=True)

    # make into list
    gsp_ids = metadata['gsp_id'].to_list()
    gsp_ids = [int(gsp_id) for gsp_id in gsp_ids]

    # adjust number of gsp_ids
    if maximum_number_of_gsp is None:
        maximum_number_of_gsp = len(metadata)
    if maximum_number_of_gsp > len(metadata):
        logging.warning(f'Only {len(metadata)} gsp available to load')
    if maximum_number_of_gsp < len(metadata):
        gsp_ids = gsp_ids[0: maximum_number_of_gsp]

    return gsp_ids


def load_pv_gsp_raw_data_from_pvlive(start: datetime, end: datetime, number_of_gsp: int = None) -> pd.DataFrame:
    """
    Load raw pv gsp data from pvline. Note that each gsp is loaded separately. Also the data is loaded in 30 day chunks.
    @param start: the start date for gsp data to load
    @param end: the end date for gsp data to load
    @param number_of_gsp: The number of gsp to load. Note that on 2021-09-01 there were 338 to load.
    @return: Data frame of time series of gsp data. Shows PV data for each GSP from {start} to {end}
    """

    # get a lit of gsp ids
    gsp_ids = get_list_of_gsp_ids(maximum_number_of_gsp=number_of_gsp)

    # setup pv Live class, although here we are getting historic data
    pvl = PVLive()

    # set the first chunk of data, note that 30 day chunks are used accept if the end time is small than that
    first_start_chunk = start
    first_end_chunk = min([first_start_chunk + timedelta(days=30), end])

    gsp_data_df = []
    _LOG.debug(f'Will be getting data for {len(gsp_ids)} gsp ids')
    for gsp_id in gsp_ids:

        # set the first chunk start and end times
        start_chunk = first_start_chunk
        end_chunk = first_end_chunk

        while start_chunk <= end:
            _LOG.debug(f"Getting data for gsp id {gsp_id} from {start_chunk} to {end_chunk}")

            gsp_data_df.append(
                pvl.between(
                    start=start_chunk, end=end_chunk, entity_type="gsp", entity_id=gsp_id, extra_fields="", dataframe=True
                )
            )

            # add 30 days to the chunk, to get the next chunk
            start_chunk = start_chunk + timedelta(days=30)
            end_chunk = end_chunk + timedelta(days=30)

            if end_chunk > end:
                end_chunk = end

    gsp_data_df = pd.concat(gsp_data_df)

    # remove any extra data loaded
    gsp_data_df = gsp_data_df[gsp_data_df["datetime_gmt"] <= end]

    # remove any duplicates
    gsp_data_df.drop_duplicates(inplace=True)

    # sort dataframe
    gsp_data_df = gsp_data_df.sort_values(by=["gsp_id", "datetime_gmt"])

    # format data, remove timezone,
    gsp_data_df['datetime_gmt'] = gsp_data_df['datetime_gmt'].dt.tz_localize(None)

    return gsp_data_df
