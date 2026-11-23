# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Đo bằng Croc v11.6.5 đã ghim, relay IPv4 loopback và ba đầu mút A/B/C trên một máy Windows. Các lượt so sánh giới hạn upload ở 24M theo cờ Croc, cùng khoảng chờ mở phiên 750 ms. Cấu hình sender dùng `--no-local --transport relay --no-multi`. Cấu hình, digest binary và kết quả dọn tiến trình nằm trong từng `evidence.json`. Đường dữ liệu của từng phiên được ghi `unknown` vì không đo socket hay bộ đếm đường truyền. Ca LAN/WAN nhiều máy chưa chạy.

Bộ [runs.csv](artifacts/r02/runs.csv) và [transfers.csv](artifacts/r02/transfers.csv) lưu 21 lượt và 30 lần truyền, gồm timeout, retry và slow-path. Số đo được tạo lại sau bản vá timeout và nhất quán giữa CSV, JSON và báo cáo readiness.

| Batch (MiB) | Kịch bản | Đạt/tổng | Mốc byte đầu/cuối | Setup/goodput chuẩn | Makespan trung vị (ms) | Overlap byte payload |
| --- | --- | --- | --- | --- | --- | --- |
| 32 | Tuần tự | 3/3 | Có | 592.6–688.3 Mbps | 1375 | — |
| 32 | Đồng thời | 3/3 | Có | 614.3–636.1 Mbps | 1531 | 312–375 ms |
| 64 | Tuần tự | 3/3 | Có | 296.1–306.8 Mbps | 3015 | — |
| 64 | Đồng thời | 3/3 | Có | 291.3–309.6 Mbps | 3203 | 1531–1953 ms |
| 128 | Tuần tự | 3/3 | Có | 103.7–231.4 Mbps | 5797 | — |
| 128 | Đồng thời | 3/3 | Có | 212.7–248.1 Mbps | 5844 | 4266–4359 ms |

Các trường `first_byte_monotonic_ms`, `last_byte_monotonic_ms`, `setup_ms` và `goodput_bps` lấy từ mốc staging RX: byte đầu là lần size tệp > 0; byte cuối là lúc xác minh và fsync hoàn tất. Makespan tính đến lần xác minh SHA-256 cuối cùng. Overlap đồng thời lấy giao hai khoảng byte staging trên chung đồng hồ monotonic của tiến trình loopback. Cả ba cỡ đều có đủ 3 lượt tuần tự và 3 lượt đồng thời. Xem [runbook Cổng 0](../docs/experiments.md#cổng-0--transport), [quy tắc lưu bằng chứng](../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) và [hồ sơ ngân sách theo cỡ batch](artifacts/r02/batch-profiles.json).

Ca không có bên gửi trả `TRANSPORT_TIMEOUT` sau 4500 ms. Báo cáo ghi cây tiến trình về 0, staging sạch và không publish dữ liệu. Lượt retry dùng cùng fixture 32 MiB với ID lần thử mới và xác minh đúng SHA-256. Lượt upload giới hạn 4M cũng xác minh đúng SHA-256. [Bằng chứng timeout](artifacts/r02/r02-timeout-reproduce-14f71d/evidence.json) · [Bằng chứng retry](artifacts/r02/r02-retry-32mib-f4bb7f/evidence.json) · [Bằng chứng đường chậm](artifacts/r02/r02-slow_path-32mib-c6dcb9/evidence.json).

**Chọn batch mặc định: 64 MiB.** Chính sách sử dụng cỡ đủ mốc 32/64/128 MiB, chọn 64 MiB vì median makespan đồng thời 3203 ms thấp hơn 128 MiB (5844 ms), trong khi giữ nền tảng goodput cao hơn 128 MiB và bảo toàn giới hạn payload thấp hơn 128 MiB. Kết quả này chỉ áp dụng cho profile Windows loopback đã khóa; chưa thay thế benchmark LAN/WAN nhiều máy.
