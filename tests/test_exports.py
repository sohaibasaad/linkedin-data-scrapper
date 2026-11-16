import csv
import io
import unittest
from openpyxl import load_workbook
from exports import csv_bytes, excel_bytes
from search_engine import FIELDS


class ExportTests(unittest.TestCase):
    def test_csv_and_excel_formula_protection_and_columns(self):
        row = {key: 'value' for key in FIELDS}
        row['Name (from search title)'] = '=HYPERLINK("bad")'
        row['LinkedIn URL'] = 'https://www.linkedin.com/in/person'
        row['Search snippet'] = '\x00@SUM(1)'
        csv_data = list(csv.DictReader(io.StringIO(csv_bytes([row]).decode('utf-8-sig'))))
        self.assertEqual(list(csv_data[0]), FIELDS)
        self.assertTrue(csv_data[0]['Name (from search title)'].startswith("'="))
        self.assertTrue(csv_data[0]['Search snippet'].startswith("'@"))
        workbook = load_workbook(io.BytesIO(excel_bytes([row])))
        sheet = workbook.active
        self.assertEqual(sheet.max_row, 2)
        self.assertEqual(sheet.cell(2, 1).data_type, 's')
        self.assertEqual(sheet.cell(2, 2).hyperlink.target, row['LinkedIn URL'])
        self.assertEqual(sheet.auto_filter.ref, 'A1:K2')
        self.assertNotIn('Review status', [c.value for c in sheet[1]])
