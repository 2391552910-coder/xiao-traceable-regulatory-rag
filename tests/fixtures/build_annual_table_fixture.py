"""Reproducible synthetic PDF; contains no real company or human judgments."""
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas


def build(path):
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    pdf = canvas.Canvas(str(path), pagesize=(600, 800), invariant=1)
    bounds = [40, 120, 220, 320, 560]
    headers = ['委员会名称', '成员情况', '召开日期', '会议内容']

    def grid(top, bands, rows):
        pdf.setLineWidth(.7)
        for x in bounds:
            pdf.line(x, 800-top, x, 800-bands[-1])
        for y in [top] + bands:
            pdf.line(bounds[0], 800-y, bounds[-1], 800-y)
        pdf.setFont('STSong-Light', 9)
        for y, row in zip([top] + bands[:-1], rows):
            for x, text in zip(bounds, row):
                pdf.drawString(x + 4, 800-y-16, text)

    grid(600, [625, 750], [headers, ['审', '姚', '2024年9', '审计委员会会议']])
    pdf.showPage()
    grid(40, [100, 160], [['计委员会', '兴田、于舒天', '月19日', '续会'],
                          ['审计委员会', '孙健', '2024年10月18日', '审计委员会第二次会议']])
    pdf.showPage()
    grid(600, [625, 750], [headers, ['审计委员会', '王一', '2024年3月21日', '审计委员会第三次会议']])
    pdf.showPage()
    grid(40, [65, 140], [headers, ['审计委员会', '王一', '2024年4月19日', '审计委员会第四次会议']])
    pdf.showPage()
    pdf.setFont('STSong-Light', 9)
    pdf.drawString(60, 800-160, '董事出席会议情况')
    for x, text in [(60, '董事'), (220, '审计委员会'), (340, '薪酬委员会'), (470, '董事会')]:
        pdf.drawString(x, 800-195, text)
    for y, name, values in [(230, '张一', ['1/1', '/', '2/2']),
                             (260, '李二', ['/', '1/1', '2/2']),
                             (290, '王三', ['0/0', '1/1', '2/2'])]:
        pdf.drawString(60, 800-y, name)
        for x, value in zip([280, 400, 540], values):
            pdf.drawRightString(x, 800-y, value)
    pdf.showPage()
    # No text layer: the parser must request OCR/review rather than invent rows.
    pdf.setFillColorRGB(.95, .95, .95)
    pdf.rect(40, 100, 520, 600, fill=1, stroke=0)
    pdf.showPage()
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont('STSong-Light', 9)
    pdf.drawString(60, 620, '财务比率（不是委员会出席表）')
    for y in [230, 260, 290]:
        pdf.drawString(60, 800-y, '项目')
        for x in [280, 400, 540]:
            pdf.drawRightString(x, 800-y, '1/2')
    pdf.showPage()
    headers = ['会议届次','召开日期','会议决议','备注']
    grid(600,[625,750],[headers,['第一次会议','2024年9月19日','12. 开展工作','']])
    pdf.showPage()
    grid(40,[100,160],[['','','13. 延续内容',''],['第二次会议','2024年10月18日','审议报告','']])
    pdf.save()


if __name__ == '__main__':
    build(Path(__file__).with_name('annual_tables_synthetic_v1.pdf'))
