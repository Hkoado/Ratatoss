# Ratatoss

Đọc [brief v1.3](docs/source/Ratatoss_Project_Brief_v1.3.md), [kế hoạch theo cổng](plan/ASTRA_PLAN.md) và [runbook](docs/experiments.md) trước khi triển khai. Brief quy định yêu cầu sản phẩm. Luồng mời ở mục 6.1 được cập nhật bởi [giao thức điều khiển](docs/control-protocol.md) và [thiết kế UX](docs/ux.md). Node ghi danh và ghép thiết bị hai chiều trước, nguồn chọn đích theo tên thiết bị đã ghép, controller phát offer riêng theo định danh và từng đích xác nhận nhận file. Mã ghép chỉ dùng để thiết lập cặp thiết bị. Các giá trị đề xuất trong kế hoạch cần được xác nhận bằng đo hoặc cấu hình đã khóa cho ca thử.

- Làm từng ticket trong [backlog](plan/BACKLOG.md). Giữ ranh giới tệp, xác nhận điều kiện đầu vào và ghi bằng chứng nghiệm thu. Dùng `gpt-6.2-astra` cho Plan và `gpt-6.2-sol` cho Act theo [prompt Plan/Act](plan/PROMPTS.md) khi chuyển từ lập kế hoạch sang thực thi.
- Ưu tiên makespan tính tới lúc người nhận cuối cùng xác minh SHA-256 toàn file. Mặc định tắt nhân bản dự phòng. Chỉ forward batch đã lưu bền và kiểm tra hash. Giữ batch đã xác minh qua lần thử lại và khởi động lại.
- Một ứng dụng cho mọi vai trò. UI/API cục bộ bind loopback. Mỗi người nhận xác nhận trước khi agent nhận job. Giữ token, mã Croc và dữ liệu người dùng khỏi log, video và benchmark.
- Khóa phiên bản Croc và cấu hình đường truyền trong mọi ca so sánh. Không điền số giả vào CSV. Khi thiếu bằng chứng, ghi trạng thái chưa chạy, bị chặn hoặc không xác định tương ứng.
- Chạy kiểm tra phù hợp với ticket qua điểm vào người dùng hoặc luồng tích hợp. Chỉ báo đạt cổng khi có đủ hiện vật chạy thật.

## Đặc tả và bảo toàn tài liệu gốc

- Với công việc giao diện, đọc [hướng dẫn tích hợp UI](spec/ui-integration.md) trước khi dùng UI Kit v1.2. Lấy hình thức và tương tác từ UI Kit, lấy quyền và trạng thái từ hợp đồng của dự án.

- Đọc [chỉ mục đặc tả](spec/README.md) và [quy tắc quản trị](spec/governance/README.md) trước khi viết hoặc thực thi đặc tả.
- Giữ nguyên ý tưởng, cấu trúc, tên đường dẫn và từng byte của nội dung gốc trong `docs/` và `plan/`. Viết đặc tả mới trong `spec/`. Xử lý xung đột qua ADR đề xuất riêng và chờ chủ dự án phê duyệt rõ ràng trước khi thay đổi nguồn gốc hoặc đường chuẩn.
- Dẫn lại tệp và mục nguồn cho yêu cầu. Đánh dấu nội dung suy ra là đề xuất, ghi nhận điều chưa biết và cấm bịa số đo, trích dẫn, SHA-256, kết quả chạy hoặc trạng thái nghiệm thu.
- Chạy `python spec/governance/verify_originals.py` trước khi bàn giao. Cấm sửa trình kiểm tra, manifest hoặc cách gọi để che sai lệch. Khi duyệt thay đổi, dùng cặp trình kiểm tra và manifest từ mốc tin cậy.
