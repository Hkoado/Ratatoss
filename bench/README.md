# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Đo bằng Croc v11.6.5 đã ghim, relay IPv4 loopback và ba đầu mút A/B/C trên một máy Windows. Các lượt so sánh giới hạn upload ở 24M theo cờ Croc, cùng khoảng chờ mở phiên 750 ms. Cấu hình sender dùng `--no-local --transport relay --no-multi`. Cấu hình, digest binary và kết quả dọn tiến trình nằm trong từng `evidence.json`. Đường dữ liệu của từng phiên được ghi `unknown` vì không đo socket hay bộ đếm đường truyền. Ca LAN/WAN nhiều máy chưa chạy.

Bộ [runs.csv](artifacts/r02/runs.csv) và [transfers.csv](artifacts/r02/transfers.csv) lưu 22 lượt, 30 lần thử, gồm cả timeout và lượt lỗi nếu có. Mã nguồn đo tại `b28ddfefce42`. Số đo dưới đây tính từ các lượt đạt.

| Batch (MiB) | Kịch bản | Đạt/tổng | Setup quan sát (ms) | Goodput ước tính (Mbit/s) | Makespan trung vị (ms) | Overlap payload (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 32 | Tuần tự | 3/3 | 1230–1240 | 209.7–211.6 | 2148 | — |
| 32 | Đồng thời | 3/3 | 1183–1389 | 209.6–326.6 | 2665 | 30–72 |
| 64 | Tuần tự | 3/3 | 1384–1397 | 206.0–206.3 | 3987 | — |
| 64 | Đồng thời | 3/3 | 1346–2162 | 204.4–241.0 | 4808 | 1014–1157 |
| 128 | Tuần tự | 3/3 | 1797–2364 | 206.8–227.0 | 8287 | — |
| 128 | Đồng thời | 3/4 | 2423–4640 | 205.9–254.3 | 9840 | 2264–3301 |

Mốc byte trong CSV lấy từ lần Croc báo tiến độ payload dương đầu tiên và lần báo 100% ở đầu nhận. Setup là thời gian đến cập nhật dương đầu tiên. Goodput ước tính từ phần trăm payload còn lại và thời lượng đến 100%. Các mốc phụ thuộc nhịp cập nhật của Croc. Phép tính overlap dùng phần giao của hai khoảng tiến độ RX trên cùng đồng hồ monotonic Windows. Makespan tính đến lần xác minh SHA-256 cuối cùng. Xem [runbook Cổng 0](../docs/experiments.md#cổng-0--transport) và [quy tắc lưu bằng chứng](../docs/experiments.md#thu-thập-và-lưu-bằng-chứng).

Ca không có bên gửi trả `TRANSPORT_TIMEOUT` sau 4509 ms. Báo cáo ghi cây tiến trình về 0, staging sạch và không publish dữ liệu. Lượt retry dùng cùng fixture 32 MiB với ID lần thử mới và xác minh đúng SHA-256. Lượt upload giới hạn 4M cũng xác minh đúng SHA-256. [Bằng chứng timeout](artifacts/r02/r02-timeout-reproduce-83133c/evidence.json) · [Bằng chứng retry](artifacts/r02/r02-retry-32mib-586ecc/evidence.json) · [Bằng chứng đường chậm](artifacts/r02/r02-slow_path-32mib-997f6d/evidence.json).

**Đề xuất bắt đầu với 64 MiB.** Trong profile này, 64 MiB phân bổ chi phí mở phiên cho lượng payload gấp đôi 32 MiB và có makespan thấp hơn 128 MiB. Cỡ này cũng giảm lượng payload tối đa của một batch cần gửi lại so với 128 MiB. Cần xác nhận lựa chọn khi chạy trên profile mạng dùng cho demo.
