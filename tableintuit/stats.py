# coding: utf-8
"""

Computing stats on the fly for data written to a partition

Copyright (c) 2015 Civic Knowledge. This file is licensed under the terms of the
Revised BSD License, included in this distribution as LICENSE.txt
"""

import logging
import datetime
from collections import Counter, OrderedDict

from livestats import livestats

from .exceptions import StatsError

logger = logging.getLogger(__name__)


def text_hist(nums, ascii=False):

    if ascii:
        parts = ' _.,,-=T#'
    else:
        parts = ' ▁▂▃▄▅▆▇▉'

    nums = list(nums)
    fraction = max(nums) / float(len(parts) - 1)
    if fraction:
        return ''.join(parts[int(round(x / fraction))] for x in nums)
    else:
        return ''


class Constant:
    """Organizes constants in a class."""

    class ConstError(TypeError):
        pass

    def __setattr__(self, name, value):
        if name in self.__dict__:
            raise self.ConstError("Can't rebind const(%s)" % name)
        self.__dict__[name] = value


type_map = {
    'str': str,
    'string': str,
    'text': str,
    'int': int,
    'integer': int,
    'number': int,
    'float': float,
    'real': float,
    'date': datetime.date,
    'datetime': datetime.datetime,
    'time': datetime.time,
    'unknown': bytes,
    'geometry': bytes

}

class StatSet(object):
    LOM = Constant()  # Level of Measurement, More or Less

    LOM.NOMINAL = 'n'  # Categorical, usually strings.
    LOM.ORDINAL = 'o'  # A number which counts or ranks. Subtraction is not defined. Times and Dates
    LOM.INTERVAL = 'i'  # A number, for which subtraction is defined, but not division
    LOM.RATIO = 'r'  # A number, for which division is defined and zero means "nothing". Kelvin, but not Celsius

    def __init__(self, parent, name, typ, n_rows=None, distribution=False, descriptive=False, sample_values = False):

        self.parent = parent
        self.n_rows = n_rows

        self.descriptive = descriptive
        self.distribution = distribution
        self.sample_values = sample_values

        if isinstance(typ, str):
            typ = type_map[typ]

        from datetime import date, time, datetime

        self.is_gvid = bool('gvid' in name)  # A special name in Ambry
        self.is_geoid= bool('geoid' in name)  # A special name in Ambry
        self.is_year = bool('year' in name)
        self.is_time = typ == time
        self.is_date = typ == date or typ == datetime

        # Tricky hack, indexing with a bool.
        self.flags = " G"[self.is_gvid] + " Y"[self.is_year] + " T"[self.is_time] + " D"[self.is_date]

        if self.is_year or self.is_time or self.is_date:
            lom = StatSet.LOM.ORDINAL
        elif typ == bytes or typ == str:
            lom = StatSet.LOM.NOMINAL
        elif typ == int or typ == float:
            lom = StatSet.LOM.INTERVAL
        else:
            lom = StatSet.LOM.NOMINAL

        self.column_name = name

        self.lom = lom
        self.type = typ
        self.n = 0
        self.counts = Counter()
        self.size = None
        self.stats = livestats.LiveStats([0.25, 0.5, 0.75])  # runstats.Statistics()

        self.bin_min = None
        self.bin_max = None
        self.bin_width = None
        self.bin_primer_count = 5000  # how many points to collect before creating hist bins

        self._hist_built = False

        self.num_bins = 16
        self.bins = [0] * self.num_bins

    @property
    def is_numeric(self):
        return self.lom == self.LOM.INTERVAL or self.lom == self.LOM.RATIO

    def add(self, v):

        self.n += 1

        try:
            if v is None:
                unival = ''
            else:
                unival = '{}'.format(v)

        except UnicodeError:
            unival = v.decode('ascii', 'replace')

        self.size = max(self.size or 0, len(unival.encode('utf-8'))) # NOTE length in bytes, not characters

        if self.lom == self.LOM.NOMINAL or self.lom == self.LOM.ORDINAL:
            if self.is_time or self.is_date:
                self.counts[unival] += 1
            else:
                if len(unival) > 100:
                    self.counts[unival[:100]] += 1
                elif v is None:
                    self.counts['NULL'] += 1
                else:
                    self.counts[unival] += 1

        elif self.is_numeric and self.descriptive:

            # To build the histogram, we need to collect counts, but would rather
            # not collect all of the values. So, collect the first 5K, then use that
            # to determine the 4sigma range of the histogram.
            # HACK There are probably a lot of 1-off errors in this
            float_v = _force_float(v)

            if self.n < self.bin_primer_count:  # Still building the counts.
                if v is None:
                    self.counts['NULL'] += 1
                else:
                    self.counts[unival] += 1

            elif self.n == self.bin_primer_count:  # Hit the limit, now can get the hist bins
                self._build_hist_bins()

            elif self.n > self.bin_primer_count and self.bin_min <= float_v <= self.bin_max:
                bin_ = int((float_v - self.bin_min) / self.bin_width)
                self.bins[bin_] += 1
            try:

                self.stats.add(float(v))
            except (ValueError, TypeError):
                if v is None:
                    self.counts['NULL'] += 1
                else:
                    self.counts[unival] += 1


    def _build_hist_bins(self):
        from math import sqrt

        if self._hist_built:
            return

        # If less than 1% are unique, assume that this number is actually an ordinal
        if self.nuniques < (self.n / 100):
            self.lom = self.LOM.ORDINAL
            self.stats = livestats.LiveStats()
        else:

            self.bin_min = self.stats.mean() - sqrt(self.stats.variance()) * 2
            self.bin_max = self.stats.mean() + sqrt(self.stats.variance()) * 2
            self.bin_width = (self.bin_max - self.bin_min) / self.num_bins

            if self.bin_width == 0:
                # I guess we just aren't getting a histogram.
                self._hist_build = True
                return

            # Puts the saved entries into the hist bins.
            def fill_bins():
                bins = [0] * self.num_bins
                for v, count in self.counts.items():
                    float_v = _force_float(v)
                    if float_v >= self.bin_min and float_v <= self.bin_max and self.bin_width != 0:
                        bin_ = int((float_v - self.bin_min) / self.bin_width)
                        if bin_ < len(bins):
                            bins[bin_] += count
                return bins

            bins = fill_bins()

            # No, strip off all of the leftmost bins that have no value. This makes for prettier power
            # and exponential distributions, where the left skew of the mean leaves the left side of the
            # chart empty.
            first_non_zero = next((index for index, value in enumerate(bins) if value != 0), None)

            if first_non_zero:
                self.bin_min = self.bin_min + self.bin_width*first_non_zero
                self.bin_width = (self.bin_max - self.bin_min) / self.num_bins

            self.bins = fill_bins()

        # self.counts = Counter()
        self._hist_build = True

    @property
    def uniques(self):
        return list(self.counts)

    @property
    def nuniques(self):
        return len(list(self.counts.items()))

    @property
    def mean(self):
        return self.stats.mean() if self.is_numeric else None

    @property
    def stddev(self):
        from math import sqrt
        return sqrt(self.stats.variance()) if self.is_numeric else None

    @property
    def min(self):
        return self.stats.minimum() if self.is_numeric else None

    @property
    def p25(self):
        try:
            return self.stats.quantiles()[0][1]
        except IndexError:
            return None

    @property
    def median(self):
        try:
            return self.stats.quantiles()[1][1]
        except IndexError:
            return None

    @property
    def p50(self):
        try:
            return self.stats.quantiles()[1][1]
        except IndexError:
            return None

    @property
    def p75(self):
        try:
            return self.stats.quantiles()[2][1]
        except IndexError:
            return None

    @property
    def max(self):
        return self.stats.maximum() if self.is_numeric else None

    @property
    def skewness(self):
        return self.stats.skewness() if self.is_numeric else None

    @property
    def kurtosis(self):
        return self.stats.kurtosis() if self.is_numeric else None

    @property
    def hist(self):
        return text_hist(self.bins) if self.is_numeric else None

    @property
    def width(self):
        return self.max_width if self.is_numeric else None

    @property
    def uvalues(self):
        return dict(self.counts.most_common(100))

    @property
    def dict(self):
        """Return a  dict that can be passed into the ColumnStats constructor"""

        try:
            skewness = self.skewness
            kurtosis = self.kurtosis
        except ZeroDivisionError:
            skewness = kurtosis = float('nan')

        base_cols = [
            ('name', self.column_name),
            ('flags', self.flags),
            ('type', self.type.__name__ ),
            ('lom', self.lom),
            ('count', self.n),
            ('nuniques', self.nuniques),
            ('width', self.size),
        ]

        descriptive_cols = [
            ('mean', self.mean),
            ('std', self.stddev),
            ('min', self.min),
            ('p25', self.p25),
            ('p50', self.p50),
            ('p75', self.p75),
            ('max', self.max)
        ]

        distribution_cols = [
            ('skewness', skewness),
            ('kurtosis', kurtosis),
            ('hist', self.bins),
            ('text_hist', text_hist(self.bins)),
        ]

        sample_values_cols = [
            ('uvalues', self.uvalues)
        ]

        return OrderedDict(
           base_cols +
           (descriptive_cols if self.descriptive else []) +
           (distribution_cols if self.distribution else []) +
           (sample_values_cols if self.sample_values else [])
        )


class Stats(object):
    """ Stats object reads rows from the input iterator, processes the row, and yields it back out"""

    def __init__(self, source, schema, distribution=False, descriptive=False, sample_values=False,
                 n_rows=None, sample_size=None):
        """
        :param source: Source iterator. Must return dict-like rows.
        :param schema:
        :param distribution: If True, generate distribution stats: histogram, skewness, kurtosis
        :param descriptive: If True, generate descriptive stats: mean, std, min, max, quartiles.
        :param n_rows: An estimate of the number of rows in the datasets, for sampling
        :param sample_size: Number of rows to sample.
        """

        self._source = source
        self._stats = {}
        self._func = None
        self._func_code = None
        self._n_rows = n_rows
        self._sample_size = sample_size

        self._distribution = distribution
        self._descriptive = descriptive
        self._sample_values = sample_values

        if bool(self._sample_size) ^ bool(self._n_rows):
            raise StatsError("If sample_size is specified, must also specify n_rows")

        if self._sample_size is not None and self._n_rows is not None and (self._sample_size <= 0 or self._n_rows <= 0):
            raise StatsError("If specified, both sample_size and n_rows must be positive and non-zero")

        for col_name, col_type in schema:
            self._stats[col_name] = StatSet(self, col_name, col_type, n_rows,
                                            distribution=self._distribution,
                                            descriptive=self._descriptive,
                                            sample_values=self._sample_values)

        self._func, self._func_code = self.build()

    @property
    def dict(self):
        return self._stats

    def __getitem__(self, item):
        return self._stats[item]

    def __contains__(self, item):
        return item in self._stats

    def build(self):

        parts = []

        for name in self._stats.keys():
            if self._stats[name] is not None:
                parts.append("stats['{name}'].add(row['{name}'])".format(name=name))

        if not parts:
            error_msg = 'Did not get any stats variables for table {}. Was add() or init() called first?'\
                .format(self.table.name)
            raise StatsError(error_msg)

        code = 'def _process_row(stats, row):\n    {}'.format('\n    '.join(parts))

        exec(code)

        f = locals()['_process_row']

        return f, code

    def stats(self):
        return [(name, self._stats[name]) for name, stat in self._stats.items()]

    def run(self):
        """ Run the stats. The source must yield Row proxies.
        """

        self._func, self._func_code = self.build()

        def process_row(row):

            try:
                self._func(self._stats, row)
            except TypeError as e:
                raise TypeError("Failed for '{}'; {}".format(self._func_code, e))
            except KeyError:
                raise KeyError(
                    'Failed to find key in row. headers = "{}", code = "{}" '
                    .format(list(row.keys()), self._func_code))
            except Exception as e:
                raise type(e)(
                    'General exception in stats. headers = "{}", code = "{}": {} '
                        .format(list(row.keys()), self._func_code, e))

        # Use all of the rows in the source
        if self._sample_size is None:
            for i, row in enumerate(self._source):
                process_row(row)
        # Use a sample of rows, evenly distributed though the source
        else:

            skip_rate = self._sample_size / self._n_rows

            i = 0
            skip = skip_rate
            for j, row in enumerate(self._source):
                skip += skip_rate
                if skip >= 1:
                    skip -= 1
                    i += 1
                    process_row(row)

        if i < 5000:  # Since the hist bins aren't built until 5K row
            for k, v in self._stats.items():
                v._build_hist_bins()

        return self

    def __str__(self):
        from tabulate import tabulate

        rows = []

        delete_flags = not any(stats.dict.get('flags','').strip() for stats in self._stats.values() )

        for name, stats in self._stats.items():
            stats_dict = stats.dict

            if delete_flags:
                try:
                    del stats_dict['flags']
                except KeyError:
                    pass

            if 'text_hist' in stats_dict:
                stats_dict['hist'] = stats_dict['text_hist']
                del stats_dict['text_hist']

            if 'uvalues' in stats_dict:
                trunc_values = { k[:20] + (k[20:] and '..'):v for k,v in stats_dict['uvalues'].items()}
                stats_dict['uvalues'] = trunc_values

            if not rows:
                rows.append(list(stats_dict.keys()))

            rows.append(list(stats_dict.values()))


        if rows:
            table = tabulate(rows[1:], rows[0], tablefmt='pipe')
            return 'Statistics \n' + table
        else:
            return 'Statistics: None \n'


def _force_float(v):
    """ Converts given argument to float. On fail logs warning and returns 0.0.

    Args:
        v (any): value to convert to float

    Returns:
        float: converted v or 0.0 if conversion failed.

    """
    try:
        return float(v)
    except Exception as exc:
        return float('nan')
        logger.warning('Failed to convert {} to float with {} error. Using 0 instead.'.format(v, exc))
