# Dashboard / Overview — bản giao diện

Mở `http://127.0.0.1:5000/dashboard` khi ứng dụng Flask đang chạy, hoặc chọn
**Overview** trong menu của My budget. **Edit budget** dẫn về kế hoạch cùng tháng.
Trang chủ tiếp tục dẫn **Start your budget** vào My budget như trước.

## Nội dung và nguồn dữ liệu

- Ba thẻ tổng quan: ngân sách kế hoạch, chi tiêu đã ghi nhận, còn lại trong kế hoạch.
- Biểu đồ bốn nhóm: tiền trọ, điện/nước/internet, ăn uống, các khoản còn lại.
  Phần trăm quanh biểu đồ là tỷ trọng trong **tổng thực chi đã ghi nhận**.
- Tiến độ P0/P1/P2 so sánh thực chi với kế hoạch của từng nhóm.
- Danh sách chi gần đây, hộp thoại xem toàn bộ, thêm khoản chi thử và check-in.
- EN/VI dùng cơ chế ngôn ngữ có sẵn; số và ngày đổi định dạng theo ngôn ngữ.

Tháng minh họa 11/2026 dùng nguồn tiền 6.000.000 đồng, kế hoạch 4.900.000 đồng,
đã chi 3.400.000 đồng, còn lại trong kế hoạch 1.500.000 đồng. **1.100.000 đồng
chưa phân bổ** là số khác với phần còn lại sau chi tiêu. Dữ liệu minh họa được
cập nhật đến ngày 11/11; ngày check-in minh họa là 12/11. Các tháng khác mở với
danh sách chi trống. Không coi danh sách trống là xác nhận không chi tiêu.

Nếu My budget có kế hoạch đã lưu trên trình duyệt cho tháng đang xem, Dashboard
đọc kế hoạch đó để tính số liệu. Dashboard không ghi đè kế hoạch ngân sách.
Chi tiêu có thể vượt kế hoạch: số còn lại âm và phần trăm thực dùng vẫn hiển thị;
thanh màu chỉ giới hạn ở chiều rộng của khung.

## Các thao tác bản thử

**Add expense** mở hộp thoại nhập tên, danh mục, số nguyên dương VNĐ và ngày.
Ngày phải thuộc tháng đang xem và không sau ngày minh họa hiển thị. **Save preview**
cập nhật các thẻ, biểu đồ, danh sách và trạng thái check-in trên trình duyệt này.
**No spending today** là xác nhận rõ ràng cho ngày minh họa; nếu đã có khoản chi
ngày đó thì không thể xác nhận không chi. Thao tác lặp không tạo thêm giao dịch.

Dữ liệu bản thử lưu riêng từng tháng tại `budget-companion:dashboard-preview:v1`.
Kế hoạch vẫn ở `budget-companion:workspace:v1`. Không có dữ liệu tài khoản,
thanh toán, bản ghi chi thật, hay API nghiệp vụ mới trong thay đổi giao diện này.
Trang Expenses, Check-in và các mục khác vẫn để giai đoạn sau. Check-in trên
Dashboard là minh họa thao tác theo ngày, không xử lý trạng thái task chính thức.

Không tự xóa/ghi đè dữ liệu lỗi. Trang báo lỗi nếu không đọc được dữ liệu hoặc có
thay đổi cùng tháng ở thẻ khác; tải lại trang để lấy bản mới trước khi ghi tiếp.
Khi tích hợp, thay nguồn dữ liệu bản thử bằng dữ liệu của module Budget/Expenses,
giữ đúng quy tắc chống trùng, trạng thái chưa ghi nhận và giới hạn truy cập người dùng.

## File để chỉnh giao diện

| Nội dung | File |
| --- | --- |
| Bố cục Dashboard | `app/templates/pages/dashboard.html` |
| Màu, thẻ, biểu đồ, màn hình nhỏ | `app/static/css/dashboard.css` |
| Tính toán, biểu đồ, các thao tác bản thử | `app/static/js/dashboard.js` |
| Dữ liệu minh họa ban đầu | `dashboard_preview()` trong `app/ui_demo.py` |
| Văn bản EN/VI | `DASHBOARD_MESSAGES` trong `app/translations.py` |

Chạy kiểm tra bằng `python -m pytest -q`. Kiểm tra thêm trong trình duyệt với
EN/VI, màn hình máy tính/điện thoại, thay kế hoạch ngân sách, thêm khoản chi,
tháng trống và số tiền vượt kế hoạch.
