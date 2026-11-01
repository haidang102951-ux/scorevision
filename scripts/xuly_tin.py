import os, requests, re, html, json, csv, io
from bs4 import BeautifulSoup
from datetime import datetime

SHEET_ID = os.environ.get("SHEET_ID", "1-EcewgzQ1P9pyk6lp3ADV69kwWccuQuY72TK77OPmYk")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7'
}

REAL_PERSON_FALLBACKS = [
    {
        'keys': ['ronaldo', 'cr7', 'al nassr'],
        'img': 'https://upload.wikimedia.org/wikipedia/commons/8/8c/Cristiano_Ronaldo_2018.jpg'
    },
    {
        'keys': ['messi', 'inter miami', 'argentina'],
        'img': 'https://upload.wikimedia.org/wikipedia/commons/b/b4/Lionel-Messi-Argentina-2022-FIFA-World-Cup_%28cropped%29.jpg'
    },
    {
        'keys': ['mourinho'],
        'img': 'https://upload.wikimedia.org/wikipedia/commons/e/ec/Jos%C3%A9_Mourinho_2019.jpg'
    },
    {
        'keys': ['mbappe', 'mbappé'],
        'img': 'https://upload.wikimedia.org/wikipedia/commons/5/57/2019-07-17_SG_Dynamo_Dresden_vs._Paris_Saint-Germain_by_Sandro_Halank%E2%80%93129_%28cropped%29.jpg'
    },
    {
        'keys': ['việt nam', 'v-league', 'asian cup', 'thầy kim', 'u.23', 'u23', 'hagl'],
        'img': 'https://upload.wikimedia.org/wikipedia/commons/4/41/Vietnam_national_football_team_at_2019_AFC_Asian_Cup.jpg'
    },
    {
        'keys': ['chelsea'],
        'img': 'https://upload.wikimedia.org/wikipedia/en/c/cc/Chelsea_FC.svg'
    },
    {
        'keys': ['man united', 'man utd', 'mu'],
        'img': 'https://upload.wikimedia.org/wikipedia/en/7/7a/Manchester_United_FC_crest.svg'
    }
]

def decode_html(s):
    if not s: return ""
    s = html.unescape(html.unescape(s))
    return re.sub(r'<[^>]*>', '', s).strip()

def get_real_og_image(link):
    if not link or not link.startswith("http"):
        return ""
    try:
        r = requests.get(link, headers=HEADERS, timeout=8)
        if not r.ok:
            return ""
        m = re.search(r'<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', r.text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+property=[\"\']og:image[\"\']', r.text, re.IGNORECASE)
        if not m:
            m = re.search(r'<meta[^>]+name=[\"\']twitter:image[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', r.text, re.IGNORECASE)
        if m:
            img = m.group(1).strip()
            if img.startswith("//"):
                img = "https:" + img
            if img.startswith("http"):
                return img
    except Exception:
        pass
    return ""

def get_fallback_person_img(title):
    t = title.lower()
    for item in REAL_PERSON_FALLBACKS:
        for k in item['keys']:
            if k in t:
                return item['img']
    return "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=900&q=80"

print("🔄 Bat dau dong bo tin tuc va trich xuat anh that...")
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/e/2PACX-1vRjGewmdAmJVjyi-0vSc22hhFPacMgGc-WmVE8PEM3jHfA7IvED3XbBp68Bwp16n1Dc2FFP9ETKTaSH/pub?gid=840175350&single=true&output=csv"

try:
    r = requests.get(SHEET_CSV_URL, timeout=12)
    rows = list(csv.reader(io.StringIO(r.text)))
    print(f"Doc duoc {len(rows)-1} bai tu Google Sheet")
except Exception as e:
    print(f"Loi doc Sheet CSV: {e}")
    rows = []

articles = []
if len(rows) > 1:
    for idx, row in enumerate(rows[1:], 1):
        if not row or len(row) < 2:
            continue
        raw_title = row[0] if len(row) > 0 else ""
        title = decode_html(raw_title)
        if not title:
            continue
        
        link = row[1].strip() if len(row) > 1 else ""
        date = decode_html(row[2]) if len(row) > 2 else ""
        source = decode_html(row[3]) if len(row) > 3 else "Score Vision"
        sheet_img = row[10].strip() if len(row) > 10 else ""
        content = decode_html(row[12]) if len(row) > 12 else ""
        
        final_img = ""
        if sheet_img.startswith("http"):
            final_img = sheet_img
        
        if not final_img and link:
            safe_t = title.encode('ascii', 'backslashreplace').decode('ascii')[:40]
            print(f"[{idx}/{len(rows)-1}] Trich xuat anh that cho: {safe_t}...")
            final_img = get_real_og_image(link)
        
        if not final_img:
            final_img = get_fallback_person_img(title)
            print(f"   -> Fallback: {final_img[:50]}")
        else:
            print(f"   -> REAL Image: {final_img[:65]}")

        lead = content
        if not lead or len(lead) < 20:
            lead = f"Bản tin thể thao cập nhật nóng nhất từ {source}. Bấm để xem phân tích chi tiết hoặc đọc bài viết gốc."
        elif len(lead) > 130:
            lead = lead[:130] + "…"

        articles.append({
            "id": idx,
            "title": title,
            "link": link,
            "date": date,
            "source": source,
            "image": final_img,
            "lead": lead,
            "content": content
        })

    os.makedirs("data", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"✅ Hoan tat! Da ghi {len(articles)} bai vao data/news.json")

print("🏁 Hoan tat xu ly!")
