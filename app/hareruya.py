from __future__ import annotations
import os,re,time,unicodedata
from concurrent.futures import ThreadPoolExecutor,as_completed
from dataclasses import dataclass
from urllib.parse import quote,urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright,TimeoutError as PlaywrightTimeoutError
BASE_URL='https://www.hareruyamtg.com/en/products/search'; LOADER='https://www.hareruyamtg.com/en/assets/img/ajax-loader.gif'
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
PRICE=re.compile(r'(?:¥|￥)\s*([0-9][0-9,]*)|([0-9][0-9,]*)\s*(?:JPY|円)\b',re.I); STOCK=re.compile(r'\b(?:NM|SP|MP|HP)\s+Stock\s*[:：]\s*(\d+)\b',re.I); PAGES=re.compile(r'(?:Page|ページ)\s*\d+\s*/\s*(\d+)',re.I); LANG=re.compile(r'[【〖]\s*(JP|EN|CS|CT|FR|DE|IT|KO|PT|RU|ES|AG)\s*[】〗]',re.I); EXP=re.compile(r'\[([^\[\]]+)\]\s*$'); IMGURL=re.compile(r'(?:https?:)?//[^"\'\s)]+(?:\.(?:jpe?g|png|webp|gif)(?:\?[^"\'\s)]*)?)',re.I)
@dataclass(frozen=True)
class Listing:
    price:int; language:str; expansion:str; foil:bool; title:str; stock:int; url:str; image_url:str
@dataclass(frozen=True)
class CardResult:
    card_name:str; rows:list[Listing]; error:str|None=None
class HareruyaError(RuntimeError): pass
def clean(s): return ' '.join(s.split())
def norm(s): return clean(unicodedata.normalize('NFKC',s)).casefold().strip()
def card_name_candidates(title):
    v=norm(title)
    if '《' in v and '》' in v: base=v.split('《',1)[1].split('》',1)[0].strip()
    else:
        base=re.split(r'\s*[【〖]\s*[a-z]{2}\s*[】〗]',v,maxsplit=1,flags=re.I)[0]
        base=re.sub(r'\s*\[[^\[\]]+\]\s*$','',base).strip()
    base=re.sub(r'\s+(?:foil|non[- ]foil)\s*$','',base,flags=re.I).strip()
    return [base]+[p.strip() for p in base.split('/') if p.strip() and p.strip()!=base]
def contains_card(title,card_name): return norm(card_name) in card_name_candidates(title)
def search_url(name): return f'{BASE_URL}?suggest_type=all&product={quote(name)}'
def page_url(base,n):
    p=urlsplit(base); q=[(k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k!='page']; q.append(('page',str(n))); return urlunsplit((p.scheme,p.netloc,p.path,urlencode(q),p.fragment))
def load_page(page,url):
    page.goto(url,wait_until='domcontentloaded',timeout=30000); page.wait_for_selector('.itemData',state='attached',timeout=20000)
    try: page.wait_for_function("""() => [...document.querySelectorAll('.itemData')].every(x=>x.querySelector('.itemDetail__price')?.textContent.trim()&&x.querySelector('.itemDetail__stock')?.textContent.trim())""",timeout=5000)
    except PlaywrightTimeoutError:
        page.evaluate("""async()=>{for(const x of document.querySelectorAll('.itemData')){x.scrollIntoView({block:'center'});await new Promise(r=>setTimeout(r,40))}window.scrollTo(0,0)}"""); page.wait_for_function("""() => [...document.querySelectorAll('.itemData')].every(x=>x.querySelector('.itemDetail__price')?.textContent.trim()&&x.querySelector('.itemDetail__stock')?.textContent.trim())""",timeout=5000)
    html=page.content()
    for delay in (3,2):
        if LOADER.casefold() not in html.casefold(): break
        time.sleep(delay); page.evaluate("""async()=>{for(const x of document.querySelectorAll('.itemData')){x.scrollIntoView({block:'center'});await new Promise(r=>setTimeout(r,40))}window.scrollTo(0,0)}"""); html=page.content()
    return html
def image_url(item):
    attrs=('src','current-src','data-src','data-lazy-src','data-original','data-image','data-image-url','data-lazy','data-bg','data-background')
    nodes=item.select('img,source')
    def scan(nodes):
        for n in nodes:
            for a in attrs:
                v=n.get(a)
                if v and LOADER.casefold()!=urljoin(BASE_URL,v).casefold(): return urljoin(BASE_URL,v)
            ss=n.get('srcset') or n.get('data-srcset')
            if ss:
                v=ss.split(',')[-1].strip().split(' ')[0]
                if v and LOADER.casefold()!=urljoin(BASE_URL,v).casefold(): return urljoin(BASE_URL,v)
        return ''
    found=scan(nodes)
    if found:return found
    a=item.parent
    for _ in range(3):
        if a is None:break
        if len(a.select('.itemData'))==1:
            found=scan(a.select('img,source'))
            if found:return found
            for m in IMGURL.finditer(str(a)):
                v=m.group(0)
                if v.casefold()!=LOADER.casefold():return urljoin(BASE_URL,v)
        a=a.parent
    return ''
def parse_page(html):
    soup=BeautifulSoup(html,'html.parser'); items=soup.select('.itemData')
    if not items: raise HareruyaError('The rendered page contains no .itemData elements.')
    rows=[]
    for item in items:
        node=item.select_one('a.itemName'); title=clean(node.get_text(' ',strip=True)) if node else ''; p=item.select_one('.itemDetail__price')
        if not title or not p: continue
        if 'art card' in title.casefold(): continue
        m=PRICE.search(clean(p.get_text(' ',strip=True)))
        if not m: continue
        stock_node=item.select_one('.itemDetail__stock'); stock=max((int(x.group(1)) for x in STOCK.finditer(clean(stock_node.get_text(' ',strip=True)))) if stock_node else [],default=0)
        lm=LANG.search(title); em=EXP.search(title)
        rows.append(Listing(int(next(x for x in m.groups() if x).replace(',','')),lm.group(1).upper() if lm else 'Unknown',em.group(1).strip() if em else 'Unknown',bool(re.search(r'\bfoil\b',title,re.I)),title,stock,urljoin(BASE_URL,node.get('href','')) if node else '',image_url(item)))
    nums=[int(m.group(1)) for box in soup.select('.result_pagenum') for m in PAGES.finditer(clean(box.get_text(' ',strip=True)))]
    return rows,max(nums or [1])
def crawl(name,page):
    base=search_url(name); html=load_page(page,base); rows,pages=parse_page(html); maxp=int(os.getenv('HARERUYA_MAX_PAGES','20'))
    for n in range(2,min(pages,maxp)+1):
        r,_=parse_page(load_page(page,page_url(base,n))); rows.extend(r)
    return rows
def select_rows(rows,name,finish):
    selected=[r for r in rows if contains_card(r.title,name)]
    if finish=='foil':selected=[r for r in selected if r.foil]
    elif finish=='nonfoil':selected=[r for r in selected if not r.foil]
    return sorted((r for r in selected if r.stock>0),key=lambda r:r.price)
def check_card(name,finish):
    try:
        with sync_playwright() as pw:
            b=pw.chromium.launch(headless=True); c=b.new_context(user_agent=UA,locale='en-US'); page=c.new_page()
            try:return CardResult(name,select_rows(crawl(name,page),name,finish))
            finally:c.close();b.close()
    except HareruyaError as e:return CardResult(name,[],str(e))
    except Exception as e:return CardResult(name,[],f'Unexpected error: {e}')
def run_cards(names,finish,progress=None):
    names=[clean(n) for n in names if clean(n)]; results=[None]*len(names); workers=min(4,len(names)) if names else 0
    if not names:return []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs=[ex.submit(check_card,i,finish) for i in names]; done=0
        for f in as_completed(fs):
            # futures return in arbitrary order, restore input order by name lookup below
            r=f.result(); idx=names.index(r.card_name); results[idx]=r; done+=1
            if progress:progress(done,len(names))
    return results
