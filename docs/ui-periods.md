# Prototype UI cho tạo kỳ và xem tổng quan

Mở `/budget-periods` hoặc chọn Budget periods trong menu ứng dụng.

Phạm vi đề xuất của **Create a Monthly Budget Period** trong bản này: chọn tháng/năm,
xem ngày đầu và ngày cuối tháng, tạo kỳ, kiểm tra tháng đã tồn tại, xem thông báo thành
công và mở Overview của kỳ đó. Chưa có đặc tả use case chính thức của nhóm trong
các file đã cung cấp; tên và luồng này cần được đối chiếu với bản đặc tả nhóm chốt.

Tạo kỳ không tự nhập nguồn tiền hoặc phân bổ P0/P1/P2. Bản ghi kỳ gồm tháng và
thời điểm tạo tại khóa trình duyệt `budget-companion:periods:v1`. Không sửa ngân sách
hay dữ liệu chi tiêu. Kế hoạch và lịch sử đã lưu trước đây được liệt kê lại để mở tiếp;
không cho tạo một kỳ trùng với tháng đã có dữ liệu đó. Dữ liệu lỗi được báo và giữ lại.

**View Budget Overview** dùng Dashboard hiện có. Kỳ vừa tạo không lấy số tiền hoặc
khoản chi từ tháng minh họa: ngân sách và phần còn lại hiển thị chưa thiết lập, tổng
chi đã ghi nhận bằng 0, biểu đồ trống. Số 0 này là tổng bản ghi hiện có, không phải xác
nhận người dùng không chi tiêu. Nút Set up budget mở My budget đúng tháng. Sau khi
lưu kế hoạch, Overview đọc số liệu kế hoạch và cập nhật phép so sánh.

Trang Dashboard thông thường vẫn có ví dụ tháng 11/2026 đã duyệt; các kỳ được tạo
qua luồng mới có trạng thái riêng. Tạo kỳ và xem tổng quan là hai use case khác nhau.
Phần check-in theo khoản chi chưa được bổ sung trong đợt này.

Các trạng thái để chụp prototype: chọn tháng/ngày theo lịch; chưa chọn tháng; tạo
thành công; trùng tháng với liên kết mở kỳ đã có; Overview chưa có ngân sách;
Overview có kế hoạch và biểu đồ phần trăm; trạng thái không có khoản chi.

Mặc định tiếng Anh, có EN/VI. Đây là frontend lưu trình duyệt, chưa xác nhận kỳ ngân
sách hay kế hoạch trên tài khoản. Không thêm API, schema, đăng nhập hoặc chức năng
nghiệp vụ thuộc module khác. Không commit/push tự động.

File chính: `pages/periods.html`, `static/css/periods.css`, `static/js/periods.js`;
Dashboard đọc trạng thái kỳ qua helper `BudgetPeriodPreview`.
