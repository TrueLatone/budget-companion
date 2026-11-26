from pathlib import Path
import json
import zipfile
import xml.etree.ElementTree as ET

root = Path(__file__).parent
out = root / 'extracted'
out.mkdir(exist_ok=True)
for path in (root / 'inputs').iterdir():
    lines = []
    if path.suffix == '.pdf':
        from pypdf import PdfReader
        for n, page in enumerate(PdfReader(path).pages, 1):
            lines.extend([f'PAGE {n}', page.extract_text()])
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if 'word/document.xml' in z.namelist():
                tree = ET.fromstring(z.read('word/document.xml'))
                ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                for p in tree.findall('.//w:p', ns):
                    lines.append(''.join(p.itertext()))
            elif 'content.xml' in z.namelist():
                tree = ET.fromstring(z.read('content.xml'))
                ns = {'t': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0', 'x': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
                for table in tree.findall('.//t:table', ns):
                    lines.append('SHEET ' + table.get('{'+ns['t']+'}name', ''))
                    for row in table.findall('t:table-row', ns):
                        cells = []
                        for c in row:
                            if c.tag not in ('{'+ns['t']+'}table-cell', '{'+ns['t']+'}covered-table-cell'):
                                continue
                            value = '\n'.join(''.join(p.itertext()) for p in c.findall('.//x:p',ns))
                            cells.extend([value] * min(30, int(c.get('{'+ns['t']+'}number-columns-repeated', '1'))))
                        if any(cells):
                            lines.append(json.dumps(cells, ensure_ascii=False))
            elif 'xl/workbook.xml' in z.namelist():
                ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                strings = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    for si in ET.fromstring(z.read('xl/sharedStrings.xml')):
                        strings.append(''.join(si.itertext()))
                for name in z.namelist():
                    if name.startswith('xl/worksheets/sheet') and name.endswith('.xml'):
                        lines.append('SHEET ' + name)
                        for row in ET.fromstring(z.read(name)).findall('.//s:row', ns):
                            cells = {}
                            for c in row.findall('s:c', ns):
                                v = c.find('s:v', ns)
                                val = v.text if v is not None else ''.join(c.find('s:is',ns).itertext()) if c.find('s:is',ns) is not None else ''
                                if c.get('t') == 's' and val:
                                    val = strings[int(val)]
                                if val:
                                    cells[c.get('r')] = val
                            if cells:
                                lines.append(json.dumps(cells, ensure_ascii=False))
    else:
        lines = [path.read_text(encoding='utf-8-sig', errors='replace')]
    (out / (path.name + '.txt')).write_text('\n'.join(lines), encoding='utf-8')
    print(path.name, len(lines))
