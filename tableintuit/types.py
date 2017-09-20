# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

"""

Guess the whether rows in a collection are header, comments, footers, etc

"""

from collections import deque, OrderedDict
import datetime

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from six import string_types, iteritems, binary_type, text_type, b


class NoMatchError(Exception):
    pass


class unknown(binary_type):

    __name__ = 'unknown'

    def __new__(cls):
        return super(unknown, cls).__new__(cls, cls.__name__)

    def __str__(self):
        return self.__name__

    def __eq__(self, other):
        return binary_type(self) == binary_type(other)

class geotype(binary_type):

    __name__ = 'geo'

    def __new__(cls):
        return super(geotype, cls).__new__(cls, cls.__name__)

    def __str__(self):
        return self.__name__

    def __eq__(self, other):
        return binary_type(self) == binary_type(other)


def test_float(v):
    # Fixed-width integer codes are actually strings.
    # if v and v[0]  == '0' and len(v) > 1:
    # return 0

    try:
        float(v)
        return 1
    except:
        return 0


def test_int(v):
    # Fixed-width integer codes are actually strings.
    # if v and v[0] == '0' and len(v) > 1:
    # return 0

    try:
        if float(v) == int(float(v)):
            return 1
        else:
            return 0
    except:
        return 0


def test_string(v):
    if isinstance(v, string_types):
        return 1
    if isinstance(v, binary_type):
        return 1
    else:
        return 0


def test_datetime(v):
    """Test for ISO datetime."""
    if not isinstance(v, string_types):
        return 0

    if len(v) > 22:
        # Not exactly correct; ISO8601 allows fractional seconds
        # which could result in a longer string.
        return 0

    if '-' not in v and ':' not in v:
        return 0

    for c in set(v):  # Set of Unique characters
        if not c.isdigit() and c not in 'T:-Z':
            return 0

    return 1


def test_time(v):
    if not isinstance(v, string_types):
        return 0

    if len(v) > 15:
        return 0

    if ':' not in v:
        return 0

    for c in set(v):  # Set of Unique characters
        if not c.isdigit() and c not in 'T:Z.':
            return 0

    return 1


def test_date(v):
    if not isinstance(v, string_types):
        return 0

    if len(v) > 10:
        # Not exactly correct; ISO8601 allows fractional seconds
        # which could result in a longer string.
        return 0

    if '-' not in v:
        return 0

    for c in set(v):  # Set of Unique characters
        if not c.isdigit() and c not in '-':
            return 0

    return 1

def test_geo(v):

    return 0


tests = [
    (int, test_int),
    (float, test_float),
    (binary_type, test_string),
    (geotype, test_geo)
]


class Column(object):
    position = None
    header = None
    type_counts = None
    type_ratios = None
    length = 0
    count = 0
    strings = None

    def __init__(self):
        self.type_counts = {k: 0 for k, v in tests}
        self.type_counts[datetime.datetime] = 0
        self.type_counts[datetime.date] = 0
        self.type_counts[datetime.time] = 0
        self.type_counts[None] = 0
        self.type_counts[text_type] = 0
        self.strings = deque(maxlen=1000)
        self.position = None
        self.header = None
        self.count = 0
        self.length = 0
        self.date_successes = 0
        self.description = None

    def inc_type_count(self, t):
        self.type_counts[t] += 1

    def test(self, v):
        from dateutil import parser

        self.count += 1

        if v is None:
            self.type_counts[None] += 1
            return None

        try:
            v = '{}'.format(v).encode('ascii')
        except UnicodeEncodeError:
            self.type_counts[text_type] += 1
            return text_type

        self.length = max(self.length, len(v))

        try:
            v = v.strip()
        except AttributeError:
            pass

        if v == '':
            self.type_counts[None] += 1
            return None

        for test, testf in tests:
            t = testf(v)

            if t > 0:
                type_ = test

                if test == binary_type:
                    if v not in self.strings:
                        self.strings.append(v)

                    if (self.count < 1000 or self.date_successes != 0) and any((c in b('-/:T')) for c in v):
                        try:
                            maybe_dt = parser.parse(v, default=datetime.datetime.fromtimestamp(0))
                        except (TypeError, ValueError, OSError): # Windows throws an OSError
                            maybe_dt = None

                        if maybe_dt:
                            # Check which parts of the default the parser didn't change to find
                            # the real type
                            # HACK The time check will be wrong for the time of
                            # the start of the epoch, 16:00.
                            if maybe_dt.time() == datetime.datetime.fromtimestamp(0).time():
                                type_ = datetime.date
                            elif maybe_dt.date() == datetime.datetime.fromtimestamp(0).date():
                                type_ = datetime.time
                            else:
                                type_ = datetime.datetime

                            self.date_successes += 1

                self.type_counts[type_] += 1

                return type_

    def _resolved_type(self):
        """Return the type for the columns, and a flag to indicate that the
        column has codes."""
        import datetime

        self.type_ratios = {test: (float(self.type_counts[test]) / float(self.count)) if self.count else None
                            for test, testf in tests + [(None, None)]}

        # If it is more than 5% str, it's a str

        try:
            if self.type_ratios.get(text_type,0) + self.type_ratios.get(binary_type,0) > .05:
                if self.type_counts[text_type] > 0:
                    return text_type, False

                elif self.type_counts[binary_type] > 0:
                    return binary_type, False
        except TypeError as e:
            # This is probably the result of the type being unknown
            pass


        if self.type_counts[datetime.datetime] > 0:
            num_type = datetime.datetime

        elif self.type_counts[datetime.date] > 0:
            num_type = datetime.date

        elif self.type_counts[datetime.time] > 0:
            num_type = datetime.time

        elif self.type_counts[float] > 0:
            num_type = float

        elif self.type_counts[int] > 0:
            num_type = int

        elif self.type_counts[text_type] > 0:
            num_type = text_type

        elif self.type_counts[binary_type] > 0:
            num_type = binary_type

        else:
            num_type = unknown

        if self.type_counts[binary_type] > 0 and num_type != binary_type:
            has_codes = True
        else:
            has_codes = False

        return num_type, has_codes

    @property
    def resolved_type(self):
        return self._resolved_type()[0]

    @property
    def resolved_type_name(self):
        try:
            return self.resolved_type.__name__
        except AttributeError:
            return self.resolved_type

    @property
    def has_codes(self):
        return self._resolved_type()[1]

    def __repr__(self):
        return "<Column {} {} {}>".format(self.position, self.header, self.resolved_type_name)

class TypeIntuiter(object):
    """Determine the types of rows in a table."""
    header = None
    counts = None

    def __init__(self):
        self._columns = OrderedDict()

    def process_header(self, row):

        header = row # Huh? Don't remember what this is for.

        for i, value in enumerate(row):
            if i not in header:
                self._columns[i] = Column()
                self._columns[i].position = i
                self._columns[i].header = value

        return self

    def process_row(self, n, row):

        for i, value in enumerate(row):
            try:
                if i not in self._columns:
                    self._columns[i] = Column()
                    self._columns[i].position = i
                self._columns[i].test(value)

            except Exception as e:
                # This usually doesn't matter, since there are usually plenty of other rows to intuit from
                # print 'Failed to add row: {}: {} {}'.format(row, type(e), e)
                print(i, value, e)
                raise

    def run(self, source, total_rows=None):

        MIN_SKIP_ROWS = 10000

        if total_rows and total_rows > MIN_SKIP_ROWS:
            skip_rows = int(total_rows / MIN_SKIP_ROWS)

            skip_rows = skip_rows if skip_rows > 1 else None

        else:
            skip_rows = None

        for i, row in enumerate(iter(source)):
            if skip_rows and i % skip_rows != 0:
                continue

            if i == 0:
                self.process_header(row)
                continue

            self.process_row(i, row)

        return self

    @property
    def columns(self):
        return self._columns

    def __getitem__(self, item):

        try:
            return self._columns[item]
        except KeyError:
            for k, v in self._columns.items():
                if item == v.header:
                    return v

        raise KeyError(item)

    @property
    def is_ascii(self):
        """return true if none of the columns have a resolved type of """
        pass


    def __str__(self):
        from tabulate import tabulate

        # return  SingleTable([[ str(x) for x in row] for row in self.rows] ).table

        results = self.results_table()


        if len(results) > 1:
            o = '\n' + text_type(tabulate(results[1:], results[0], tablefmt='pipe'))
        else:
            o = ''

        return 'TypeIntuiter ' + o

    @staticmethod
    def normalize_type(typ):

        if isinstance(typ, string_types):
            import datetime

            m = dict(list(__builtins__.items()) + list(datetime.__dict__.items()))
            if typ == 'unknown':
                typ = binary_type
            else:
                typ = m[typ]

        return typ

    @staticmethod
    def promote_type(orig_type, new_type):
        """Given a table with an original type, decide whether a new determination of a new applicable type
        should overide the existing one"""

        if not new_type:
            return orig_type

        if not orig_type:
            return new_type

        try:
            orig_type = orig_type.__name__
        except AttributeError:
            pass

        try:
            new_type = new_type.__name__
        except AttributeError:
            pass

        type_precidence = ['unknown', 'int', 'float', 'date', 'time', 'datetime', 'str', 'bytes', 'unicode']

        # TODO This will fail for dates and times.

        if type_precidence.index(new_type) > type_precidence.index(orig_type):
            return new_type
        else:
            return orig_type

    def results_table(self):

        fields = 'position header length resolved_type has_codes count ints floats strs unicode nones datetimes dates times '.split()

        header = list(fields)
        # Shorten a few of the header names
        header[0] = '#'
        header[2] = 'size'
        header[4] = 'codes'
        header[9] = 'uni'
        header[11] = 'dt'

        rows = list()

        rows.append(header)

        for d in self.to_rows():
            rows.append([d[k] for k in fields])

        return rows

    def to_rows(self):

        for k,v in self.columns.items():
            d = {
                'position': v.position,
                'header': v.header,
                'length': v.length,
                'resolved_type': v.resolved_type_name,
                'has_codes': v.has_codes,
                'count': v.count,
                'ints': v.type_counts.get(int, None),
                'floats': v.type_counts.get(float, None),
                'strs': v.type_counts.get(binary_type, None),
                'unicode': v.type_counts.get(text_type, None),
                'nones': v.type_counts.get(None, None),
                'datetimes': v.type_counts.get(datetime.datetime, None),
                'dates': v.type_counts.get(datetime.date, None),
                'times': v.type_counts.get(datetime.time, None),
                'strvals': b(',').join(list(v.strings)[:20])
            }
            yield d


