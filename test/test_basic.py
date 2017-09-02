import unittest

from appurl import parse_app_url
from csv import DictReader
from rowgenerators import get_generator, SelectiveRowGenerator
from tableintuit import RowIntuiter, RowIntuitError
from tableintuit import TypeIntuiter, Stats

def df(*v):
    """Return a path to a test data file"""
    from os.path import dirname, join

    return join(dirname(__file__), 'test_data', *v)


class BasicTest(unittest.TestCase):

    def test_row_intuition(self):



        with open(df('rows', 'sources.csv')) as f:
            for e in DictReader(f):

                path = df('rows', e['path'])

                gen = get_generator(parse_app_url(path).get_resource().get_target())

                rows = list(gen)
                self.assertEquals(int(e['rows']), len(rows))

                ri = RowIntuiter()
                ri.run(rows)

                self.assertEqual(int(e['start']), ri.start_line)
                self.assertEqual(e['comments'], ','.join(str(e) for e in ri.comment_lines))
                self.assertEqual(e['headers'], ','.join(str(e) for e in ri.header_lines))

    def test_row_intuition_rowgen(self):
        """Like test_row_intuition, but the dict read rows from the csv file
        are direct input to a RowGenerator"""
        from csv import DictReader

        with open(df('rowgen_sources.csv')) as f:
            for e in DictReader(f):
                print(e['name'])
                gen = get_generator(e['url'])

                rows = list(gen)

                self.assertEquals(int(e['n_rows']), len(rows))

                try:
                    ri = RowIntuiter()
                    ri.run(rows)
                except RowIntuitError as exc:
                    print("Error: ", e, exc)

                if e['expect_start']:
                    self.assertEqual(int(e['expect_start']), ri.start_line)

                if e['expect_headers']:
                    self.assertEquals(e['expect_headers'], ','.join(str(e) for e in ri.header_lines))

    def test_intuition_fails(self):

        from tableintuit import RowIntuiter

        url = 'http://public.source.civicknowledge.com/example.com/row_intuit/headers_1.csv'
        rg = get_generator(parse_app_url(url).get_resource().get_target())
        rows = list(rg)
        ri = RowIntuiter().run(rows)

        print(ri.start_line, ri.header_lines)

    def test_urltype(self):



        self.assertEqual('file', parse_app_url('/foo/bar.zip').proto)
        self.assertEqual('file', parse_app_url('file:///foo/bar.zip').proto)
        self.assertEqual('gs', parse_app_url('gs://foo/bar.zip').proto)
        self.assertEqual('socrata', parse_app_url('socrata://foo/bar.zip').proto)
        self.assertEqual('http', parse_app_url('http://foo/bar.zip').proto)
        self.assertEqual('http', parse_app_url('https://foo/bar.zip').proto)

        self.assertEqual('csv', parse_app_url('/foo/bar.csv').target_format)
        self.assertEqual('csv', parse_app_url('file:///foo/bar.zip#foobar.csv').target_format)
        self.assertEqual('file', parse_app_url('file:///foo/bar.zip#foobar.csv').proto)
        #self.assertEqual('csv', parse_app_url('gs://blahblahblah').target_format)

        self.assertEqual('csv', parse_app_url(
            'http://public.source.civicknowledge.com/example.com/sources/simple-example.csv.zip').get_target().target_format)

    def test_filetype(self):

        self.assertEqual('csv', parse_app_url('/foo/bar.csv').target_format)
        self.assertEqual('csv', parse_app_url('file:///foo/bar.zip#foobar.csv').target_format)
        #self.assertEqual('csv', parse_app_url('gs://foo/blahblahblah?foo=bar').target_format)

    def test_selective(self):
        from csv import DictReader
        from tableintuit import RowIntuiter
        from itertools import islice

        rows = [['header1']] + [['header2']] + [[i] for i in range(10)]

        rg = SelectiveRowGenerator(rows, start=5, headers=[0, 1], comments=[2, 3], end=9)

        self.assertEquals([[u'header1 header2'], [3], [4], [5], [6], [7], [8], [9]], list(rg))
        self.assertEqual([['header1'], ['header2']], rg.headers)
        self.assertEqual([[0], [1]], rg.comments)

        with open(df('rowgen_sources.csv')) as f:
            sources = {e['name']: e for e in DictReader(f)}

        rg = get_generator(sources['rentcsv']['url'])
        ri = RowIntuiter().run(list(rg))

        rows = list(islice(SelectiveRowGenerator(rg, **ri.spec), 100))

        # First row is the header
        self.assertEqual([u'id', u'gvid', u'renter cost_gt_30', u'renter cost_gt_30_cv', u'owner cost_gt_30_pct',
                          u'owner cost_gt_30_pct_cv'],
                         rows[0])

        # Second is the first data row, which is actually the 6th row in the file
        self.assertEqual([u'1', u'0O0P01', u'1447', u'13.6176070905', u'42.2481751825', u'8.272140707'],
                         rows[1])

    def test_type_intuition(self):

        from six import binary_type, text_type

        with open(df('stat_sources.csv')) as f:
            def proc_dict(d):
                if d['headers']:
                    d['headers'] = [int(e) for e in d['headers'].split(',')]
                if d['start']:
                    d['start'] = int(d['start'])
                return d

            sources = {e['name']: proc_dict(e) for e in DictReader(f)}

        def run_ti(e):
            rg = get_generator(e['url'])
            srg = SelectiveRowGenerator(rg, **e)
            rows = list(srg)
            ti = TypeIntuiter().run(rows)

            return ti

        ti = run_ti(sources['namesu8'])
        print(ti)
        self.assertEquals(binary_type, ti[0].resolved_type)
        self.assertEquals(binary_type, ti[1].resolved_type)
        self.assertEquals(52, ti[2].count)
        self.assertEquals(20, ti[2].type_counts[binary_type])
        self.assertEquals(32, ti[2].type_counts[text_type])
        self.assertEquals(text_type, ti[2].resolved_type)
        self.assertEquals(2, ti[3].type_counts[binary_type])
        self.assertEquals(50, ti[3].type_counts[text_type])
        self.assertEquals(text_type, ti[3].resolved_type)

        ti = run_ti(sources['types1'])
        self.assertEquals(13, ti['float'].type_counts[float])
        self.assertEquals(0, ti['float'].type_counts[int])
        self.assertEquals(0, ti['float'].type_counts[binary_type])
        self.assertEquals(0, ti['int'].type_counts[float])
        self.assertEquals(13, ti['int'].type_counts[int])
        self.assertEquals(0, ti['int'].type_counts[text_type])

    def test_stats(self):

        with open(df('stat_sources.csv')) as f:
            def proc_dict(d):
                if d['headers']:
                    d['headers'] = [int(e) for e in d['headers'].split(',')]
                if d['start']:
                    d['start'] = int(d['start'])
                return d

            sources = {e['name']: proc_dict(e) for e in DictReader(f)}

        for k, e in sources.items():

            rg = get_generator(e['url'])
            srg = SelectiveRowGenerator(rg, **e)
            rows = list(srg)
            print('----')
            print(e['name'])
            print(len(rows))
            print(rows[0])
            print(rows[1])

            ti = TypeIntuiter().run(rows)

            header = [c.header for k, c in ti.columns.items()]

            schema = [(c.header, c.resolved_type) for k, c in ti.columns.items()]

            stats = Stats(schema).run(dict(zip(header, row)) for row in rows)

            print(str(stats).encode('utf8'))




if __name__ == '__main__':
    unittest.main()
