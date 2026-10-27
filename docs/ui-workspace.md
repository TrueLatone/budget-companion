# Giao diện My budget

Khung ứng dụng dùng chung hiện có My budget (`/budget`) và Overview (`/dashboard`).
Expenses, Check-in, Spending tips, Settings và Help vẫn ở trạng thái chờ.
Hướng dẫn Dashboard và các thao tác bản thử nằm trong `docs/ui-dashboard.md`.

## Mở trên local

Tại thư mục dự án:

```sh
source .venv/bin/activate
python -m flask --app app run --debug
```

Mở `http://127.0.0.1:5000/` rồi bấm **Start your budget**, hoặc mở trực tiếp
`http://127.0.0.1:5000/budget`.

## Phạm vi bản thử

- Giao diện bám theo mẫu đã thống nhất: sidebar, ô nhập và bảng tổng hợp.
- Chuyển EN/VI sử dụng cơ chế ngôn ngữ hiện có của website.
- Đổi nguồn tiền hoặc số tiền các khoản chi để cập nhật phân bổ, tổng và phần còn lại.
- Chỉ nhận số nguyên dương bằng VNĐ; phân bổ vượt nguồn tiền sẽ được báo lỗi.
- Có hộp thoại thêm khoản chi tùy chỉnh và xóa các khoản tùy chỉnh đó.
- Nút **Save budget** lưu bản thử vào trình duyệt và giữ người dùng tại My budget.
- Lưu riêng theo từng tháng. Dữ liệu chỉ có trên trình duyệt đang sử dụng;
  không tạo ngân sách đã xác nhận trên tài khoản hoặc cơ sở dữ liệu.
- Các giá trị ban đầu là ví dụ: nguồn tiền 6.000.000 đồng, phân bổ 4.900.000 đồng,
  chưa phân bổ 1.100.000 đồng. Tháng minh họa ban đầu là 11/2026.

Đây là giao diện thử, chưa thay thế nghiệp vụ Budget Planning của nhóm. Chưa có
gợi ý kế hoạch, kiểm tra mức tối thiểu P1, xác nhận/khóa ngân sách, lịch chi tiêu
hay kết nối các API đang đề xuất. Khi tích hợp, dùng dữ liệu và quy tắc do module
Budget Planning cung cấp; không coi dữ liệu mẫu là kết quả xử lý nghiệp vụ.

## Các file chính

| Phần | File |
| --- | --- |
| Trang My budget | `app/templates/pages/budget.html` |
| Khung ứng dụng và menu | `app/templates/workspace_base.html`, `app/templates/components/workspace_nav.html` |
| Màu, bố cục và màn hình nhỏ | `app/static/css/workspace.css` |
| Tính tổng, thêm khoản chi và lưu trình duyệt | `app/static/js/workspace.js` |
| Nội dung song ngữ | `WORKSPACE_MESSAGES` trong `app/translations.py` |
| Dữ liệu minh họa và tháng | `app/ui_demo.py` |

Khung trang gốc có các block để tái sử dụng; trang chủ tiếp tục dùng menu và giao
diện cũ. Dashboard dùng khung này để đọc kế hoạch đã lưu, nhưng không tự thay đổi
ngân sách. Không thay đổi schema hay các API nghiệp vụ.

Kiểm tra: `python -m pytest -q` và kiểm tra thao tác thực tế trong trình duyệt.
