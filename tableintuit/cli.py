# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

"""

CLI program

"""

from __future__ import print_function
import sys

def main():
    import argparse
    import sys
    from tableintuit import __meta__, RowIntuiter
    from rowgenerators import RowGenerator
    from itertools import islice
    from collections import deque



    parser = argparse.ArgumentParser(
        prog='tintuit',
        description='Print a table, row or stats intuition report'.format(__meta__.__version__))

    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument('-r', '--rows', default=False, action='store_true',
                   help='Print header, comment and data row limits. ')
    g.add_argument('-t', '--types', default=False, action='store_true',
                   help='Print a types report')
    g.add_argument('-s', '--stats', default=False, action='store_true',
                   help='Print a stats report')
    g.add_argument('-H', '--head', default=False, action='store_true',
                   help='Print the head of the rows, up to three lines past the start of data. ')

    parser.add_argument('url', help='Path to file or a URL')

    args = parser.parse_args(sys.argv[1:])

    print(args)

    RI_HEAD_LENGTH=1000
    RI_TAIL_LENGTH=150

    rg = RowGenerator(url=args.url)

    head = islice(rg, None, RI_HEAD_LENGTH)
    tail = deque(rg, RI_TAIL_LENGTH)

    if len(tail) < RI_TAIL_LENGTH:
        diff = RI_TAIL_LENGTH-len(tail)
        if diff > len(head):
            tail = head + list(tail)
        else:
            tail = head[:-diff] + list(tail)

    ri = RowIntuiter().run(head, tail)

    print(ri)
