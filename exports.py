"""Spreadsheet exports with formula-injection protection."""
import csv
import io
import re

from search_engine import FIELDS


def safe_cell(value):
    text = str(value if value is not None else '')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    if text.lstrip().startswith(('=', '+', '-', '@')):
        text = "'" + text
    return text


def csv_bytes(rows):
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction='ignore')
    writer.writeheader()
    writer.writerows({key: safe_cell(row.get(key, '')) for key in FIELDS} for row in rows)
    return output.getvalue().encode('utf-8-sig')


def excel_bytes(rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Candidates'
    sheet.append(FIELDS)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='173B57')
    for row in rows:
        sheet.append([safe_cell(row.get(key, ''))[:32767] for key in FIELDS])
        for cell in sheet[sheet.max_row]:
            cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        link = sheet.cell(sheet.max_row, 2)
        # URLs have already passed search_engine.normalize_profile_url.
        if link.value.startswith('https://www.linkedin.com/in/'):
            link.hyperlink = link.value
            link.style = 'Hyperlink'
    sheet.freeze_panes = 'C2'
    sheet.auto_filter.ref = sheet.dimensions
    for i in range(1, len(FIELDS) + 1):
        sheet.column_dimensions[get_column_letter(i)].width = 28 if i == 1 else 55
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
