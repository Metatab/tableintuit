import unittest


def df(v):
    """Return a path to a test data file"""
    from os.path import dirname, join

    return join(dirname(__file__), 'test_data',v)

class BasicTest(unittest.TestCase):

    def test_basic(self):

        from csv import DictReader
        from rowgenerators import RowGenerator
        from tableintuit import TypeIntuiter, RowIntuiter

        with open(df('sources.csv')) as f:

            for e in DictReader(f):
                rows = list(RowGenerator(df(e['path'])))
                self.assertEquals( int(e['rows']), len(rows))

                ti = TypeIntuiter()
                ti.run(rows)

                self.assertEqual(int(e['columns']), len(list(ti.columns)) )

                ri = RowIntuiter()
                ri.run(rows)
                self.assertEqual(int(e['start']),  ri.start_line)
                self.assertEqual(e['comments'],  ','.join( str(e) for e in ri.comment_lines))
                self.assertEqual(e['headers'], ','.join(str(e) for e in ri.header_lines))

                print ri.end_line

    def test_urltype(self):

        from rowgenerators import RowGenerator as rg

        self.assertEqual('file', rg('/foo/bar.zip').urltype)
        self.assertEqual('file', rg('file:///foo/bar.zip').urltype)
        self.assertEqual('gs', rg('gs://foo/bar.zip').urltype)
        self.assertEqual('socrata', rg('socrata://foo/bar.zip').urltype)
        self.assertEqual('http', rg('http://foo/bar.zip').urltype)
        self.assertEqual('http', rg('https://foo/bar.zip').urltype)

    def test_urlfiletype(self):
        from rowgenerators import RowGenerator as rg

        self.assertEqual('csv', rg('/foo/bar.csv').filetype)
        self.assertEqual('zip', rg('file:///foo/bar.zip#foobar.csv').filetype)
        self.assertEqual('xls', rg('gs://foo/bar.xls?foo=bar').filetype)

    def test_filetype(self):

        from rowgenerators import RowGenerator as rg

        self.assertEqual('csv', rg('/foo/bar.csv').filetype)
        self.assertEqual('csv', rg('file:///foo/bar.zip#foobar.csv').filetype)
        self.assertEqual('xls', rg('gs://foo/bar.xls?foo=bar').filetype)


if __name__ == '__main__':
    unittest.main()
