import os
import requests
import re
import time

from bs4 import BeautifulSoup
from google import genai
from datetime import datetime

# =========================
# CẤU HÌNH
# =========================

SHEET_ID = os.environ["SHEET_ID"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")

SHEET_NAME = "Nguồn Tin"
GEMINI_MODEL = "gemini-2.0-flash"

FALLBACK_IMAGE = (
    "https://images.pexels.com/photos/177948/"
    "pexels-photo-177948.jpeg"
)

# Gemini SDK mới
client = genai.Client(api_key=GEMINI_API_KEY)


# =========================
# GOOGLE SHEETS
# =========================

def sheet_req(method, path, data=None):

    url = (
        f"https://sheets.googleapis.com/v4/"
        f"spreadsheets/{SHEET_ID}{path}"
    )

    if "?" in path:
        url += "&key=" + GOOGLE_API_KEY
    else:
        url += "?key=" + GOOGLE_API_KEY

    if method == "GET":
        r = requests.get(url, timeout=20)

    elif method == "PUT":
        r = requests.put(url, json=data, timeout=20)

    elif method == "POST":
        r = requests.post(url, json=data, timeout=20)

    else:
        raise Exception(f"Method không hợp lệ: {method}")

    if r.status_code >= 400:
        raise Exception(
            f"Google Sheets error {r.status_code}: {r.text[:500]}"
        )

    return r.json()


def get_records(name=SHEET_NAME):

    d = sheet_req("GET", f"/values/{name}")

    rows = d.get("values", [])

    if not rows:
        return []

    headers = [str(h).strip() for h in rows[0]]

    records = []

    for row in rows[1:]:

        row = row + [""] * (len(headers) - len(row))

        records.append(
            dict(zip(headers, row))
        )

    return records


def update_cell(name, row, col, value):

    if col <= 26:

        column_letter = chr(64 + col)

    else:

        column_letter = ""

        n = col

        while n > 0:

            n, remainder = divmod(n - 1, 26)

            column_letter = (
                chr(65 + remainder)
                + column_letter
            )

    path = (
        f"/values/{name}!"
        f"{column_letter}{row}:"
        f"{column_letter}{row}"
        f"?valueInputOption=RAW"
    )

    sheet_req(
        "PUT",
        path,
        {
            "values": [[value]]
        }
    )


# =========================
# LẤY NỘI DUNG BÀI
# =========================

def get_article_content(link):

    if not link:
        return ""

    response = requests.get(
        link,
        timeout=20,
        headers={
            "User-Agent":
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    for element in soup(
        [
            "script",
            "style",
            "noscript",
            "nav",
            "footer",
            "header",
            "form"
        ]
    ):
        element.decompose()

    paragraphs = []

    for p in soup.find_all("p"):

        text = p.get_text(
            " ",
            strip=True
        )

        if len(text) >= 40:
            paragraphs.append(text)

    paragraphs = paragraphs[:20]

    return "\n\n".join(paragraphs)


# =========================
# GEMINI - TỪ KHÓA ẢNH
# =========================

def extract_keywords(title, content):

    prompt = f"""
Bạn là biên tập viên bóng đá.

Hãy đọc tiêu đề và nội dung dưới đây.

Nhiệm vụ:
Tạo 3-5 từ khóa tiếng Anh để tìm
ảnh bóng đá phù hợp trên Pexels.

Ưu tiên:
- đội bóng
- cầu thủ
- giải đấu
- trận đấu
- bóng đá
- chủ đề chính của bài

CHỈ trả về các từ khóa,
cách nhau bằng dấu phẩy.

Không giải thích.

TIÊU ĐỀ:
{title}

NỘI DUNG:
{content[:4000]}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    if not response.text:
        return "football"

    keywords = response.text.strip()

    keywords = re.sub(
        r"[*#`\"]",
        "",
        keywords
    )

    return keywords[:200]


# =========================
# PEXELS
# =========================

def get_image(keywords):

    if not PEXELS_API_KEY:

        print(
            "⚠️ Không có PEXELS_API_KEY "
            "→ dùng ảnh mặc định"
        )

        return FALLBACK_IMAGE

    try:

        query = "football " + keywords

        response = requests.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": query,
                "per_page": 5
            },
            headers={
                "Authorization": PEXELS_API_KEY
            },
            timeout=15
        )

        if response.status_code != 200:

            print(
                "⚠️ Pexels lỗi:",
                response.status_code
            )

            return FALLBACK_IMAGE

        data = response.json()

        photos = data.get(
            "photos",
            []
        )

        if not photos:

            print(
                "⚠️ Không tìm thấy ảnh Pexels"
            )

            return FALLBACK_IMAGE

        photo = photos[0]

        src = photo.get(
            "src",
            {}
        )

        image = (
            src.get("large")
            or src.get("original")
            or FALLBACK_IMAGE
        )

        return image

    except Exception as e:

        print(
            "⚠️ Lỗi Pexels:",
            e
        )

        return FALLBACK_IMAGE


# =========================
# GEMINI - VIẾT LẠI BÀI
# =========================

def rewrite_article(
    title,
    content,
    source,
    link
):

    prompt = f"""
Bạn là một biên tập viên bóng đá chuyên nghiệp.

Hãy viết lại bài viết dưới đây thành
một bài tin bóng đá tiếng Việt
hấp dẫn, tự nhiên, dễ đọc.

YÊU CẦU:

- Không sao chép nguyên văn.
- Không bịa thêm sự kiện.
- Không tự tạo số liệu.
- Không thay đổi sự thật.
- Giữ chính xác tên cầu thủ,
  đội bóng, giải đấu và sự kiện.
- Viết theo phong cách báo bóng đá hiện đại.
- Tiêu đề hấp dẫn nhưng không giật tít sai.
- Mở bài tạo sự tò mò.
- Chia đoạn ngắn, dễ đọc trên điện thoại.
- Có thể sử dụng tiêu đề phụ khi phù hợp.
- Nếu nguồn không xác nhận điều gì,
  không được biến nó thành sự thật.
- Không thêm thông tin ngoài nội dung nguồn.

Cuối bài bắt buộc ghi:

Nguồn: {source}
Link nguồn: {link}

TIÊU ĐỀ GỐC:
{title}

NỘI DUNG GỐC:
{content}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    if not response.text:

        raise Exception(
            "Gemini không trả về nội dung"
        )

    return response.text.strip()


# =========================
# TÊN FILE
# =========================

def safe_filename(title):

    name = re.sub(
        r"[^\w\s-]",
        "",
        title
    )

    name = re.sub(
        r"\s+",
        "-",
        name
    )

    name = name.strip("-")

    if not name:
        name = "tin-bong-da"

    return name[:70]


# =========================
# BẮT ĐẦU
# =========================

print(
    "========================================"
)

print(
    "🔥 BẮT ĐẦU XỬ LÝ TIN NÓNG"
)

print(
    "========================================"
)


try:

    rows = get_records()

except Exception as e:

    print(
        "❌ Không đọc được Google Sheets:",
        e
    )

    raise


print(
    f"✅ Đọc được {len(rows)} dòng"
)


processed = 0
skipped = 0
errors = 0


# =========================
# XỬ LÝ TỪNG DÒNG
# =========================

for idx, row in enumerate(
    rows,
    start=2
):

    status = str(
        row.get(
            "Trạng thái",
            ""
        )
    ).strip()

    if status != "Chờ xử lý":

        skipped += 1

        continue


    title = str(
        row.get(
            "Tiêu đề",
            ""
        )
    ).strip()


    link = str(
        row.get(
            "Link bài viết",
            ""
        )
    ).strip()


    source = str(
        row.get(
            "Nguồn",
            ""
        )
    ).strip()


    if not link:

        print(
            f"⚠️ Dòng {idx}: không có link"
        )

        update_cell(
            SHEET_NAME,
            idx,
            7,
            "❌ Không có link"
        )

        errors += 1

        continue


    print("")
    print(
        "----------------------------------------"
    )

    print(
        f"🔄 {idx}: {title[:80]}"
    )


    try:

        # Lấy bài gốc
        content = get_article_content(link)

        print(
            f"📄 Nội dung: {len(content)} ký tự"
        )


        if len(content) < 150:

            update_cell(
                SHEET_NAME,
                idx,
                7,
                "❌ Nội dung quá ngắn"
            )

            print(
                "⚠️ Nội dung quá ngắn"
            )

            errors += 1

            continue


        # Gemini tạo từ khóa ảnh
        keywords = extract_keywords(
            title,
            content
        )

        print(
            f"🔑 Từ khóa: {keywords}"
        )


        # Pexels
        image_url = get_image(
            keywords
        )

        print(
            f"🖼️ Ảnh: {image_url[:100]}"
        )


        # Ghi dữ liệu vào Sheet
        update_cell(
            SHEET_NAME,
            idx,
            10,
            keywords
        )

        update_cell(
            SHEET_NAME,
            idx,
            11,
            image_url
        )

        update_cell(
            SHEET_NAME,
            idx,
            12,
            "Pexels"
        )


        # Gemini viết bài
        print(
            "🤖 Gemini đang viết lại..."
        )

        output = rewrite_article(
            title,
            content,
            source,
            link
        )


        # Tạo thư mục output
        os.makedirs(
            "output",
            exist_ok=True
        )


        date_str = datetime.now().strftime(
            "%Y-%m-%d"
        )


        filename = (
            f"{date_str}-"
            f"{safe_filename(title)}"
            f".md"
        )


        filepath = os.path.join(
            "output",
            filename
        )


        with open(
            filepath,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(output)


        # Cập nhật trạng thái
        update_cell(
            SHEET_NAME,
            idx,
            7,
            "✅ Đã xử lý"
        )


        update_cell(
            SHEET_NAME,
            idx,
            8,
            filepath
        )


        processed += 1


        print(
            f"✅ HOÀN THÀNH: {filepath}"
        )


        time.sleep(1)


    except Exception as e:

        errors += 1

        error_text = str(e)

        print(
            f"❌ LỖI: {error_text}"
        )


        try:

            update_cell(
                SHEET_NAME,
                idx,
                7,
                "❌ Lỗi: "
                + error_text[:100]
            )

        except Exception as sheet_error:

            print(
                "❌ Không thể cập nhật "
                "trạng thái Sheet:",
                sheet_error
            )


# =========================
# KẾT THÚC
# =========================

print("")

print(
    "========================================"
)

print(
    "🏁 HOÀN THÀNH"
)

print(
    "========================================"
)

print(
    f"✅ Đã xử lý: {processed}"
)

print(
    f"⏭️ Bỏ qua: {skipped}"
)

print(
    f"❌ Lỗi: {errors}"
)

print(
    "========================================"
)
