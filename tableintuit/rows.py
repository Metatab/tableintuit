# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

"""

Guess the whether rows in a collection are header, comments, footers, etc


"""

from six import binary_type, text_type
import re


import logging
logger = logging.getLogger(__name__)


class RowIntuiter(object):

    """ Intuit row types.

    This intuiter works by converting each row into a picture, a string that has
    a character for each column to represent key datatypes:

    _ for blanks
    n for numbers
    X for everything else

    After creating a picture for a line, the intuiter tries to match it to regular expressions for
    each line type. Most of the types are hard coded, but the intuiter will also load rows from
    the middle of the rowset and try to extract a general patter to match data. Then it uses that
    data pattern to find where the data rows start and end.


    """

    N_TEST_ROWS = 150

    type_map = {
        text_type: binary_type,
        float: int}

    def __init__(self, debug = False):
        self.comment_lines = []
        self.header_lines = []
        self.start_line = 0
        self.end_line = None

        self.data_pattern_source = None

        self.patterns = (
            ('B', re.compile(r'^_+$')),  # Blank
            ('C', re.compile(r'^XX_+$')),  # Comment
            ('C', re.compile(r'^X_+$')),  # Comment
            ('H', re.compile(r'^X+$')),  # Header
            ('H', re.compile(r'^_{,6}X+$')),  # Header, A few starting blanks, the rest are strings.
            ('H', re.compile(r"(?:X_)")),  # Header
        )

        self.test_rows = []

        self.debug = debug

        if debug:
            logger.setLevel(logging.DEBUG)

    @property
    def spec(self):
        """Return a dict with values that can be fed directly into SelectiveRowGenerator"""
        return dict(
            headers=self.header_lines,
            start=self.start_line,
            comments=self.comment_lines,
            end=self.end_line
        )

    def picture(self, row):
        """Create a simplified character representation of the data row, which can be pattern matched
        with a regex """

        template = '_Xn'
        types = (type(None), binary_type, int)

        def guess_type(v):

            try:
                v = text_type(v).strip()
            except ValueError:
                v = binary_type(v).strip()
                #v = v.decode('ascii', 'replace').strip()

            if not bool(v):
                return type(None)

            for t in (float, int, binary_type, text_type):
                try:
                    return type(t(v))
                except:
                    pass

        def p(e):
            tm = t = None

            try:
                t = guess_type(e)
                tm = self.type_map.get(t, t)
                return template[types.index(tm)]
            except ValueError as e:
                raise ValueError("Type '{}'/'{}' not in the types list: {} ({})".format(t, tm, types, e))

        return ''.join(p(e) for e in row)

    def _data_pattern_source(self, rows, change_limit=5):

        l = max(len(row) for row in rows)  # Length of longest row

        patterns = [set() for _ in range(l)]

        contributors = 0  # Number  of rows that contributed to pattern.

        for j, row in enumerate(rows):

            changes = sum(1 for i, c in enumerate(self.picture(row)) if c not in patterns[i])

            # The pattern should stabilize quickly, with new rows not changing many cells. If there is
            # a large change, ignore it, as it may be spurious
            if j > 0 and changes > change_limit:
                continue

            contributors += 1

            for i, c in enumerate(self.picture(row)):
                patterns[i].add(c)

        pattern_source = ''.join("(?:{})".format('|'.join(s)) for s in patterns)

        return pattern_source, contributors, l

    def data_pattern(self, rows):

        tests = 50
        test_rows = min(20, len(rows))

        def try_tests(tests, test_rows, rows):
            # Look for the first row where you can generate a data pattern that does
            # not have a large number of changes in subsequent rows.
            for i in range(tests):

                max_changes = len(rows[0]) / 4  # Data row should have fewer than 25% changes compared to next

                test_rows_slice = rows[i: i + test_rows]

                if not test_rows_slice:
                    continue

                pattern_source, contributors, l = self._data_pattern_source(test_rows_slice, max_changes)

                ave_cols = sum(1 for r in test_rows_slice for c in r) / len(test_rows_slice)

                # If more the 75% of the rows contributed to the pattern, consider it good
                if contributors > test_rows * .75:
                    return pattern_source, ave_cols

            return (None, None)

        pattern_source, ave_cols = try_tests(tests, test_rows, rows)

        if not pattern_source:
            from .exceptions import RowIntuitError
            raise RowIntuitError('Failed to find data pattern')

        pattern = re.compile(pattern_source)

        return pattern, pattern_source, ave_cols

    @staticmethod
    def match_picture(picture, patterns):
        for l, r in patterns:
            if r.search(picture):
                return l

        return False

    def run(self, head_rows, tail_rows=None, n_rows=None):
        """
        Run the intuition process
        :param head_rows: A list of rows from the start of the file. Should have at least 30 rows
        :param tail_rows: A list of rows from the end of the file. Optional, but should have at least 30 rows
        :param n_rows: Total number of rows, if a subset was provided in head_rows
        :return:
        """

        from .exceptions import RowIntuitError

        header_rows = []
        found_header = False
        MIN_SKIP_ROWS = 30

        try:
            data_pattern_skip_rows = min(MIN_SKIP_ROWS, len(head_rows) - 8)

        except TypeError:
            # Hopefully b/c head_rows is a generator, not a sequence
            raise RowIntuitError("Head_rows must be a sequence, not a generator or iterator")


        try:
            data_pattern, self.data_pattern_source, n_cols = self.data_pattern(head_rows[data_pattern_skip_rows:])
        except Exception as e:
            logger.debug("Failed to find data pattern")
            raise

        patterns = ([('D', data_pattern),
                     # More than 25% strings in row is header, if it isn't matched as data
                     ('H', re.compile(r'X{{{},{}}}'.format(max(3, n_cols/8),max(3,n_cols/4)))),
                     ] +
                    list(self.patterns))

        if self.debug:

            logger.debug("--- Patterns")
            for e in patterns:
                logger.debug("    {} {}".format(e[0], e[1].pattern))

        for i, row in enumerate(head_rows):

            picture = self.picture(row)

            label = self.match_picture(picture, patterns)

            try:
                # If a header or data has more than half of the line is a continuous nulls,
                # it's probably a comment.
                if label != 'B' and len(re.search('_+', picture).group(0)) > len(row)/2:
                    label = 'C'
            except AttributeError:
                pass  # re not matched

            if not found_header and label == 'H':
                found_header = True

            if label is False:

                if found_header:
                    label = 'D'
                else:
                    # Could be a really wacky header
                    found_header = True
                    label = 'H'

            if self.debug:
                logger.debug("HEAD: {:<5} {} {} {}".format(i, label, picture, row))

            if label == 'C':
                self.comment_lines.append(i)

            elif label == 'H':
                self.header_lines.append(i)
                header_rows.append(row)

            elif label == 'D':
                self.start_line = i
                self.headers = self.coalesce_headers(header_rows)
                break

        if tail_rows:
            from itertools import takewhile, islice

            for i, row in enumerate(islice(reversed(tail_rows), 0, 10)):
                picture = self.picture(row)
                label = self.match_picture(picture, patterns)
                logger.debug("TAIL: {:<5} {} {} {}".format(i, label, picture, row))

            # Compute the data label for the end line, then reverse them.
            labels = reversed(list(self.match_picture(self.picture(row), patterns) for row in tail_rows))

            # Count the number of lines, from the end, that are either comment or blank
            end_line = len(list(takewhile(lambda x: x == 'C' or x == 'B' or x == 'H', labels)))

            if end_line:
                self.end_line = n_rows-end_line-1

        return self

    @classmethod
    def coalesce_headers(cls, header_lines):
        """Collects headers that are spread across multiple lines into a single row"""

        header_lines = [list(hl) for hl in header_lines if bool(hl)]

        if len(header_lines) == 0:
            return []

        if len(header_lines) == 1:
            return header_lines[0]

        # If there are gaps in the values of a line, copy them forward, so there
        # is some value in every position
        for hl in header_lines:
            last = None
            for i in range(len(hl)):
                hli = text_type(hl[i])
                if not hli.strip():
                    hl[i] = last
                else:
                    last = hli

        headers = [' '.join(text_type(col_val).strip() if col_val else '' for col_val in col_set)
                   for col_set in zip(*header_lines)]

        headers = [slugify(h.strip()) for h in headers]

        return headers

# From http://stackoverflow.com/a/295466
def slugify(value):
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.type(
    """
    import re
    import unicodedata
    from six import text_type
    value = text_type(value)
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('utf8')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    value = re.sub(r'[-\s]+', '_', value)
    return value
