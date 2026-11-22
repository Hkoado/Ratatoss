# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Đo bằng Croc v11.6.5 đã ghim, relay IPv4 loopback và ba đầu mút A/B/C trên một máy Windows. Các lượt so sánh giới hạn upload ở 24M theo cờ Croc, cùng khoảng chờ mở phiên 750 ms. Cấu hình sender dùng `--no-local --transport relay --no-multi`. Cấu hình, digest binary và kết quả dọn tiến trình nằm trong từng `evidence.json`. Đường dữ liệu của từng phiên được ghi `unknown` vì không đo socket hay bộ đếm đường truyền. Ca LAN/WAN nhiều máy chưa chạy.

Bộ [runs.csv](artifacts/r02/runs.csv) và [transfers.csv](artifacts/r02/transfers.csv) lưu 22 lượt, 30 lần thử, gồm cả timeout và lượt lỗi nếu có. Mã nguồn đo tại `b28ddfefce42`. Số đo dưới đây tính từ các lượt đạt.

| Batch (MiB) | Kịch bản | Đạt/tổng | Mốc byte đầu/cuối | Setup/goodput chuẩn | Makespan trung vị (ms) | Overlap byte payload |
| --- | --- | --- | --- | --- | --- | --- |
| 32 | Tuần tự | 3/3 | Không có | Để trống | 2148 | — |
| 32 | Đồng thời | 3/3 | Không có | Để trống | 2665 | Chưa xác minh |
| 64 | Tuần tự | 3/3 | Không có | Để trống | 3987 | — |
| 64 | Đồng thời | 3/3 | Không có | Để trống | 4808 | Chưa xác minh |
| 128 | Tuần tự | 3/3 | Không có | Để trống | 8287 | — |
| 128 | Đồng thời | 3/4 | Không có | Để trống | 9840 | Chưa xác minh |

Các trường `first_byte_monotonic_ms`, `last_byte_monotonic_ms`, `setup_ms` và `goodput_bps` để trống trong CSV chuẩn vì lần báo tiến độ Croc không phải mốc byte tin cậy. Các cập nhật tiến độ và phần trăm tương ứng chỉ được giữ trong `evidence.json` dưới dạng ước tính. Chúng không được dùng để xác nhận setup, goodput, overlap RX/TX hay chọn batch mặc định. Makespan tính đến lần xác minh SHA-256 cuối cùng. Xem [runbook Cổng 0](../docs/experiments.md#cổng-0--transport), [quy tắc lưu bằng chứng](../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) và [hồ sơ ngân sách theo cỡ batch](artifacts/r02/batch-profiles.json).

Ca không có bên gửi trả `TRANSPORT_TIMEOUT` sau 4509 ms. Báo cáo ghi cây tiến trình về 0, staging sạch và không publish dữ liệu. Lượt retry dùng cùng fixture 32 MiB với ID lần thử mới và xác minh đúng SHA-256. Lượt upload giới hạn 4M cũng xác minh đúng SHA-256. [Bằng chứng timeout](artifacts/r02/r02-timeout-reproduce-83133c/evidence.json) · [Bằng chứng retry](artifacts/r02/r02-retry-32mib-586ecc/evidence.json) · [Bằng chứng đường chậm](artifacts/r02/r02-slow_path-32mib-997f6d/evidence.json).

**Chưa chọn batch mặc định.** Bộ số liệu hiện tại không gồm mốc byte đầu/cuối đáng tin cậy và không thể nghiệm thu setup/goodput hoặc overlap theo quy tắc R0.2. Không đưa ra đề xuất 32, 64 hoặc 128 MiB làm lựa chọn mặc định cho đến khi có mốc payload byte-level và kết quả overlap đã xác minh.
