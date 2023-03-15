# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

from .exceptions import *
from .rows import *
from .types import *
from .stats import Stats


def intuit_df(df, **kwargs):
    """Intuit a DataFrame"""

    from pandas import DataFrame

    if not isinstance(df, DataFrame):
        raise RowIntuitError("Expecting a DataFrame")

    samp_len = 1000 if len(df) > 1000 else len(df)

    head = list(df.columns) + list(df.sample(int(samp_len/2)).itertuples(index=False))

    tail = list(df.sample(int(samp_len/2)).itertuples(index=False))

    #ri = RowIntuiter().run(head, tail)
    #return ri

    source = [list(df.columns)] + list([ tuple(e) for e in df.itertuples(index=False)])

    ti = TypeIntuiter().run(source)
    return ti