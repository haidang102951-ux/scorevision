import os, requests, re
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime

SHEET_ID = os.environ["SHEET_ID"]
API_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

# === ĐÚNG CÁCH KHỞI TẠO GEMINI MỚI ===
client = genai.Client(api_key=GEMINI_KEY)

# === ĐỌC/GHI SHEET ===
def sheet_req(method, path, data=None):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}{path}"
    url += "&key=" + API_KEY if "?" in path else "?key=" + API_KEY
    r = requests.get(url, timeout=15) if method == "GET" else requests.post(url, json=data, timeout=15)
    if r.status_code >= 400: raise Exception(f"Sheet error: {r.status_code}")
    return r.json()

def get_records(name="Nguồn Tin"):
    d = sheet_req("GET", f"/values/{name}")
    rows = d.get("values", [])
    if not rows: return []
    headers = [h.strip() for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:]]

def update_cell(name, row, col, val):
    sheet_req("POST", f"/values/{name}!{chr(64+col)}{row}:{chr(64+col)}{row}?valueInputOption=RAW", {"values": [[val]]})

# === XỬ LÝ ===
def extract_keywords(title, content):
    p = f"Trả về 3-5 TỪ KHÓA TIẾNG ANH ngắn gọn để tìm ảnh bóng đá. CHỈ trả từ khóa.\nTIÊU ĐỀ: {title}\nNỘI DUNG: {content[:500]}"
    return client.models.generate_content(model="gemini-2.0-flash", contents=p).text.strip()

def get_image(keywords):
    if not PEXELS_KEY: return "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"
    r = requests.get(f"https://api.pexels.com/v1/search?query=football+{keywords}&per_page=1", headers={"Authorization": PEXELS_KEY}, timeout=10)
    return r.json()["photos"][0]["src"]["large"] if r.ok and r.json().get("photos") else "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"

def rewrite(title, content, src, link):
    p = f"""Viết lại bài bóng đá, đổi cách diễn đạt, không dịch nguyên văn. Ghi nguồn cuối: Nguồn: {src} — {link}

TIÊU ĐỀ: {title}
NỘI DUNG: {content}"""
    return client.models.generate_content(model="gemini-2.0-flash", contents=p).text

# === CHẠY ===
print("🔄 Bắt đầu...")
rows = get_records()
print(f"✅ Đọc {len(rows)} dòng")

for idx, row in enumerate(rows, start=2):
    if str(row.get("Trạng thái", "")).strip() != "Chờ xử lý": continue
    link, title, src = row.get("Link bài viết",""), row.get("Tiêu đề",""), row.get("Nguồn","")
    print(f"🔄 Xử lý: {title[:40]}...")
    try:
        html = requests.get(link, timeout=15, headers={"User-Agent":"Mozilla/5.0"}).text
        soup = BeautifulSoup(html, "html.parser")
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True))>40][:12]
        content = "\n\n".join(paras)
        if len(content) < 150: update_cell("Nguồn Tin", idx, 7, "❌ Nội dung quá ngắn"); continue

        kw = extract_keywords(title, content)
        img = get_image(kw)
        update_cell("Nguồn Tin", idx, 10, kw)
        update_cell("Nguồn Tin", idx, 11, img)
        update_cell("Nguồn Tin", idx, 12, "Pexels")

        out = rewrite(title, content, src, link)
        os.makedirs("output", exist_ok=True)
        fn = f"output/{datetime.now().strftime('%Y-%m-%d')}-{re.sub(r'[^\\w\\s-]','',title[:40])}.md"
        with open(fn, "w", encoding="utf-8") as f: f.write(out)

        update_cell("Nguồn Tin", idx, 7, "✅ Đã xử lý")
        update_cell("Nguồn Tin", idx, 8, fn)
        print(f"✅ Xong → {fn}")
    except Exception as e:
        update_cell("Nguồn Tin", idx, 7, f"❌ Lỗi: {str(e)[:40]}")
        print(f"❌ Lỗi: {e}")

print("🏁 Hoàn thành!")
