"""Synthetic PDF fixture only; no real company report or real human judgment."""
import json
import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, NumberObject, DecodedStreamObject
from src.data.annual_reports import recover_reports
from scripts.extract_annual_facts import extract_manifest
from scripts.accept_annual_extraction import verify


def synthetic_pdf(path):
    text='SYNTHETIC FIXTURE ONLY. Fixture Company 000000 2024年年度报告。公司于报告期内召开董事会会议十二次并保存全部会议记录。'
    chars=list(dict.fromkeys(text));codes={c:i+1 for i,c in enumerate(chars)}
    cmap=DecodedStreamObject()
    cmap.set_data(('begincmap\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n'+str(len(chars))+' beginbfchar\n'+
                   '\n'.join(f'<{codes[c]:04X}> <{c.encode("utf-16-be").hex()}>' for c in chars)+'\nendbfchar\nendcmap').encode())
    descendant=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/CIDFontType2'),
                                  NameObject('/BaseFont'):NameObject('/Fixture'),NameObject('/DW'):NumberObject(500)})
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type0'),
                           NameObject('/BaseFont'):NameObject('/Fixture'),NameObject('/Encoding'):NameObject('/Identity-H'),
                           NameObject('/DescendantFonts'):ArrayObject([descendant]),NameObject('/ToUnicode'):cmap})
    writer=PdfWriter();page=writer.add_blank_page(width=1200,height=400)
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    content=DecodedStreamObject();content.set_data(('BT /F1 10 Tf 10 300 Td <'+''.join(f'{codes[c]:04X}' for c in text)+'> Tj ET').encode())
    page[NameObject('/Contents')]=content
    writer.write(path)


def test_synthetic_pdf_import_extract_verify_and_tamper_detection(tmp_path):
    source=tmp_path/'source';source.mkdir();synthetic_pdf(source/'000000_2024.pdf')
    company={'stock_code':'000000.SZ','name':'FixtureCompany','year':2024}
    result=recover_reports([company],2024,tmp_path/'recovered',source)
    assert result['identity_verified_reports']==1
    extraction=extract_manifest(tmp_path/'recovered/download_report.csv',tmp_path/'extracted')
    assert extraction['documents_processed']==1 and extraction['verified_fact_count']==0
    folder=tmp_path/'extracted/000000.SZ';pdf=result['rows'][0]['file']
    checked=verify(pdf,company,folder)
    assert checked['candidates']>=1 and checked['verified_facts']==0
    page=folder/'page_0001.txt';page.write_text(page.read_text()+'tampered')
    with pytest.raises(ValueError,match='page_text_hash'):verify(pdf,company,folder)
