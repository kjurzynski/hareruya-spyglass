from app.hareruya import parse_page, select_rows


def test_parse_and_filter():
    html = '''
    <div class="result_pagenum">Page 1 / 1</div>
    <div class="itemData">
      <a class="itemName" href="/en/products/detail/123">Lightning Bolt 【EN】 [LEA]</a>
      <img src="/upload/save_image/123.jpg" alt="Lightning Bolt">
      <div class="itemDetail__price">¥1,500</div>
      <div class="itemDetail__stock">NM Stock: 3</div>
    </div>
    <div class="itemData">
      <a class="itemName">Lightning Bolt 【JP】 [LEA] Foil</a>
      <div class="itemDetail__price">¥2,500</div>
      <div class="itemDetail__stock">NM Stock: 1</div>
    </div>
    '''
    rows, pages = parse_page(html)
    assert pages == 1
    assert len(rows) == 2
    assert rows[0].price == 1500
    assert rows[0].language == "EN"
    assert rows[0].url == "https://www.hareruyamtg.com/en/products/detail/123"
    assert rows[0].image_url == "https://www.hareruyamtg.com/upload/save_image/123.jpg"
    assert rows[1].foil is True
    assert len(select_rows(rows, "Lightning Bolt", "nonfoil")) == 1
    assert len(select_rows(rows, "Lightning Bolt", "foil")) == 1


def test_image_can_be_in_single_listing_ancestor():
    html = """
    <div class="listing-wrapper">
      <div class="itemImage"><img data-src="https://files.hareruyamtg.com/product/abc123.jpeg"></div>
      <div class="itemData">
        <a class="itemName" href="/en/products/detail/456">Counterspell 【EN】 [ICE]</a>
        <div class="itemDetail__price">¥900</div>
        <div class="itemDetail__stock">NM Stock: 2</div>
      </div>
    </div>
    """
    rows, _ = parse_page(html)
    assert rows[0].image_url == "https://files.hareruyamtg.com/product/abc123.jpeg"


def test_loader_image_is_rejected():
    from app.hareruya import extract_image_url, LOADER_IMAGE_URL
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(f'<div class="itemData"><img src="{LOADER_IMAGE_URL}"></div>', 'html.parser')
    assert extract_image_url(soup.select_one('.itemData')) == ''


def test_real_image_is_extracted():
    from app.hareruya import extract_image_url
    from bs4 import BeautifulSoup
    soup = BeautifulSoup('<div class="itemData"><img data-src="https://files.hareruyamtg.com/product/card.jpg"></div>', 'html.parser')
    assert extract_image_url(soup.select_one('.itemData')) == 'https://files.hareruyamtg.com/product/card.jpg'


def test_art_card_is_skipped():
    html = """
    <div class="result_pagenum">Page 1 / 1</div>
    <div class="itemData">
      <a class="itemName" href="/en/products/detail/999">Lightning Bolt Art Card 【EN】 [LEA]</a>
      <div class="itemDetail__price">¥500</div>
      <div class="itemDetail__stock">NM Stock: 2</div>
    </div>
    """
    rows, _ = parse_page(html)
    assert rows == []
