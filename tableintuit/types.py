# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

"""

Guess the whether rows in a collection are header, comments, footers, etc

"""
import numpy as np
import datetime
import logging
import math
from collections import deque, OrderedDict, defaultdict

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class NoMatchError(Exception):
    pass


class unknown(bytes):
    __name__ = 'unknown'

    def __new__(cls):
        return super(unknown, cls).__new__(cls, cls.__name__)

    def __str__(self):
        return self.__name__

    def __eq__(self, other):
        return bytes(self) == bytes(other)


class geotype(bytes):
    __name__ = 'geo'

    def __new__(cls):
        return super(geotype, cls).__new__(cls, cls.__name__)

    def __str__(self):
        return self.__name__

    def __eq__(self, other):
        return bytes(self) == bytes(other)

nans = ['#N/A', '#N/A', 'N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan',
        '1.#IND', '1.#QNAN', 'NA', 'NULL', 'NaN', 'n/a', 'nan', 'null']

def test_nan(v):
    from math import isnan

    if isinstance(v, bool):
        return False

    elif isinstance(v, str):
        if v in nans:
            return math.nan

    elif isinstance(v, float) and isnan(v):
        return math.nan

    return False


def test_float(v):
    # Fixed-width integer codes are actually strings.
    # if v and v[0]  == '0' and len(v) > 1:
    # return 0

    if isinstance(v, (bool, np.ndarray)):
        return False
    try:
        float(v)
        return float
    except:
        return False


def test_int(v):
    # Fixed-width integer codes are actually strings.
    # if v and v[0] == '0' and len(v) > 1:
    # return 0

    if isinstance(v, (bool, np.ndarray)):
        return False

    try:
        if float(v) == int(float(v)) :
            return int
        else:
            return False
    except:
        return False


def test_string(v):
    if isinstance(v, str):
        return str
    else:
        return False


def test_datetime(v):
    """"""
    from dateutil import parser

    try:
        dt = parser.parse(v)

        if dt.time() == datetime.datetime.fromtimestamp(0).time():
            type_ = datetime.date
        elif dt.date() == datetime.datetime.fromtimestamp(0).date():
            type_ = datetime.time
        else:
            type_ = datetime.datetime

        return type_
    except:
        return False


def test_geo(v):
    return False


def test_none(v):
    if v is None:
        return None
    else:
        return False


def test_ascii(v):
    try:
        v.encode('ascii')
        return True
    except:
        return False


def test_latin1(v):
    try:
        v.encode('latin1')
        return True
    except:
        return False

def test_object(v):
    if isinstance(v, object):
        return object
    else:
        return False

def test_ndarray(v):
    if isinstance(v, np.ndarray):
        return np.ndarray
    else:
        return False

def test_bool(v):
    return isinstance(v, bool) and bool

tests = [
    (None, test_none),
    (math.nan, test_nan),
    (int, test_int),
    (float, test_float),
    (datetime.datetime, test_datetime),
    (str, test_string),
    (geotype, test_geo),
    (np.ndarray, test_ndarray),
    (bool, test_bool),
    (object, test_object),

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
        self.type_counts = defaultdict(int)
        self.str_type_counts = defaultdict(int)
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

        self.count += 1

        for test, testf in tests:
            type_ = testf(v)
            #print(test, testf, type_)
            if type_ is not False:

                if type_ is str:

                    if v not in self.strings:
                        self.strings.append(v)

                    self.str_type_counts['ascii'] += test_ascii(v)
                    self.str_type_counts['latin1'] += test_latin1(v)
                    self.length = max(self.length, len(v))

                self.type_counts[type_] += 1

                return type_

        return unknown



    def _resolved_type(self):
        """Return the type for the columns, and a flag to indicate that the
        column has codes."""
        import datetime

        self.type_ratios = {test: (float(self.type_counts[test]) / float(self.count)) if self.count else None
                            for test, testf in tests + [(None, None)]}

        # If it is more than 5% str, it's a str

        try:
            if self.type_ratios.get(str, 0) + self.type_ratios.get(bytes, 0) > .05:
                if self.type_counts[str] > 0:
                    return str, False

        except TypeError as e:
            # This is probably the result of the type being unknown
            pass

        for type_ in TypeIntuiter.type_order.keys():

            if self.type_counts[type_] > 0:
                col_type = type_

        if self.type_counts[str] > 0 and col_type != str:
            has_codes = True
        else:
            has_codes = False

        return col_type, has_codes

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

    # Names of intuited types, and the order they appear in tables.
    type_order = {
         datetime.datetime: 'dt',
         datetime.date: 'date',
         datetime.time: 'time',
         float: 'float',
         int: 'int',
         str: 'str',
         bool: 'bool',
         np.ndarray: 'nda',
         object: 'obj',
         None: 'None'}

    def __init__(self):
        self._columns = OrderedDict()

    def process_header(self, row):

        header = row  # Huh? Don't remember what this is for.

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
            o = '\n' + str(tabulate(results[1:], results[0], tablefmt='pipe'))
        else:
            o = ''

        return 'TypeIntuiter ' + o

    @staticmethod
    def normalize_type(typ):

        if isinstance(typ, str):
            import datetime

            m = dict(list(__builtins__.items()) + list(datetime.__dict__.items()))
            if typ == 'unknown':
                typ = bytes
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

        fields = 'pos header len rtype codes N '.split()

        fields += [e for e in self.all_types]

        # Translate some of the names for the table header
        header = [self.type_order.get(e, e) for e in fields]

        rows = list()

        rows.append(header)

        for d in self.to_rows():
            try:
                rows.append([d[k] for k in fields])
            except KeyError:
                print(d)
                raise

        return rows

    @property
    def all_types(self):
        all_types = set()
        for c in self.columns.values():
            for type_, n in c.type_counts.items():
                if n > 0:
                    all_types.add(type_)

        return [ e for e in self.type_order.keys() if e in all_types]

    def to_rows(self):
        all_types = self.all_types

        for k, v in self.columns.items():
            d = {
                'pos': v.position,
                'header': v.header,
                'len': v.length,
                'rtype': v.resolved_type_name,
                'codes': v.has_codes,
                'N': v.count,
            }

            for type_ in all_types:
                d[type_] = v.type_counts[type_]

            d['strvals'] =  ','.join(list(v.strings)[:20])

            yield d
