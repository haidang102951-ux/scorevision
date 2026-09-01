import os, requests, re, json
from bs4 import BeautifulSoup
from google import genai
from datetime import datetime

# === KẾT NỐI SHEET BẰNG API KEY ===
SHEET_ID = os.environ["SHEET_ID"]
API_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

# === KHỞI TẠO GEMINI ĐÚNG CÁCH MỚI ===
client = genai.Client(api_key=GEMINI_KEY)

# === HÀM ĐỌC/GHI SHEET ===
def sheet_request(method, path, data=None):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}{path}"
    if "?" in path:
        url += f"&key={API_KEY}"
    else:
        url += f"?key={API_KEY}"
    if method == "GET":
        r = requests.get(url, timeout=15)
    else:
        r = requests.post(url, json=data, timeout=15)
    if r.status_code >= 400:
        print(f"❌ Sheet API Error {r.status_code}: {r.text}")
        raise Exception(f"Sheet error: {r.status_code}")
    return r.json()

def get_all_records(sheet_name="Nguồn Tin"):
    data = sheet_request("GET", f"/values/{sheet_name}")
    rows = data.get("values", [])
    if not rows: return []
    headers = [h.strip() for h in rows[0]]
    records = []
    for row in rows[1:]:
        rec = {}
        for i, h in enumerate(headers):
            rec[h] = row[i] if i < len(row) else ""
        records.append(rec)
    return records

def update_cell(sheet_name, row, col, value):
    letter = chr(64 + col)
    sheet_request("POST", f"/values/{sheet_name}!{letter}{row}:{letter}{row}?valueInputOption=RAW",
                  {"values": [[value]]})

# === TRÍCH TỪ KHÓA ===
def trich_tu_khoa(title, content):
    prompt = f"""Đọc tiêu đề & nội dung bóng đá, trả về 3-5 TỪ KHÓA TIẾNG ANH ngắn gọn để tìm ảnh Pexels. CHỈ trả từ khóa, không giải thích.
TIÊU ĐỀ: {title}
NỘI DUNG: {content[:500]}"""
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text.strip()

# === TÌM ẢNH PEXELS ===
def tim_anh(tu_khoa):
    if not PEXELS_KEY:
        return "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"
    q = f"football soccer {tu_khoa}"
    r = requests.get(f"https://api.pexels.com/v1/search?query={q}&per_page=1&orientation=landscape&size=large",
                     headers={"Authorization": PEXELS_KEY}, timeout=10)
    if r.status_code == 200:
        photos = r.json().get("photos", [])
        if photos: return photos[0]["src"]["large"]
    return "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"

# === VIẾT LẠI BÀI ===
def viet_lai_bai(title, content, source, link):
    prompt = f"""Bạn là biên tập viên tin bóng đá Việt Nam.

=== NGUỒN ===
Nguồn: {source} | Link: {link}
TIÊU ĐỀ GỐC: {title}
NỘI DUNG GỐC:
{content}

=== YÊU CẦU ===
1. VIẾT BÀI MỚI HOÀN TOÀN, không dịch nguyên văn
2. Đổi cấu trúc, không giữ cụm > 5 từ
3. Giữ thông tin, số liệu, tên người, sự kiện
4. Viết tự nhiên, hấp dẫn, giọng báo thể thao VN
5. Ghi nguồn cuối: "Nguồn: {source} — {link}"

=== ĐỊNH DẠNG ===
TIÊU ĐỀ MỚI:
---
NỘI DUNG:
(3-5 đoạn)
---
Nguồn: {source} — {link}
"""
    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
    return response.text

# === CHẠY CHÍNH ===
print("🔄 Bắt đầu xử lý...")
rows = get_all_records("Nguồn Tin")
print(f"✅ Đọc được {len(rows)} dòng")

for idx, row in enumerate(rows, start=2):
    trang_thai = str(row.get("Trạng thái", "")).strip()
    if trang_thai != "Chờ xử lý":
        continue

    link = row.get("Link bài viết", "")
    title = row.get("Tiêu đề", "")
    source = row.get("Nguồn", "")
    print(f"🔄 Xử lý dòng {idx}: {title[:40]}...")

    try:
        # Lấy nội dung bài
        resp = requests.get(link, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40][:12]
        content = "\n\n".join(paras)
        if len(content) < 150:
            update_cell("Nguồn Tin", idx, 7, "❌ Nội dung quá ngắn")
            continue

        # Từ khóa + ảnh
        tu_khoa = trich_tu_khoa(title, content)
        anh_bia = tim_anh(tu_khoa)
        update_cell("Nguồn Tin", idx, 10, tu_khoa)
        update_cell("Nguồn Tin", idx, 11, anh_bia)
        update_cell("Nguồn Tin", idx, 12, "Pexels")

        # Viết lại bài
        ket_qua = viet_lai_bai(title, content, source, link)

        # Lưu file
        today = datetime.now().strftime("%Y-%m-%d")
        safe_title = re.sub(r'[^\w\s-]', '', title[:40]).strip()
        os.makedirs("output", exist_ok=True)
        filename = f"output/{today}-{safe_title}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(ket_qua)

        # Cập nhật trạng thái
        update_cell("Nguồn Tin", idx, 7, "✅ Đã xử lý")
        update_cell("Nguồn Tin", idx, 8, filename)
        print(f"✅ Xong → {filename}")

    except Exception as e:
        update_cell("Nguồn Tin", idx, 7, f"❌ Lỗi: {str(e)[:40]}")
        print(f"❌ Lỗi dòng {idx}: {e}")
        continue

print("🏁 Hoàn thành!")
