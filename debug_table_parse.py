"""Debug Word XML table parsing"""
from xml.dom import minidom

# 读取 Word XML
xml_path = r"D:\溯源\报告模板\unpacked_2025年7月16日臭氧垂直\word\document.xml"

with open(xml_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 解析 XML
doc = minidom.parseString(content)

# 查找所有表格
tables = doc.getElementsByTagName('w:tbl')
with open('table_debug.txt', 'w', encoding='utf-8') as f:
    f.write(f"Found {len(tables)} tables\n\n")

    # 打印所有表格
    for table_idx, table in enumerate(tables):
        f.write(f"\n{'='*80}\n")
        f.write(f"Table {table_idx + 1}:\n\n")

        # 提取表格行和单元格
        rows = table.getElementsByTagName('w:tr')
        f.write(f"Table has {len(rows)} rows\n\n")

        for i, row in enumerate(rows[:10]):  # 只看前 10 行
            cells = row.getElementsByTagName('w:tc')
            row_texts = []

            for j, cell in enumerate(cells):
                # 获取单元格文本
                texts = cell.getElementsByTagName('w:t')
                cell_text = ''.join([t.firstChild.nodeValue if t.firstChild else '' for t in texts])

                if cell_text.strip():
                    row_texts.append(f"Cell[{j}]: {cell_text.strip()}")

            f.write(f"Row {i+1} ({len(cells)} cells):\n")
            for text in row_texts:
                f.write(f"  {text}\n")
            f.write("\n")

print("Output saved to table_debug.txt")
