# Tự gỡ `blocked` cho issue

Workflow **Issue readiness** chuyển issue đang mở từ `blocked` sang `ready` khi có đúng một assignee và tất cả phép kiểm đầu vào đều đạt. Workflow đọc dữ liệu GitHub và hiện vật từ `main`. [Quy tắc nhóm §1, §3–4](../../CONTRIBUTING.md) · [Backlog](../../plan/BACKLOG.md) · [Thứ tự PLARS và demo](../governance/adr/0002-plars-integration-order.md)

## Các phép kiểm

1. Thêm các issue tiền nhiệm trong **Relationships → Blocked by**. Workflow kiểm các quan hệ cùng repo, gồm những quan hệ đã định trong [cấu hình](../../.github/issue-readiness.json) và quan hệ bổ sung trên GitHub. Mọi tiền nhiệm phải đóng với lý do **Completed**. [Quan hệ phụ thuộc của GitHub](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-issue-dependencies)
2. Workflow tìm PR bàn giao của mỗi tiền nhiệm từ lịch sử GitHub theo tiêu đề `[#N]` hoặc liên kết `Closes #N`. Mọi PR bàn giao đang mở hoặc đã merge phải có squash commit trong lịch sử `main`, do chủ repo hoặc `@NguyenHuy1804` merge, có một approval hợp lệ trên commit cuối và đạt các check bắt buộc trước merge. Với PR do `@NguyenHuy1804` mở, workflow chấp nhận approval trên commit cuối từ một thành viên khác của repo. Với PR của các thành viên còn lại, workflow chấp nhận approval từ chủ repo hoặc `@NguyenHuy1804` khi người duyệt khác tác giả. Khi REST thiếu SHA của commit merge, workflow tra `mergeCommit` qua GraphQL rồi kiểm lịch sử như thường lệ. Với #4, workflow kiểm quyết định đã ban hành qua ADR 0002 trên `main`. [Quyết định #4](../governance/adr/0002-plars-integration-order.md) · [Quy tắc review](../../CONTRIBUTING.md#kiểm-tra-các-cập-nhật-lên-main)
3. Workflow đối chiếu các tệp đầu vào, báo cáo nghiệm thu tiền nhiệm và hiện vật thử riêng được chỉ định trong cấu hình. Issue ngoài danh sách cần có phép kiểm tương ứng trong cấu hình trước khi được xét tự mở.

## Hiện vật dùng cho phép kiểm

Đầu vào #6 nằm trong `bench/artifacts/r02-preflight/`. `endpoints.json` ánh xạ `A`, `B`, `C` tới ba định danh SHA-256 riêng của các đầu mút lab đã lược thông tin nhận dạng. `profile.json` ghi `croc_version`, `croc_sha256`, `relay_config` và `network_profile`. Hai trường cấu hình trỏ tới tệp tương đối đã khóa trong cùng thư mục. Dùng binary và bộ fixture đã kiểm trong hồ sơ lab. Các số đo overlap, setup và goodput được thu khi thực hiện #6 và đi vào báo cáo nghiệm thu dùng để mở #7 và #8. [Runbook cổng 0](../../docs/experiments.md#cổng-0--transport) · [Fixture đã kiểm](croc-lab.md#fixture-tổng-hợp-tái-tạo-được)

Với các mục `reports` khác, chương trình kiểm thử hoặc ca thu thập hiện vật ghi `readiness.json` từ kết quả thật. Đối tượng `checks` ánh xạ từng tên phép kiểm trong cấu hình tới `status` và `evidence`. Kết quả đạt dùng `status` là `pass`. `evidence` ánh xạ tên tệp tương đối trong gói báo cáo tới SHA-256 của dữ liệu hoặc log thô đã lược bí mật. Workflow kiểm đủ từng kết quả và đối chiếu hash của tệp. Phép kiểm nghiệp vụ nằm ở chương trình tạo kết quả tương ứng. [Quy tắc lưu bằng chứng](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)

## Xem kết quả

Khi issue đổi trạng thái hoặc hiện vật mới vào `main`, workflow chạy lại. Lịch 20 phút giúp đối chiếu thay đổi quan hệ và thử lại khi API gặp lỗi tạm thời. Trong **Actions → Issue readiness**, xem số issue và điều kiện còn thiếu trong phần tóm tắt. Khi chạy thủ công, giữ `dry_run` để xem các issue đủ điều kiện hoặc bỏ chọn để áp dụng nhãn.

Workflow thêm `ready` trước rồi gỡ `blocked` để lượt chạy sau có thể tiếp tục nếu API ngắt giữa hai thao tác. Issue còn `blocked` vẫn chờ. Cơ chế tự động chỉ chuyển các issue đang mang `blocked` theo chiều sang `ready`. GitHub ghi thao tác cập nhật nhãn trong lịch sử issue.
