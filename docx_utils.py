from docx import Document
from docx.shared import Cm, Pt
import os


def generate_table_setting_report(orders_data, filename="table_report.docx"):
    document = Document()

    sections = document.sections
    for section in sections:
        section.top_margin = Cm(0.5)
        section.bottom_margin = Cm(0.5)
        section.left_margin = Cm(0.5)
        section.right_margin = Cm(0.5)

    style = document.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(11)

    for order in orders_data:
        dishes_str = "+".join(order['dishes'])
        line_text = f"{order['user_name']} {order['user_class']}\t{dishes_str}"

        p = document.add_paragraph(line_text)
        p.paragraph_format.space_after = Pt(0)

    os.makedirs("reports", exist_ok=True)
    file_path = os.path.join("reports", filename)
    document.save(file_path)
    return file_path