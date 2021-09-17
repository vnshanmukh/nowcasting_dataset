""" Function to split datasets up """

import pandas as pd
from typing import List, Tuple, Union

import logging

from nowcasting_dataset.dataset.split.day import split_day, split_day_random
from nowcasting_dataset.dataset.split.year import (
    split_year,
    TrainValidationTestYear,
    default_train_test_validation_year,
)
from nowcasting_dataset.dataset.split.week import (
    split_week_random,
    split_week,
)
from enum import Enum

logger = logging.getLogger(__name__)


class SplitMethod(Enum):
    Day = "day"
    DayRandom = "day_random"
    Week = "week"
    WeekRandom = "week_random"
    Year = "year"
    Same = "same"


def split_data(
    datetimes: Union[List[pd.Timestamp], pd.DatetimeIndex],
    method: SplitMethod,
    train_test_validation_split: Tuple[int] = (3, 1, 1),
    train_test_validation_year: TrainValidationTestYear = default_train_test_validation_year,
) -> (List[pd.Timestamp], List[pd.Timestamp], List[pd.Timestamp]):
    """
    Split the date using various different methods

    Args:
        datetimes: The datetimes to be split
        method: the method to be used
        train_test_validation_split: ratios of how the split is made
        train_test_validation_year: pydantic class of which years below to which dataset

    Returns: train, validation and test dataset

    """

    logger.info(f"Splitting data with method {method}")

    if method == SplitMethod.Same:
        train_datetimes = datetimes
        validation_datetimes = datetimes
        test_datetimes = datetimes
    elif method == SplitMethod.Day:
        train_datetimes, validation_datetimes, test_datetimes = split_day(
            datetimes=datetimes, train_test_validation_split=train_test_validation_split
        )
    elif method == SplitMethod.DayRandom:
        train_datetimes, validation_datetimes, test_datetimes = split_day_random(
            datetimes=datetimes, train_test_validation_split=train_test_validation_split
        )
    elif method == SplitMethod.Week:
        train_datetimes, validation_datetimes, test_datetimes = split_week(
            datetimes=datetimes, train_test_validation_split=train_test_validation_split
        )
    elif method == SplitMethod.WeekRandom:
        train_datetimes, validation_datetimes, test_datetimes = split_week_random(
            datetimes=datetimes, train_test_validation_split=train_test_validation_split
        )
    elif method == SplitMethod.Year:
        train_datetimes, validation_datetimes, test_datetimes = split_year(
            datetimes=datetimes, train_test_validation_year=train_test_validation_year
        )
    else:
        raise

    return train_datetimes, validation_datetimes, test_datetimes
