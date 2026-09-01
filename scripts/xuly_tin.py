import gspread, json, os, requests, re
from bs4 import BeautifulSoup
import google.generativeai as genai
from datetime import datetime

# === KẾT NỐI DỊCH VỤ ===
gc = gspread.service_account_from_dict(json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]))
sheet = gc.open_by_key(os.environ["SHEET_ID"]).worksheet("Nguồn Tin")
rows = sheet.get_all_records()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")

# === TRÍCH TỪ KHÓA ĐỂ TÌM ẢNH ===
def trich_tu_khoa(title, content):
    prompt = f"""
    Đọc tiêu đề và nội dung bài bóng đá, trả về 3-5 TỪ KHÓA TIẾNG ANH ngắn gọn
    để tìm ảnh trên Pexels. CHỈ trả về từ khóa, không giải thích gì thêm.
    TIÊU ĐỀ: {title}
    NỘI DUNG: {content[:500]}
    """
    resp = model.generate_content(prompt)
    return resp.text.strip()

# === TÌM ẢNH TỪ PEXELS ===
def tim_anh(tu_khoa):
    if not PEXELS_KEY:
        return "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"
    query = f"football soccer {tu_khoa}"
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=landscape&size=large"
    resp = requests.get(url, headers={"Authorization": PEXELS_KEY}, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        if data.get("photos"):
            return data["photos"][0]["src"]["large"]
    return "https://images.pexels.com/photos/177948/pexels-photo-177948.jpeg"

# === VIẾT LẠI BÀI ===
def viet_lai_bai(title, content, source, link, lang):
    prompt = f"""
    Bạn là biên tập viên tin tức bóng đá Việt Nam.

    === NGUỒN ===
    Nguồn: {source} | Link gốc: {link}
    TIÊU ĐỀ GỐC: {title}
    NỘI DUNG GỐC:
    {content}

    === YÊU CẦU ===
    1. ❌ KHÔNG dịch nguyên văn. VIẾT BÀI MỚI HOÀN TOÀN!
    2. ✅ Đổi cấu trúc, cách diễn đạt, không giữ cụm từ > 5 từ.
    3. ✅ Giữ nguyên thông tin, số liệu, tên người, sự kiện.
    4. ✅ Viết tự nhiên, hấp dẫn, giọng văn báo thể thao Việt Nam.
    5. ✅ Luôn ghi nguồn cuối bài: "Nguồn: {source} — {link}"

    === ĐỊNH DẠNG ===
    TIÊU ĐỀ MỚI:
    ---
    NỘI DUNG:
    (viết 3-5 đoạn, thông tin đầy đủ)
    ---
    Nguồn: {source} — {link}
    """
    resp = model.generate_content(prompt)
    return resp.text

# === XỬ LÝ TỪNG TIN ===
for idx, row in enumerate(rows, start=2):
    trang_thai = str(row.get("Trạng thái", "")).strip()
    if trang_thai != "Chờ xử lý":
        continue
    
    link = row["Link bài viết"]
    title = row["Tiêu đề"]
    source = row["Nguồn"]
    lang = row.get("Ngôn ngữ", "vi")
    
    print(f"🔄 Xử lý: {title[:50]}...")

    try:
        # === LẤY NỘI DUNG BÀI ===
        resp = requests.get(link, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        all_p = soup.find_all("p")
        paras = [p.get_text(strip=True) for p in all_p if len(p.get_text(strip=True)) > 40][:12]
        content = "\n\n".join(paras)
        
        if len(content) < 150:
            sheet.update_cell(idx, 7, "❌ Nội dung quá ngắn")
            continue

        # === TRÍCH TỪ KHÓA + TÌM ẢNH ===
        tu_khoa = trich_tu_khoa(title, content)
        anh_bia = tim_anh(tu_khoa)
        sheet.update_cell(idx, 10, tu_khoa)
        sheet.update_cell(idx, 11, anh_bia)
        sheet.update_cell(idx, 12, "Pexels")

        # === VIẾT LẠI BÀI ===
        ket_qua = viet_lai_bai(title, content, source, link, lang)

        # === LƯU FILE ===
        today = datetime.now().strftime("%Y-%m-%d")
        safe_title = re.sub(r'[^\w\s-]', '', title[:40]).strip()
        filename = f"output/{today}-{safe_title}.md"
        os.makedirs("output", exist_ok=True)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(ket_qua)

        # === CẬP NHẬT TRẠNG THÁI ===
        sheet.update_cell(idx, 7, "✅ Đã xử lý")
        sheet.update_cell(idx, 8, filename)
        print(f"✅ Xong → {filename}")

    except Exception as e:
        sheet.update_cell(idx, 7, f"❌ Lỗi: {str(e)[:40]}")
        print(f"❌ Lỗi: {e}")
        continue
