from app.hareruya import contains_card, parse_page

def test_exact_name_matching():
    assert contains_card('《Tithe》[VIS]','Tithe')
    assert contains_card('《税収/Tithe》[VIS]','Tithe')
    assert not contains_card('《Blood Tithe》[M11]','Tithe')
    assert not contains_card('《Smothering Tithe》[RNA]','Tithe')

def test_art_card_ignored():
    html='<div class="result_pagenum">Page 1 / 1</div><div class="itemData"><a class="itemName">《Tithe Art Card》[VIS]</a><div class="itemDetail__price">¥500</div><div class="itemDetail__stock">NM Stock: 2</div></div>'
    assert parse_page(html)[0] == []

def test_parser_keeps_real_results():
    html='<div class="result_pagenum">Page 1 / 1</div><div class="itemData"><a class="itemName">《Tithe》[VIS]</a><div class="itemDetail__price">¥1,500</div><div class="itemDetail__stock">NM Stock: 3</div></div>'
    rows,_=parse_page(html)
    assert len(rows)==1 and rows[0].price==1500
