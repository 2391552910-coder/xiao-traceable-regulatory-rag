import pytest
from scripts.audit_date_evidence import signed_date


def test_footer_date_is_typed_and_exactly_locatable():
    text = '违法发生于2001年1月2日。\n中国证券监督管理委员会\n二○○四年十二月三十一日'
    result = signed_date(text)
    assert result['value'] == '2004-12-31'
    assert result['date_type'] == 'decision_signing_date'
    assert text[result['source_start']:result['source_end']] == result['quote']


def test_body_event_dates_and_unsigned_dates_are_not_accepted():
    assert signed_date('中国证券监督管理委员会调查2004年1月1日的交易。') is None
    assert signed_date('2004年1月1日') is None


def test_impossible_dates_rejected():
    with pytest.raises(ValueError):
        signed_date('中国证券监督管理委员会\n二○○四年二月三十日')
