# Tự gỡ `blocked` cho issue

Workflow **Issue readiness** chuyển issue đang mở từ `blocked` sang `ready` khi có đúng một assignee, đầu vào đã được chủ repo xác nhận và mọi tiền nhiệm đều đã nghiệm thu. Quy tắc review, CI, squash merge và bằng chứng thực nghiệm áp dụng theo quy trình nhóm và điều kiện của từng ticket. [Quy tắc nhóm §1, §3–4](../../CONTRIBUTING.md) · [Backlog](../../plan/BACKLOG.md) · [Thứ tự PLARS và demo](../governance/adr/0002-plars-integration-order.md)

## Xác nhận trên GitHub

1. Gán người phụ trách và thêm các issue tiền nhiệm trong **Relationships → Blocked by** của issue đang chờ. Workflow đọc quan hệ giữa các issue trong cùng repo. [Quan hệ phụ thuộc của GitHub](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies)
2. Khi đầu vào đã có, chủ repo đăng `/inputs-ready #5 #23` trên dòng đầu của một bình luận nếu danh sách tiền nhiệm là `#5` và `#23`. Với issue độc lập, dùng `/inputs-ready none`. Có thể ghi cấu hình và đường dẫn hiện vật đã lược bí mật ở các dòng tiếp theo. Xác nhận đầu vào có thể thực hiện trước khi các issue tiền nhiệm hoàn tất.
3. Sau khi mỗi issue tiền nhiệm được đóng với lý do **Completed**, chủ repo đăng `/accepted #42 https://may-chu/duong-dan-bang-chung` trên dòng đầu của một bình luận. Dùng số của tất cả PR đầu ra và một đường dẫn đến bằng chứng nghiệm thu. Workflow kiểm tra các PR được liệt kê đã được chủ repo merge vào `main` trước lúc xác nhận. Bình luận của chủ repo xác nhận rằng approval hợp lệ trên commit cuối, kiểm tra bắt buộc đạt, phương thức merge là squash và bằng chứng nghiệm thu đã được kiểm tra. Với quyết định hoặc công việc không có PR, dùng `/accepted none https://may-chu/duong-dan-bang-chung`.

Các số và đường dẫn trên là ví dụ cú pháp. Sau khi sửa mô tả issue, đăng xác nhận mới. Nếu danh sách tiền nhiệm thay đổi, đăng lại `/inputs-ready` với danh sách mới. Dùng `/inputs-pending` hoặc `/acceptance-revoked` để rút xác nhận tương ứng. Khi cần chặn lại một issue đã được chuyển sang `ready`, đăng `/inputs-pending`, thêm `blocked` và gỡ `ready`.

## Xem kết quả

Sau khi workflow có trên `main`, các sự kiện issue và bình luận xác nhận sẽ kích hoạt lượt kiểm tra. Workflow còn quét theo lịch 20 phút để đối chiếu thay đổi quan hệ và xử lý lại khi có lỗi tạm thời. Trong **Actions → Issue readiness**, xem số issue và điều kiện còn thiếu trong phần tóm tắt. Khi chạy thủ công, giữ `dry_run` để xem các issue đủ điều kiện hoặc bỏ chọn để áp dụng nhãn.

Workflow thêm `ready` trước rồi gỡ `blocked` để lượt chạy sau có thể tiếp tục nếu API ngắt giữa hai thao tác. Issue còn `blocked` vẫn chờ. Cơ chế tự động chỉ chuyển các issue đang mang `blocked` theo chiều sang `ready`. GitHub ghi thao tác cập nhật nhãn trong lịch sử issue.
