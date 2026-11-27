import csv
import hashlib
import html
import io
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

# ==============================================================================
# SCORE VISION — FOOTBALL NEWS SYNC & DAILY SEO ARTICLE PUBLISHER
# 1. Filters strictly for football news & blocks Google News generic icons.
# 2. Extracts real og:image and og:description from source pages (0 AI tokens).
# 3. Generates up to MAX_DAILY_AI_ARTICLES (default: 2/day) full SEO HTML
#    articles in Vietnamese (Style 3 Navy & White) only when GEMINI_API_KEY is set.
# ==============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ARTICLES_DIR = os.path.join(BASE_DIR, "bai-viet")
NEWS_JSON_PATH = os.path.join(DATA_DIR, "news.json")
PUBLISHED_JSON_PATH = os.path.join(DATA_DIR, "published_articles.json")
HUB_HTML_PATH = os.path.join(BASE_DIR, "bai-viet.html")
SITEMAP_PATH = os.path.join(BASE_DIR, "sitemap.xml")

SHEET_ID = os.environ.get("SHEET_ID", "1-EcewgzQ1P9pyk6lp3ADV69kwWccuQuY72TK77OPmYk")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MAX_DAILY_AI_ARTICLES = int(os.environ.get("MAX_DAILY_AI_ARTICLES", "6"))

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vRjGewmdAmJVjyi-0vSc22hhFPacMgGc-WmVE8PEM3jHfA7IvED3XbBp68Bwp16n1Dc2FFP9ETKTaSH"
    "/pub?gid=840175350&single=true&output=csv"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

NON_FOOTBALL_KEYWORDS = [
    "điền kinh", "nguyễn thị oanh", "vua tốc độ", "đua ôtô", "đua ô tô", "đua xe",
    "rally", "f1", "motogp", "billiards", "bi-a", "cầu lông", "bơi lội", "đội tuyển lặn",
    "đi bộ", "giảm cân", "tennis", "quần vợt", "pickleball", "golf", "bóng chuyền",
    "bóng rổ", "nba", "esports", "boxing", "mma", "ufc", "cử tạ", "bắn súng",
    "snooker", "cricket", "bóng bầu dục", "bóng chày"
]

BAD_IMAGE_DOMAINS = [
    "lh3.googleusercontent.com",
    "news.google.com",
    "gstatic.com",
    "google.com/images",
]

REAL_PERSON_FALLBACKS = [
    {"keys": ["ronaldo", "cr7", "al nassr"], "img": "https://upload.wikimedia.org/wikipedia/commons/8/8c/Cristiano_Ronaldo_2018.jpg"},
    {"keys": ["messi", "inter miami", "argentina"], "img": "https://upload.wikimedia.org/wikipedia/commons/b/b4/Lionel-Messi-Argentina-2022-FIFA-World-Cup_%28cropped%29.jpg"},
    {"keys": ["mourinho"], "img": "https://upload.wikimedia.org/wikipedia/commons/e/ec/Jos%C3%A9_Mourinho_2019.jpg"},
    {"keys": ["mbappe", "mbappé"], "img": "https://upload.wikimedia.org/wikipedia/commons/5/57/2019-07-17_SG_Dynamo_Dresden_vs._Paris_Saint-Germain_by_Sandro_Halank%E2%80%93129_%28cropped%29.jpg"},
    {"keys": ["việt nam", "v-league", "asian cup", "thầy kim", "u.23", "u23", "u.17", "u17", "hagl"], "img": "https://upload.wikimedia.org/wikipedia/commons/4/41/Vietnam_national_football_team_at_2019_AFC_Asian_Cup.jpg"},
    {"keys": ["chelsea"], "img": "https://upload.wikimedia.org/wikipedia/en/c/cc/Chelsea_FC.svg"},
    {"keys": ["man united", "man utd", "mu "], "img": "https://upload.wikimedia.org/wikipedia/en/7/7a/Manchester_United_FC_crest.svg"},
]


def decode_html(text):
    if not text:
        return ""
    text = html.unescape(html.unescape(text))
    return re.sub(r"<[^>]*>", "", text).strip()


def is_football_article(title, category=""):
    combined = f"{title} {category}".lower()
    return not any(kw in combined for kw in NON_FOOTBALL_KEYWORDS)


def is_bad_image(url):
    if not url or not url.startswith("http"):
        return True
    low = url.lower()
    return any(bad in low for bad in BAD_IMAGE_DOMAINS)


def has_foreign_script(text):
    """Reject accidental CJK or Cyrillic characters from LLM output."""
    return bool(re.search(r"[\u4e00-\u9fff\u0400-\u04ff]", text or ""))


def slugify(text):
    text = text.lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:64] or "bai-viet-bong-da"


def get_fallback_img(title):
    t = title.lower()
    for item in REAL_PERSON_FALLBACKS:
        if any(k in t for k in item["keys"]):
            return item["img"]
    return "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=900&q=80"


def extract_article_meta(link):
    """Fetch real og:image and og:description from source URL (0 AI tokens)."""
    if not link or not link.startswith("http"):
        return "", ""
    try:
        r = requests.get(link, headers=HEADERS, timeout=8, allow_redirects=True)
        if not r.ok or not r.text:
            return "", ""
        body = r.text
        img = ""
        for pat in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ]:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if cand.startswith("//"):
                    cand = "https:" + cand
                if not is_bad_image(cand):
                    img = cand
                    break

        desc = ""
        for pat in [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        ]:
            m = re.search(pat, body, re.IGNORECASE)
            if m:
                cand = decode_html(m.group(1))
                if len(cand) >= 40:
                    desc = cand
                    break
        return img, desc
    except Exception:
        return "", ""


def load_published_state():
    if os.path.exists(PUBLISHED_JSON_PATH):
        try:
            with open(PUBLISHED_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("history", {})
                    data.setdefault("daily_counts", {})
                    return data
        except Exception:
            pass
    return {"history": {}, "daily_counts": {}}


def save_published_state(state):
    with open(PUBLISHED_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_seo_article_html(art_data, source_name, source_link, today_str):
    title_esc = html.escape(art_data["title"])
    desc_esc = html.escape(art_data["seo_description"])
    cat_esc = html.escape(art_data.get("category", "Phân tích bóng đá"))
    read_time = html.escape(art_data.get("read_time", "Đọc 5 phút"))
    lead_esc = html.escape(art_data["lead"])

    sections_html = []
    for sec in art_data.get("sections", []):
        h = html.escape(sec.get("heading", ""))
        ps = "\n        ".join(f"<p>{html.escape(p)}</p>" for p in sec.get("paragraphs", []) if p.strip())
        if h and ps:
            sections_html.append(f"<h2>{h}</h2>\n        {ps}")

    takeaways = art_data.get("key_takeaways", [])
    takeaway_html = ""
    if takeaways:
        lis = "\n            ".join(f"<li>{html.escape(t)}</li>" for t in takeaways if t.strip())
        takeaway_html = f"""
        <h2>Điểm nhấn đáng chú ý</h2>
        <ul>
            {lis}
        </ul>"""

    schema_json = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": art_data["title"],
            "description": art_data["seo_description"],
            "author": {"@type": "Organization", "name": "Score Vision"},
            "publisher": {"@type": "Organization", "name": "Score Vision", "url": "https://scorevision.io.vn"},
            "datePublished": today_str,
            "inLanguage": "vi",
        },
        ensure_ascii=False,
    )

    source_note = ""
    if source_link and source_link.startswith("http"):
        source_note = (
            f'<div class="callout"><strong>Nguồn tham khảo dữ liệu:</strong> '
            f'Tổng hợp &amp; phân tích mở rộng bởi Score Vision từ bản tin của '
            f'<a href="{html.escape(source_link)}" target="_blank" rel="noopener noreferrer">{html.escape(source_name)}</a>.</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta name="google-adsense-account" content="ca-pub-5011502652158923">
    <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-5011502652158923" crossorigin="anonymous"></script>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title_esc} | Score Vision</title>
    <meta name="description" content="{desc_esc}">
    <link rel="icon" type="image/png" href="../favicon.png">
    <meta name="theme-color" content="#0b192c">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="stylesheet" href="../assets/theme.css?v=20261127">
    <style>
        .article-wrap {{ max-width: 860px; margin: 0 auto; }}
        .breadcrumb {{ font-size: 13px; color: #64748b; margin-bottom: 16px; }}
        .breadcrumb a {{ color: #be123c; text-decoration: none; font-weight: 600; }}
        .article-body {{ background: #ffffff; border: 1px solid #dbe2ea; border-radius: 18px; padding: 34px 32px; box-shadow: 0 4px 16px rgba(11,25,44,0.06); }}
        .article-body h2 {{ font-size: 21px; font-weight: 800; color: #0b192c; margin: 28px 0 12px; padding-left: 12px; border-left: 4px solid #e11d48; line-height: 1.35; }}
        .article-body p {{ font-size: 15.5px; color: #334155; line-height: 1.85; margin-bottom: 14px; }}
        .article-body ul {{ margin: 10px 0 16px 22px; color: #334155; font-size: 15.5px; line-height: 1.8; }}
        .article-body li {{ margin-bottom: 8px; }}
        .callout {{ background: #f8fafc; border: 1px solid #dbe2ea; border-left: 4px solid #0b192c; border-radius: 10px; padding: 16px 18px; margin: 20px 0 0; font-size: 14.5px; color: #334155; }}
        .callout a {{ color: #be123c; font-weight: 700; }}
        @media (max-width: 720px) {{ .article-body {{ padding: 22px 18px; }} }}
    </style>
    <script type="application/ld+json">{schema_json}</script>
</head>
<body class="sv-theme-navy">
<header class="sv-header">
    <div class="sv-container">
        <a href="../index.html" class="sv-brand">
            <div class="sv-logo"><img src="../logo.png" alt="Score Vision" onerror="this.src='../favicon.png'"></div>
            <div>
                <div class="sv-brand-title">Score Vision</div>
                <div class="sv-brand-sub">CHUYÊN SÂU · DỮ LIỆU · PHÂN TÍCH BÓNG ĐÁ</div>
            </div>
        </a>
    </div>
</header>

<div class="sv-container sv-nav-wrap">
    <nav class="sv-nav" aria-label="Điều hướng chính">
        <a href="../index.html">Trang chủ</a>
        <a href="../lich-dau.html">Lịch đấu</a>
        <a href="../du-doan.html">Phân Tích &amp; Dự Đoán</a>
        <a href="../bai-viet.html" class="active">Kiến Thức &amp; Chiến Thuật</a>
        <a href="../bang-xep-hang.html">Bảng xếp hạng</a>
        <a href="../thong-ke.html">Thống kê</a>
        <a href="../tin-nong.html">Tin Nóng</a>
        <a href="../ket-qua.html">Kết Quả</a>
    </nav>
</div>

<main class="sv-container article-wrap">
    <div class="breadcrumb"><a href="../index.html">Trang chủ</a> / <a href="../bai-viet.html">Kiến thức &amp; Chiến thuật</a> / {title_esc}</div>

    <section class="sv-hero">
        <span class="sv-eyebrow">{cat_esc} · {read_time}</span>
        <h1>{title_esc}</h1>
        <p>{lead_esc}</p>
    </section>

    <article class="article-body">
        {"".join(sections_html)}
        {takeaway_html}
        {source_note}
    </article>

    <footer class="sv-footer">
        <p><strong>Score Vision</strong> — Nền tảng phân tích &amp; dữ liệu bóng đá chuyên sâu</p>
        <div class="sv-footer-links">
            <a href="../index.html">Trang chủ</a>
            <a href="../bai-viet.html">Kiến thức &amp; Chiến thuật</a>
            <a href="../gioi-thieu.html">Giới thiệu</a>
            <a href="../lien-he.html">Liên hệ</a>
            <a href="../chinh-sach-bao-mat.html">Chính sách bảo mật</a>
            <a href="../dieu-khoan.html">Điều khoản sử dụng</a>
        </div>
        <p>© 2026 Score Vision (scorevision.io.vn). Toàn bộ bản quyền được bảo lưu.</p>
    </footer>
</main>
<script src="../assets/motion.js?v=20261127" defer></script>
</body>
</html>
"""


def prepend_to_hub_and_sitemap(slug, art_data):
    rel_href = f"bai-viet/{slug}.html"
    if os.path.exists(HUB_HTML_PATH):
        with open(HUB_HTML_PATH, "r", encoding="utf-8") as f:
            hub_html = f.read()
        if rel_href not in hub_html and "<!-- AUTO_ARTICLES_START -->" in hub_html:
            card_html = (
                f'        <a href="{rel_href}" class="art-card">\n'
                f'            <div>\n'
                f'                <div class="art-meta">\n'
                f'                    <span class="art-tag blue">{html.escape(art_data.get("category", "Phân tích bóng đá"))}</span>\n'
                f'                    <span class="art-time">{html.escape(art_data.get("read_time", "Đọc 5 phút"))}</span>\n'
                f'                </div>\n'
                f'                <h2 class="art-title">{html.escape(art_data["title"])}</h2>\n'
                f'                <p class="art-excerpt">{html.escape(art_data["seo_description"])}</p>\n'
                f'            </div>\n'
                f'            <div class="art-foot">\n'
                f'                <span class="art-author">Ban Biên Tập Score Vision</span>\n'
                f'                <span class="art-cta">Đọc bài phân tích →</span>\n'
                f'            </div>\n'
                f'        </a>\n'
            )
            hub_html = hub_html.replace(
                "<!-- AUTO_ARTICLES_START -->",
                "<!-- AUTO_ARTICLES_START -->\n" + card_html,
                1,
            )
            with open(HUB_HTML_PATH, "w", encoding="utf-8") as f:
                f.write(hub_html)

    if os.path.exists(SITEMAP_PATH):
        with open(SITEMAP_PATH, "r", encoding="utf-8") as f:
            sm = f.read()
        full_url = f"https://scorevision.io.vn/{rel_href}"
        if full_url not in sm and "</urlset>" in sm:
            entry = f"  <url>\n    <loc>{full_url}</loc>\n  </url>\n\n</urlset>"
            sm = sm.replace("</urlset>", entry, 1)
            with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
                f.write(sm)


def generate_daily_seo_articles(articles):
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY not set -> skipping AI SEO article generation (0 quota used).")
        return

    tz_vn = timezone(timedelta(hours=7))
    today_str = datetime.now(tz_vn).strftime("%Y-%m-%d")
    state = load_published_state()
    done_today = state["daily_counts"].get(today_str, 0)
    if done_today >= MAX_DAILY_AI_ARTICLES:
        print(f"Daily cap reached ({done_today}/{MAX_DAILY_AI_ARTICLES}) for {today_str}. Skipping AI calls.")
        return

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Cannot init google-genai client: {e}")
        return

    os.makedirs(ARTICLES_DIR, exist_ok=True)
    for item in articles:
        if done_today >= MAX_DAILY_AI_ARTICLES:
            break
        key = hashlib.md5((item["link"] or item["title"]).encode("utf-8")).hexdigest()
        if key in state["history"]:
            continue

        prompt = f"""Bạn là biên tập viên thể thao chuyên sâu của Score Vision (scorevision.io.vn).
Hãy viết 1 bài phân tích bóng đá chuẩn SEO, hoàn toàn độc lập và sâu sắc dựa trên chủ đề thời sự sau:
- Tiêu đề gốc: {item["title"]}
- Tóm tắt ngữ cảnh: {item["content"] or item["title"]}
- Nguồn: {item["source"]}

YÊU CẦU NGHIÊM NGẶT:
1. Viết 100% bằng TIẾNG VIỆT chuẩn mực báo chí thể thao. TUYỆT ĐỐI KHÔNG chèn bất kỳ chữ Hán, chữ Nga hay ký tự lạ nào.
2. KHÔNG nhắc tới cá cược, tỷ lệ kèo, tài xỉu hay cờ bạc. Tập trung vào chuyên môn chiến thuật, phong độ, nhân sự và bối cảnh giải đấu.
3. Trả về DUY NHẤT 1 JSON hợp lệ (không bọc markdown ```json) theo cấu trúc:
{{
  "title": "Tiêu đề SEO hấp dẫn 60-85 ký tự",
  "seo_description": "Mô tả meta SEO 130-160 ký tự",
  "category": "Phân tích bóng đá",
  "read_time": "Đọc 5 phút",
  "lead": "Đoạn mở đầu 2-3 câu tóm tắt góc nhìn chuyên môn",
  "sections": [
    {{"heading": "1. Bối cảnh và diễn biến chính", "paragraphs": ["Đoạn văn 1 (80-120 chữ)", "Đoạn văn 2 (80-120 chữ)"]}},
    {{"heading": "2. Phân tích chiến thuật và nhân sự", "paragraphs": ["Đoạn văn 1 (80-120 chữ)", "Đoạn văn 2 (80-120 chữ)"]}},
    {{"heading": "3. Tác động tới cục diện sắp tới", "paragraphs": ["Đoạn văn 1 (80-120 chữ)", "Đoạn văn 2 (80-120 chữ)"]}}
  ],
  "key_takeaways": ["Ý chính 1", "Ý chính 2", "Ý chính 3"]
}}"""

        try:
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            raw = (resp.text or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
            art_data = json.loads(raw)

            full_text = json.dumps(art_data, ensure_ascii=False)
            if has_foreign_script(full_text):
                print("Rejected AI output due to foreign script contamination.")
                continue

            slug = f"{today_str}-{slugify(art_data['title'])}"
            out_path = os.path.join(ARTICLES_DIR, f"{slug}.html")
            html_content = build_seo_article_html(art_data, item["source"], item["link"], today_str)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            prepend_to_hub_and_sitemap(slug, art_data)
            state["history"][key] = {"slug": slug, "date": today_str}
            done_today += 1
            state["daily_counts"][today_str] = done_today
            save_published_state(state)
            print(f"Published AI SEO article [{done_today}/{MAX_DAILY_AI_ARTICLES}]: bai-viet/{slug}.html")
            if done_today < MAX_DAILY_AI_ARTICLES:
                time.sleep(4)
        except Exception as e:
            print(f"AI article error: {e}")


def main():
    print("Syncing football news from Google Sheet...")
    try:
        r = requests.get(SHEET_CSV_URL, timeout=12)
        rows = list(csv.reader(io.StringIO(r.text)))
        print(f"Loaded {max(0, len(rows) - 1)} raw rows from Sheet.")
    except Exception as e:
        print(f"Error reading Sheet CSV: {e}")
        rows = []

    articles = []
    skipped_non_football = 0
    for idx, row in enumerate(rows[1:], 1):
        if not row or len(row) < 2:
            continue
        title = decode_html(row[0] if len(row) > 0 else "")
        category = decode_html(row[5]) if len(row) > 5 else ""
        if not title or not is_football_article(title, category):
            skipped_non_football += 1
            continue

        link = row[1].strip() if len(row) > 1 else ""
        date = decode_html(row[2]) if len(row) > 2 else ""
        source = decode_html(row[3]) if len(row) > 3 else "Score Vision"
        sheet_img = row[10].strip() if len(row) > 10 else ""
        sheet_content = decode_html(row[12]) if len(row) > 12 else ""

        final_img = "" if is_bad_image(sheet_img) else sheet_img
        scraped_desc = ""

        if (not final_img or not sheet_content) and link:
            og_img, og_desc = extract_article_meta(link)
            if not final_img and og_img:
                final_img = og_img
            scraped_desc = og_desc

        if not final_img:
            final_img = get_fallback_img(title)

        final_content = sheet_content if (sheet_content and not has_foreign_script(sheet_content)) else scraped_desc

        articles.append({
            "id": len(articles) + 1,
            "title": title,
            "link": link,
            "date": date,
            "source": source,
            "image": final_img,
            "content": final_content,
        })

    os.makedirs(DATA_DIR, exist_ok=True)
    output_data = {
        "updated_at": datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M:%S +0700"),
        "total": len(articles),
        "items": articles,
    }
    with open(NEWS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(articles)} football items to data/news.json (filtered {skipped_non_football} non-football items).")
    generate_daily_seo_articles(articles)


if __name__ == "__main__":
    main()
