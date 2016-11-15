# -*- coding: utf-8 -*-
# Copyright (c) 2016 Civic Knowledge. This file is licensed under the terms of the
# MIT License, included in this distribution as LICENSE.txt

"""
Old code for matching headers across files where the headers may have changed.

"""

class ClusterHeaders(object):
    """Using Source table headers, cluster the source tables into destination tables"""

    def __init__(self, bundle=None):
        self._bundle = bundle
        self._headers = {}

    def match_headers(self, a, b):
        from difflib import ndiff
        from collections import Counter

        c = Counter(e[0] for e in ndiff(a, b) if e[0] != '?')

        same = c.get(' ', 0)
        remove = c.get('-', 0)
        add = c.get('+', 0)

        return float(remove+add) / float(same)

    def match_headers_a(self, a, b):
        from difflib import SequenceMatcher

        for i, ca in enumerate(a):
            for j, cb in enumerate(b):
                r = SequenceMatcher(None, ca, cb).ratio()

                if r > .9:
                    print(ca, cb)
                    break

    def add_header(self, name, headers):
        self._headers[name] = headers

    def pairs(self):
        return set([(name1, name2) for name1 in list(self._headers) for name2 in list(self._headers) if name2 > name1])

    @classmethod
    def long_substr(cls, data):
        data = list(data)
        substr = ''
        if len(data) > 1 and len(data[0]) > 0:
            for i in range(len(data[0])):
                for j in range(len(data[0]) - i + 1):
                    if j > len(substr) and cls.is_substr(data[0][i:i + j], data):
                        substr = data[0][i:i + j]
        return substr

    @classmethod
    def is_substr(cls, find, data):
        if len(data) < 1 and len(find) < 1:
            return False
        for i in range(len(data)):
            if find not in data[i]:
                return False
        return True

    def cluster(self):

        pairs = self.pairs()

        results = []
        for a, b_ in pairs:
            results.append((round(self.match_headers(self._headers[a], self._headers[b_]), 3), a, b_))

        results = sorted(results, key=lambda r: r[0])

        clusters = []

        for r in results:
            if r[0] < .3:
                a = r[1]
                b = r[2]
                allocated = False
                for c in clusters:
                    if a in c or b in c:
                        c.add(a)
                        c.add(b)
                        allocated = True
                        break
                if not allocated:
                    ns = set([a, b])
                    clusters.append(ns)

        d = {self.long_substr(c).strip('_'): sorted(c) for c in clusters}

        return d


