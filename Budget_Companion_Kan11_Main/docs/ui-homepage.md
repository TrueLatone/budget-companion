# Trang chủ Budget Companion

Giao diện web hỗ trợ tiếng Anh và tiếng Việt, mặc định là tiếng Anh. Trang `/` là trang giới thiệu sản phẩm, gồm menu, phần mở đầu, ba lợi ích,
ba bước sử dụng, lời mời bắt đầu và chân trang. Phong cách: xanh tím, lavender,
coral nhẹ; tiêu đề Lora và nội dung Be Vietnam Pro.

## Chỉnh ở đâu?

| Nội dung | File |
| --- | --- |
| Nội dung và thứ tự các phần | `app/templates/pages/home.html` |
| Menu và liên kết | `app/templates/components/navbar.html` |
| Khung trang, font và tài nguyên chung | `app/templates/base.html` |
| Màu, chữ, khoảng cách, bố cục theo chiều rộng | `app/static/css/app.css` |
| Menu thu gọn và trạng thái điều hướng | `app/static/js/app.js` |
| Biểu tượng dùng chung | `app/templates/components/icons.html` |
| Hình minh họa đầu trang | `app/static/images/home-hero.webp` |
| Nội dung tiếng Anh và tiếng Việt | `app/translations.py` |
| Chọn và ghi nhớ ngôn ngữ | `app/i18n.py` |

Màu nằm trong các biến `--bc-*` ở đầu file CSS. Để thay ảnh, dùng một ảnh
ngang tỉ lệ 3:2 và cập nhật đường dẫn, kích thước cùng mô tả `alt` trong `home.html`.

## Xem trên máy

Mở Terminal tại thư mục dự án, dùng môi trường Python đã cài thư viện:

```sh
source .venv/bin/activate
python -m flask --app app run --debug
```

Mở `http://127.0.0.1:5000`, lưu file đã chỉnh rồi tải lại trang.
Kiểm tra hiện có: `python -m pytest -q`.

## Chuyển ngôn ngữ

Chọn **EN** hoặc **VI** trên menu. Trên màn hình nhỏ, mở menu để thấy hai lựa chọn.
Website ghi nhớ lựa chọn trong trình duyệt, kể cả khi tải lại hoặc mở trang chức năng khác.
Bạn cũng có thể mở `/?lang=en` hoặc `/?lang=vi` để chọn trực tiếp.

Nội dung song ngữ nằm trong `MESSAGES` của `app/translations.py`. Khi thêm chữ mới,
thêm cùng một khóa vào cả hai ngôn ngữ rồi dùng `{{ t('ten_khoa') }}` trong template.
Giữ thẻ HTML trong template; chỉ đặt nội dung chữ trong bản dịch. Dùng `money(5000000)`
để hiện `5,000,000` ở tiếng Anh hoặc `5.000.000` ở tiếng Việt; đơn vị vẫn là VNĐ.
Đây là phần giao diện, không thay đổi dữ liệu hay các API chức năng của nhóm.

## Phạm vi hiện tại

- Menu Features và How it works dẫn đến các phần trong trang chủ.
- Các nút ngân sách, chi tiêu, tổng quan, gợi ý và tài khoản dùng route hiện có.
- Những route chức năng vẫn đang là trang placeholder của dự án. Đăng nhập,
  nhập ngân sách và ghi chi tiêu sẽ được nối với phần xử lý của từng module sau.
- Các thẻ nhỏ trong phần ba bước là minh họa bằng HTML, có nhãn dữ liệu minh họa.
- Bootstrap và Google Fonts hiện được nạp từ CDN như cấu trúc khởi đầu của dự án.

## Nguồn hình minh họa

Hình được tạo bằng công cụ ImageGen tích hợp, sau đó nén sang WebP để tải nhanh.
File WebP là tài nguyên riêng; phần chữ, menu, nút và nội dung trang được dựng bằng HTML/CSS.

Prompt tạo ảnh (dùng bản mẫu trang chủ đã được duyệt làm tham khảo):

```text
Use case: stylized-concept. Asset type: single reusable landscape homepage hero illustration, 3:2 ratio, 1536x1024 if possible. Reference image is only a STYLE AND SUBJECT REFERENCE, NOT an edit target. Generate only the cozy student desk scene seen at upper-right of the supplied homepage mockup, as a standalone image; do not reproduce the web page. An open modern laptop on a pale warm wooden student desk, viewed from a pleasing slightly elevated three-quarter front angle. Its screen is a beautifully minimal abstract budget interface with soft lavender charts: three small pastel summary panels, a violet line graph and a coral/lavender donut chart, all completely without text, words, letters, numbers or logos. Keep a lavender ceramic mug and two neutral books to the left, a restrained small green plant near a bright window in back right, and a closed cream notebook with pen on right. Soft hand-painted / refined 3D illustration with believable materials, gentle sunlight, soft shadows, cozy calm atmosphere. Palette warm white #FAF9FD, lavender #EEEAFE, violet #5B55D9 with very small coral #F27A65 accents; soft natural green plants and warm neutral desk. Composition: laptop is visual focus slightly right of center; all important objects fit within canvas with generous clean pale margins; no cropped screen or cut-off laptop. White/pale lavender outer edges, especially left, softly fade into nearly white background so image blends with a white/lavender webpage. No full webpage, no headline, no CTA buttons outside the laptop, no header, no footer, no device surrounding the whole scene, no people, no currency symbols, no numerals, no words anywhere including mug/books/notebook. This will be placed on right side of a real webpage with separately rendered HTML text on left.
```
