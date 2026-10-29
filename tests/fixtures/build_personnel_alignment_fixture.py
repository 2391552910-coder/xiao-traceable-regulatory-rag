"""Regenerate the synthetic fixture; reportlab is needed only by this builder."""
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


def build(path):
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    pdf = canvas.Canvas(str(path), pagesize=(600, 800))
    xs = [40, 150, 300, 370, 430]
    rows = [['张三', '新任董事', '男', '53岁', '2024年9月至今'],
            ['李四', '退任董事', '女', '45岁', '2021年1月至2024年5月']]
    for count in (2, 1):
        pdf.setFont('STSong-Light', 10)
        for x, value in zip(xs, ['姓名', '职务', '性别', '年龄', '任期']):
            pdf.drawString(x, 740, value)
        for number, values in enumerate(rows[:count]):
            for x, value in zip(xs, values):
                pdf.drawString(x, 720 - number * 18, value)
        pdf.showPage()
    pdf.save()


if __name__ == '__main__':
    build(Path(__file__).with_name('personnel_alignment_synthetic.pdf'))
