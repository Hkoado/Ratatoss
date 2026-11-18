# Backlog theo cổng

Tên thư mục mã dưới đây chỉ ranh giới trách nhiệm. Dùng module tương đương hiện có và ghi đường dẫn thực tế trong bàn giao.

| Ticket | Đầu vào và phụ thuộc | Ranh giới tệp | Điều kiện hoàn tất |
|---|---|---|---|
| R0.1 Adapter | Croc binary, relay thử nghiệm, fixture SHA-256 | Adapter, cấu hình phiên bản/relay, smoke runner | Adapter kiểm phiên bản, tự gửi/nhận, báo lỗi/timeout, kết thúc cây tiến trình và cách ly tệp dở. |
| R0.2 Đo transport | R0.1, ba đầu mút, 32/64/128 MiB | Runner, bench, docs/experiments.md | Có hash, overlap, setup/goodput theo cỡ, timeout tái hiện và lý do chọn cỡ batch đầu tiên. |
| R1.1 Store | R0.2, schema manifest | Manifest, piece store, kiểm tra/ghép, reconcile | Hỏng hash bị từ chối, commit trước khi publish, restart giữ dữ liệu hợp lệ, hash file cuối đúng. |
| R1.2 Control plane | R0.2, danh tính peer và schema | Controller, SQLite/state, lịch cố định, auth | Một lease hiệu lực mỗi khóa; ACK lặp/muộn, rớt heartbeat và expire có ca kiểm tra. |
| R1.3 Node và UI | R1.1–R1.2, adapter | Agent RX/TX, UI/API local, đóng gói | Cùng bản cài tạo/nhận job, consent trước nhận, đóng/mở tab không mất tiến độ, giới hạn phiên có hiệu lực. |
| R1.4 Demo | R1.3, A/B/C/D và LAN B/C đã đo | Runbook, hiện vật chạy, CSV | Pipeline chồng lặp, C rớt/quay lại, hash đúng ở B/C/D, batch hợp lệ giữ nguyên, B gửi và A nhận job mới. |
| R2.1 PLARS | R1.4, nhóm nghẽn và mẫu goodput | Scheduler, cấu hình/tải và telemetry | Phân công động khi còn slot, không vượt ngân sách chung, D chọn A khi tốt hơn, cooldown ghi được. |
| R2.2 Baselines | R2.1, fixture, hồ sơ mạng | Runner/bench và báo cáo | Năm cấu hình so được, có đối chứng cùng topology/slot, chạy lặp WAN chung, lệch tốc và rớt mạng, lưu báo cáo cả trường hợp thua. |
| R3.1 SafeExit | R2.2, yêu cầu chịu lỗi được chọn | Chính sách bản sao, trạng thái, ca thử | Chứng minh ngưỡng bản sao theo miền lỗi; báo chi phí so với mặc định. |
| R3.2 Controller recovery | R2.2, mô hình persistence | Controller, SQLite, reconcile | Restart duy trì đúng availability, không hoàn tất sai hoặc truyền lại batch còn nguyên. |
| R3.3 Tối ưu | R2.2, giả thuyết có số đo | Scheduler hoặc adapter, runner | Mỗi thay đổi đa nguồn/phát hiện nghẽn/cỡ batch có so sánh riêng với PLARS cơ bản. |
| R3.4 Bảo mật mở rộng | R2.2, khóa tin cậy và yêu cầu quyền đọc | Manifest signature, bảo vệ payload | Từ chối manifest sửa/chữ ký sai và kiểm tra quyền giải mã xuyên hop. |
