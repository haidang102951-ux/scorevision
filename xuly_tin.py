import os, requests, re
from bs4 import BeautifulSoup
from google import genai  # ✅ KHỚP với google-genai trong .yml
from datetime import datetime

SHEET_ID = os.environ["SHEET_ID"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ["PEXELS_API_KEY"]

# ✅ KHỞI TẠO ĐÚNG CÁCH thư viện google-genai — KHÔNG CÓ genai.configure!
client = genai.Client(api_key=GEMINI_API_KEY)

# === GỌI AI ĐÚNG CÁCH ===
def go_ai(prompt):
    try:
        resp = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"⚠️ Lỗi AI: {e}")
        return ""

# === ĐỌC/GHI SHEET KHÔNG DÙNG gspread ===
def sheet_req(method, path, data=None):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}{path}"
    url += "&key=" + GOOGLE_API_KEY if "?" in path else "?key=" + GOOGLE_API_KEY
    try:
        if method == "GET":
            r = requests.get(url, timeout=15)
        else:
            r = requests.post(url, json=data, timeout=15)
        return r.json() if r.ok else None
    except Exception as e:
        print(f"⚠️ Lỗi Sheet: {e}")
        return None

def get_records(tab="Nguồn Tin"):
    d = sheet_req("GET", f"/values/{tab}")
    if not d or "values" not in d: return []
    rows = d["values"]
    if len(rows) < 2: return []
    headers = [str(h).strip() for h in rows[0]]
    return [dict(zip(headers, row)) for row in rows[1:]]

def update_cell(tab, row, col, val):
    sheet_req("PUT", f"/values/{tab}!{chr(64+col)}{row}:{chr(64+col)}{row}?valueInputOption=RAW",
              {"values": [[val]]})

# === ẢNH PEXELS ===
def get_image(kw):
    default = "https://images.unsplash.com/photo-1574629810360-7efbbe195018?w=800"
    if not PEXELS_API_KEY or not kw: return default
    try:
        r = requests.get(f"https://api.pexels.com/v1/search?query=football+{kw}&per_page=1",
                        headers={"Authorization": PEXELS_API_KEY}, timeout=10)
        return r.json()["photos"][0]["src"]["large"] if r.ok and r.json().get("photos") else default
    except: return default

# === CHẠY ===
print("🔄 Bắt đầu xử lý...")
rows = get_records("Nguồn Tin")
print(f"✅ Đọc được {len(rows)} dòng")

for idx, row in enumerate(rows, start=2):
    if str(row.get("Trạng thái", "")).strip() != "Chờ xử lý": continue
    link = row.get("Link bài viết", "")
    title = row.get("Tiêu đề", "")
    src = row.get("Nguồn", "")
    print(f"🔄 Xử lý: {title[:40]}...")
    
    try:
        html = requests.get(link, timeout=15, headers={"User-Agent":"Mozilla/5.0"}).text
        soup = BeautifulSoup(html, "html.parser")
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True))>40][:12]
        content = "\n\n".join(paras)
        if len(content) < 150:
            update_cell("Nguồn Tin", idx, 7, "❌ Nội dung quá ngắn")
            continue

        kw = go_ai(f"Trả về 3-5 TỪ KHÓA TIẾNG ANH bóng đá. CHỈ từ khóa.\nTIÊU ĐỀ: {title}\nNỘI DUNG: {content[:500]}")
        img = get_image(kw)
        update_cell("Nguồn Tin", idx, 10, kw)
        update_cell("Nguồn Tin", idx, 11, img)
        update_cell("Nguồn Tin", idx, 12, "Pexels")

        bai_moi = go_ai(f"""Viết lại bài bóng đá, đổi cách diễn đạt, không dịch nguyên văn.
Ghi nguồn cuối: Nguồn: {src} — {link}

TIÊU ĐỀ: {title}
NỘI DUNG: {content}""")

        os.makedirs("output", exist_ok=True)
        safe_title = re.sub(r'[^\w\s-]', '', title[:40]).strip()
        fn = f"output/{datetime.now().strftime('%Y-%m-%d')}-{safe_title}.md"
        with open(fn, "w", encoding="utf-8") as f:
            f.write(bai_moi)

        update_cell("Nguồn Tin", idx, 7, "✅ Đã xử lý")
        update_cell("Nguồn Tin", idx, 8, fn)
        print(f"✅ Xong → {fn}")
    except Exception as e:
        update_cell("Nguồn Tin", idx, 7, f"❌ Lỗi: {str(e)[:40]}")
        print(f"❌ Lỗi dòng {idx}: {e}")

print("🏁 Hoàn thành!")
