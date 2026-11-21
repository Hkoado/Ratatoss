# Quy tắc làm việc nhóm Ratatoss

## 1. Nhận issue trước khi làm

- Chủ dự án phân việc qua GitHub Issues. Mỗi issue có một người phụ trách, phạm vi tệp, phụ thuộc và điều kiện nghiệm thu. Nếu có ticket backlog, ghi mã ticket trong issue.
- Dùng [mẫu issue](.github/ISSUE_TEMPLATE/ratatoss-task.md). Điền mã **Ticket** hoặc tên **Tuyến** cho việc ngoài backlog. Dùng [MAPDOCS](MAPDOCS.md) để chọn tài liệu khi bắt đầu.
- Bắt đầu bằng R0.1 khi có binary Croc đã ghim, relay thử nghiệm và fixture SHA-256. Với các ticket sau, ghi issue phụ thuộc và đầu vào còn thiếu. Tích hợp PLARS ở R2.1 trước demo nghiệm thu R1.4 theo quyết định cho bản chính thức. [Backlog](plan/BACKLOG.md) · [Thứ tự đã chốt](spec/governance/adr/0002-plars-integration-order.md)
- Dùng nhãn `blocked` khi còn thiếu phụ thuộc hoặc đầu vào. Chỉ bắt đầu triển khai khi issue đã có người phụ trách, có nhãn `ready` và đã gỡ `blocked`. Khai báo tiền nhiệm trong **Relationships → Blocked by**. Workflow kiểm tra trực tiếp PR, review, CI và hiện vật trên `main`, rồi tự đổi nhãn khi đủ điều kiện. [Cấu hình kiểm tra và cách xem kết quả](spec/operations/issue-readiness.md)
- Lấy `main` mới nhất và tạo nhánh riêng cho issue đã nhận. Nếu cần sửa ngoài phạm vi hoặc đụng tệp của issue khác, trao đổi trong issue trước.

## 2. Đặt tên nhánh và PR

| Mục | Chuẩn | Ví dụ |
| --- | --- | --- |
| Nhánh | `<loại>/#N-<mo-ta-ngan>` | `feat/#42-batch-reconcile` |
| Tiêu đề PR | `[#N] <mô tả thay đổi>` | `[#42] Đối chiếu batch khi Node kết nối lại` |
| Mô tả PR | `Closes #N` khi PR hoàn thành issue, `Refs #N` khi còn việc | `Closes #42` |

`N` là số **GitHub Issue**. Dùng `feat`, `fix`, `docs`, `test`, `refactor` hoặc `chore` theo loại việc. Phần mô tả ngắn của nhánh dùng chữ thường ASCII và dấu gạch nối. Đặt tên nhánh trong dấu nháy khi chạy lệnh.

```powershell
git switch main
git pull --ff-only origin main
git switch -c 'feat/#42-batch-reconcile'
# Sau khi commit thay đổi
git push -u origin 'feat/#42-batch-reconcile'
```

## 3. Mở PR và review

- Mở PR vào `main` từ nhánh issue. Mặc định mỗi PR xử lý một issue. Nếu issue cần nhiều PR, dùng `Refs #N` cho các PR trước và `Closes #N` cho PR hoàn tất. Giữ `[#N]` trong tiêu đề từng PR để workflow nhận diện các PR bàn giao từ lịch sử issue. [Cách GitHub liên kết và đóng issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue)
- Mô tả phạm vi thay đổi, cách kiểm tra và kết quả thực tế. Ghi rõ mục chưa chạy hoặc bị chặn. Có thể mở Draft PR để xin góp ý sớm, rồi chuyển sang Ready for review khi đủ bằng chứng.
- Mời ít nhất một thành viên khác review. Nếu có commit mới sau khi được duyệt, yêu cầu review lại. Xử lý các yêu cầu sửa và xác nhận các kiểm tra bắt buộc đã đạt trước khi merge.
- Tuân thủ [quy tắc bảo toàn tài liệu gốc](spec/governance/README.md). Chạy `python spec/governance/verify_originals.py` và ghi kết quả trong PR.

## 4. Quyền merge vào `main`

- **Chỉ chủ dự án thực hiện merge.** Tác giả PR và người review chịu trách nhiệm chuẩn bị và duyệt thay đổi. PR của chủ dự án cũng cần người khác duyệt.
- **Mọi thay đổi vào `main` đi qua PR**, kể cả sửa gấp hoặc revert. Cấm push trực tiếp, force-push, xóa `main` và bật auto-merge.
- Chủ dự án kiểm tra PR đã sẵn sàng, có ít nhất một lượt duyệt hợp lệ, hết xung đột, đã xử lý các trao đổi và đạt các kiểm tra bắt buộc. Dùng **Squash and merge** và giữ `[#N]` trong tiêu đề commit gộp.
- Để GitHub thực thi quy tắc, cấu hình bảo vệ `main` với PR bắt buộc, ít nhất một approval, hủy approval cũ khi có commit mới, yêu cầu xử lý trao đổi và kiểm tra CI đã có. Chặn force-push, xóa nhánh và giới hạn quyền cập nhật qua PR cho chủ dự án theo khả năng của repo. [Quy tắc bảo vệ nhánh trên GitHub](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)

## 5. Ràng buộc khi triển khai

- Một ứng dụng phục vụ mọi vai trò. UI/API cục bộ bind loopback. Node ghi danh và ghép thiết bị hai chiều trước. Nguồn chọn thiết bị đã ghép, controller gửi offer theo từng định danh đích, và mỗi đích xác nhận trước khi nhận việc. Mã ghép chỉ dùng để thiết lập cặp thiết bị. [Kiến trúc](docs/architecture.md) · [Giao thức điều khiển](docs/control-protocol.md) · [UX](docs/ux.md)
- Ưu tiên makespan đến lúc đích cuối cùng xác minh SHA-256 toàn tệp. Tắt nhân bản dự phòng theo mặc định. Chỉ chuyển tiếp batch đã kiểm hash và lưu bền. Giữ batch hợp lệ qua lần thử lại và khởi động lại. [Kế hoạch](plan/ASTRA_PLAN.md) · [Lưu trữ và phục hồi](docs/storage-and-recovery.md)
- Khóa phiên bản Croc và cấu hình đường truyền cho mỗi ca so sánh. Giữ token, mã Croc và dữ liệu người dùng ngoài log, video và benchmark. Chỉ báo đạt cổng khi có hiện vật chạy thật. Khi thiếu số đo, ghi trạng thái và lý do. [Runbook thử nghiệm](docs/experiments.md)
