"""Localize errors at the web boundary; services retain their stable messages."""
import re
from app.i18n import get_ui_language

VI = {
    "Funds are locked after generating plans.": "Nguồn tiền gốc đã khóa vì tháng này đã có phương án.",
    "Enter multiples of 1,000 VND.": "Nhập số tiền theo bội số 1.000 ₫.",
    "Authentication required": "Vui lòng đăng nhập.",
    "Expense names must be unique within the month.": "Tên khoản chi đã tồn tại trong tháng này.",
    "Due day must be 1 to 31 and only applies to monthly expenses.": "Ngày đến hạn chỉ áp dụng cho khoản hằng tháng, từ 1 đến 31.",
    "Due day must be an integer from 1 to 31.": "Nhập ngày đến hạn là số nguyên từ 1 đến 31.",
    "Only P1 expenses may specify a minimum.": "Chỉ khoản P1 mới có mức tối thiểu.",
    "Allocations exceed available funds.": "Tổng phân bổ vượt quá nguồn tiền của tháng.",
    "Enter an expense name of 1 to 120 characters.": "Nhập tên khoản chi từ 1 đến 120 ký tự.",
    "Enter a category name of 1 to 100 characters.": "Nhập tên danh mục từ 1 đến 100 ký tự.",
    "Choose a valid priority and allocation frequency.": "Chọn mức ưu tiên và tần suất hợp lệ.",
    "This field is required.": "Vui lòng điền trường này.",
    "Not a valid choice.": "Vui lòng chọn một giá trị trong danh sách.",
    "This budget month is already confirmed.": "Ngân sách tháng này đã được xác nhận.",
    "This month's confirmed plan and expense setup are locked.": "Tháng đã xác nhận và đã khóa các khoản phân bổ.",
    "Only unconfirmed plans can be customized.": "Chỉ có thể điều chỉnh kế hoạch chưa xác nhận.",
    "Internet, when included, must be P0.": "Khoản Internet phải thuộc P0.",
    "Select at least one valid suggested expense, once each.": "Chọn ít nhất một khoản gợi ý hợp lệ. Mỗi khoản chỉ chọn một lần.",
    "Submit exactly one amount for each P1 and P2 expense.": "Mỗi khoản P1 và P2 cần đúng một số tiền.",
    "Allocations plus planned savings must exactly equal available funds; generate plans again.": "Tổng phân bổ và tiết kiệm phải bằng nguồn tiền. Hãy tạo lại kế hoạch.",
    "The transaction date must belong to this month's tracking interval.": "Ngày giao dịch phải nằm trong thời gian theo dõi của tháng.",
    "Future spending cannot be recorded.": "Chưa thể ghi nhận chi tiêu cho ngày tương lai.",
    "Future tasks cannot be checked in.": "Chưa đến ngày ghi nhận khoản chi này.",
    "The transaction date must be within the task's assigned period.": "Ngày giao dịch phải nằm trong kỳ phân bổ của khoản chi.",
    "Choose planned, actual or no_expense.": "Chọn theo kế hoạch, số tiền thực tế hoặc không phát sinh.",
    "A planned check-in can only be recorded once per task.": "Mỗi khoản chỉ được ghi nhận theo kế hoạch một lần.",
    "This task has actual transactions. Remove or correct them before confirming NO_EXPENSE.": "Khoản này đã có giao dịch. Hãy sửa hoặc xóa giao dịch trước khi chọn không phát sinh.",
    "This task already has spending. Add a separate actual purchase or edit a transaction.": "Khoản này đã ghi nhận chi tiêu. Hãy nhập giao dịch mới hoặc sửa giao dịch hiện có.",
    "Only bill tasks have a payment status.": "Chỉ hóa đơn mới có trạng thái thanh toán.",
    "Notes must be at most 2000 characters.": "Ghi chú tối đa 2.000 ký tự.",
    "Titles must be at most 120 characters.": "Tên khoản chi tối đa 120 ký tự.",
    "Invalid budget impact scope.": "Phạm vi ảnh hưởng ngân sách không hợp lệ.",
    "No budget expenses or plan exist. Add expenses in Budget setup first.": "Hãy thêm khoản chi để lập ngân sách tháng.",
    "No budget plan exists. Generate plans in Budget setup first.": "Hãy tạo kế hoạch từ các khoản chi đã nhập.",
    "No confirmed plan exists. Review and confirm a saved Budget plan first.": "Hãy xác nhận một phương án để tạo lịch.",
    "The confirmed plan has no allocations to schedule. Review the saved Budget plan.": "Kế hoạch đã chốt chưa có khoản phân bổ.",
    "rating must be an integer from 1 to 5": "Điểm đánh giá phải là số nguyên từ 1 đến 5.",
    "comment must be text of at most 2000 characters": "Nhận xét tối đa 2.000 ký tự.",
    "as_of must be within the selected month and cannot be a future date": "Chọn ngày trong tháng đã chọn và không sau hôm nay.",
    "decision must be ACCEPT or REJECT": "Hãy chọn chấp nhận hoặc từ chối.",
    "This recommendation has already been decided": "Bạn đã phản hồi đề xuất này.",
    'Budget month not found.': 'Không tìm thấy tháng ngân sách.',
    'Budget month not found': 'Không tìm thấy tháng ngân sách.',
    'Budget month was not found for this user': 'Không tìm thấy tháng ngân sách.',
    'Expense resource not found.': 'Không tìm thấy khoản chi.',
    'Budget expense not found.': 'Không tìm thấy khoản chi.',
    'Spending record not found.': 'Không tìm thấy khoản chi.',
    'Task not found.': 'Không tìm thấy khoản chi.',
    'Category not found.': 'Không tìm thấy danh mục.',
    'Spending category not found.': 'Không tìm thấy danh mục.',
    'Budget plan not found.': 'Không tìm thấy kế hoạch đã lưu.',
    'Budget resource not found.': 'Không tìm thấy kế hoạch đã lưu.',
    'Only confirmed allocations in the same month may be scheduled.': 'Khoản tiền phải thuộc đúng tháng của kế hoạch đã xác nhận.',
    'A transaction and its task must belong to the same month.': 'Khoản tiền phải thuộc đúng tháng của kế hoạch đã xác nhận.',
    'The saved plan references an expense outside its month.': 'Khoản tiền phải thuộc đúng tháng của kế hoạch đã xác nhận.',
    "Tracking must start within the allocation's month.": 'Ngày bắt đầu theo dõi phải thuộc tháng đã chọn.',
    'Tracking start date must be a date within the budget month.': 'Ngày bắt đầu theo dõi phải thuộc tháng đã chọn.',
    'Invalid canonical allocation frequency.': 'Tần suất phân bổ không hợp lệ.',
    'This retry token belongs to a different transaction.': 'Mã gửi lại đã được dùng cho giao dịch khác. Hãy mở lại biểu mẫu.',
    'This retry token was already used for a different transaction.': 'Mã gửi lại đã được dùng cho giao dịch khác. Hãy mở lại biểu mẫu.',
    'A retry token of 1 to 64 characters is required.': 'Mã xác nhận không hợp lệ. Hãy mở lại biểu mẫu.',
    'Confirm a budget plan before creating its spending schedule.': 'Hãy xác nhận kế hoạch trước khi tạo lịch.',
    'Tasks must be scheduled after confirmation.': 'Hãy xác nhận kế hoạch trước khi tạo lịch.',
    'A concurrent write changed the expense data. Reload and retry using the same token.': 'Dữ liệu vừa thay đổi. Hãy tải lại trang và thử lại.',
    'Concurrent metadata write; reload and retry.': 'Dữ liệu vừa thay đổi. Hãy tải lại trang và thử lại.',
    'The budget changed concurrently or violates a saved constraint. Reload and try again.': 'Dữ liệu vừa thay đổi. Hãy tải lại trang và thử lại.',
    'Existing task dates differ from this confirmed schedule.': 'Lịch đã lưu khác với phân bổ ban đầu. Hãy kiểm tra kế hoạch đã xác nhận.',
    'Existing task limits or periods differ; original schedules cannot be overwritten.': 'Lịch đã lưu khác với phân bổ ban đầu. Hãy kiểm tra kế hoạch đã xác nhận.',
    'The schedule must conserve its complete monthly allocation.': 'Tổng hạn mức trong lịch phải bằng phân bổ tháng.',
    'Available funds must be a nonnegative integer VND amount.': 'Nguồn tiền phải là số nguyên VND không âm.',
    'A spending record has no valid priority.': 'Hãy chọn mức ưu tiên P0, P1 hoặc P2.',
    'Every expense needs a P0/P1/P2 priority.': 'Hãy chọn mức ưu tiên P0, P1 hoặc P2.',
    'Every included expense requires an allocation.': 'Mỗi khoản chi cần đúng một mức phân bổ trong tháng này.',
    'Allocations must reference each expense in this month exactly once.': 'Mỗi khoản chi cần đúng một mức phân bổ trong tháng này.',
    'Review the latest manual plan before confirming.': 'Bản tùy chỉnh đã thay đổi. Hãy tải lại để xem số tiền mới nhất.',
    'The manual plan changed in another tab. Review the latest amounts before confirming.': 'Bản tùy chỉnh đã thay đổi. Hãy tải lại để xem số tiền mới nhất.',
    'The plan was changed in another tab. Reload before customizing.': 'Bản tùy chỉnh đã thay đổi. Hãy tải lại để xem số tiền mới nhất.',
    'Choose an existing category or enter a new category, not both.': 'Chọn một danh mục hiện có hoặc nhập một danh mục mới.',
    'Recurring must be a boolean.': 'Giá trị lặp lại phải là có hoặc không.',
    'Invalid suggested expense values.': 'Thông tin khoản chi gợi ý không hợp lệ.',
    'Invalid suggested expense fields.': 'Thông tin khoản chi gợi ý không hợp lệ.',
    'Multiple manual drafts exist. Resolve the duplicate before saving.': 'Đã có nhiều bản tùy chỉnh cho tháng này. Cần xử lý bản trùng trước khi lưu.',
    'Invalid allocation changes.': 'Khoản phân bổ đã thay đổi. Hãy tạo lại kế hoạch.',
    'Stored customized allocations are inconsistent.': 'Khoản phân bổ đã thay đổi. Hãy tạo lại kế hoạch.',
    'Customized plan contains outdated expenses. Regenerate plans.': 'Khoản phân bổ đã thay đổi. Hãy tạo lại kế hoạch.',
    'Only a generated budget option can be customized.': 'Chỉ có thể xác nhận hoặc điều chỉnh phương án đã tạo.',
    'Only a generated plan can be confirmed.': 'Chỉ có thể xác nhận hoặc điều chỉnh phương án đã tạo.',
    'An expense references an unauthorized category.': 'Khoản chi dùng danh mục bạn không có quyền truy cập.',
    'A draft plan has scheduled tasks; it cannot be replaced.': 'Phương án đã có lịch và đã được khóa.',
    'A scheduled plan cannot be customized.': 'Phương án đã có lịch và đã được khóa.',
    'A scheduled customized plan cannot be overwritten.': 'Phương án đã có lịch và đã được khóa.',
    'A JSON object is required': 'Dữ liệu gửi lên phải là một đối tượng JSON.',
    'Invalid calendar month': 'Tháng không hợp lệ.',
    'month must use YYYY-MM format': 'Tháng không hợp lệ.',
    'as_of must use YYYY-MM-DD format': 'Ngày phân tích phải có định dạng YYYY-MM-DD.',
    'Invalid as_of date': 'Ngày phân tích phải có định dạng YYYY-MM-DD.',
    'Recommendation was not found': 'Không tìm thấy đề xuất.',
    'Resource not found.': 'Không tìm thấy đề xuất.',
    'Saved task limits must be known nonnegative integer VND.': 'Hạn mức đã lưu phải là số nguyên không âm.',
    'Saved Budget/Expense references need correction before analysis.': 'Cần kiểm tra liên kết giữa kế hoạch và khoản chi trước khi phân tích.',
    'This legacy proposal is read-only and cannot be accepted. Refresh recommendations from current data.': 'Đề xuất cũ chỉ cho phép xem. Hãy cập nhật đề xuất từ dữ liệu hiện tại.',
    'This duplicate confirmation is no longer available.': 'Yêu cầu xác nhận giao dịch trùng đã hết hạn hoặc đã được xử lý.',
    'This duplicate confirmation was already used or has expired. Nothing was saved again.': 'Yêu cầu xác nhận giao dịch trùng đã hết hạn hoặc đã được xử lý.',

}

def ui_error(value):
    text = str(value)
    if get_ui_language() != "vi":
        return text
    for label, translated in (("Monthly allocation","Phân bổ tháng"),("Payment status","Trạng thái thanh toán"),("Priority","Mức ưu tiên")):
        if text.startswith(label + " ") and not text.isascii():
            return translated + text[len(label):]
    if text in VI:
        return VI[text]
    if text.startswith("Required P0 expenses are missing:"):
        return "Thiếu khoản P0 bắt buộc: " + text.partition(":")[2].strip()
    if text.startswith("Budget shortfall:"):
        return "Nguồn tiền còn thiếu " + re.search(r"(\d+) more", text).group(1) + " VND để đáp ứng các khoản bắt buộc."
    if "below its P1 minimum" in text:
        return text.split(" allocation")[0] + ": số tiền thấp hơn mức tối thiểu P1."
    if "must receive its exact" in text:
        return "Số tiền của khoản P0 phải bằng đúng mức đã thiết lập."
    if "integer VND" in text or "VND limit" in text:
        field = text.split(" must")[0].split(" exceeds")[0]
        name = {"Available funds":"Nguồn tiền","Minimum amount":"Mức tối thiểu","Estimated amount":"Ước tính","Allocated amount":"Số phân bổ","Planned savings":"Tiết kiệm"}.get(field, field.replace(" amount","") if field.startswith("P0 ") else "Số tiền")
        rule = "là số nguyên dương" if "positive" in text else "là số nguyên không âm"
        return f"{name} phải {rule} trong giới hạn cho phép (VND)."
    groups = [
        (("not found","was not found","unauthorized","outside its month"),"Không tìm thấy dữ liệu trong ngân sách của bạn."),
        (("another tab","reload","latest manual","retry token","duplicate confirmation"),"Dữ liệu đã thay đổi hoặc phiên thao tác đã hết hạn. Hãy tải lại trang và kiểm tra trước khi thử lại."),
        (("scheduled","saved task","schedule","assigned period"),"Lịch hiện có không khớp với kế hoạch. Hãy kiểm tra lại tháng và phân bổ đã xác nhận."),
        (("required","needs a","requires an","exactly once"),"Hãy kiểm tra các trường bắt buộc và nhập đủ thông tin cho từng khoản chi."),
        (("generated","draft","customized","manual","allocation"),"Hãy kiểm tra lại các khoản phân bổ và mở bản kế hoạch mới nhất."),
        (("date","month","yyyy"),"Ngày hoặc tháng đã chọn không hợp lệ."),
        (("csrf","session"),"Phiên biểu mẫu đã hết hạn hoặc không hợp lệ. Hãy tải lại trang và thử lại."),
    ]
    for keys, message in groups:
        if any(key in text.lower() for key in keys):
            return message
    if any(ord(c)>127 for c in text):
        return text
    return "Dữ liệu gửi lên không hợp lệ. Vui lòng kiểm tra lại thông tin."
