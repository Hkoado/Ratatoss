# Prompt bàn giao cho phiên làm việc

## Plan · `gpt-6.2-astra`

> Đọc AGENTS.md, brief v1.3, kế hoạch, backlog, và thiết kế hiện có. Chọn một ticket có đủ đầu vào. Nêu mục tiêu, giả thuyết, phụ thuộc, ranh giới tệp, thay đổi API/trạng thái, ca kiểm tra và hiện vật cần để nghiệm thu. Phân biệt yêu cầu brief, quyết định tạm thời và lựa chọn cần số đo. Chỉ ra điểm phải dừng khi thiếu bằng chứng cổng trước. Trả về kế hoạch bằng tiếng Việt.

## Act · `gpt-6.2-sol`

> Thực thi ticket đã chọn theo kế hoạch. Giữ phần thay đổi trong ranh giới tệp và dùng cấu trúc repo hiện có. Chạy các ca xác minh qua điểm vào thực tế của tính năng. Với Croc hoặc demo nhiều máy, ghi phiên bản, cấu hình đã làm sạch bí mật, đường truyền quan sát được, kết quả hash và dấu thời gian. Lưu hiện vật đo được, báo rõ mọi phép thử chưa chạy và điều kiện nghiệm thu còn thiếu. Cập nhật trạng thái ticket theo bằng chứng. Không tự mở rộng sang cổng kế tiếp khi cổng hiện tại chưa đạt.

## Bắt đầu với R0.1

Dán vào phiên Plan dùng `gpt-6.2-astra`:

> Lập kế hoạch ticket R0.1 cho Ratatoss. Đọc AGENTS.md, plan/ASTRA_PLAN.md, plan/BACKLOG.md và docs/experiments.md. Mục tiêu là adapter chạy Croc v11.6.5 bằng binary đã ghim và cấu hình relay xác định, tự gửi/nhận fixture, kiểm SHA-256, trả kết quả timeout, dọn cây tiến trình và cách ly tệp dở. Xác định điểm vào smoke runner, đầu vào thử, ranh giới tệp, lệnh kiểm và hiện vật cần giữ. Ghi việc nào thuộc phép đo 32/64/128 MiB và overlap của R0.2. Soạn bàn giao để Sol thực thi R0.1.

Dán vào phiên Act dùng `gpt-6.2-sol`, kèm đầu ra Plan:

> Thực thi R0.1 theo kế hoạch Astra đính kèm. Kiểm tra adapter và runner sẵn có trước khi chỉnh. Dùng Croc v11.6.5 và relay thử nghiệm đã cấu hình nếu đủ đầu vào. Chạy ca gửi/nhận với fixture SHA-256 và timeout có thể tái hiện. Lưu phiên bản, lệnh đã lược bí mật, mã thoát, xác nhận cleanup và kết quả hash. Báo tiêu chí còn thiếu nếu môi trường chưa đủ để chạy thật. Dừng ở ranh giới R0.1.

## Đầu ra bàn giao

Ghi mã ticket, tệp thay đổi, lệnh hoặc thao tác đã thực hiện, kết quả theo từng tiêu chí, đường dẫn bằng chứng và blocker nếu có. Với các thử nghiệm chưa chạy, giữ mẫu CSV chỉ có hàng tiêu đề.
