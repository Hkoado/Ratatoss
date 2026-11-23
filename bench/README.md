# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Đo bằng Croc v11.6.5 đã ghim, relay IPv4 loopback và ba đầu mút A/B/C trên một máy Windows. Các lượt so sánh giới hạn upload ở 24M theo cờ Croc, cùng khoảng chờ mở phiên 750 ms. Cấu hình sender dùng `--no-local --transport relay --no-multi`. Cấu hình, digest binary và kết quả dọn tiến trình nằm trong từng `evidence.json`. Đường dữ liệu của từng phiên được ghi `unknown` vì không đo socket hay bộ đếm đường truyền. Ca LAN/WAN nhiều máy chưa chạy.

Bộ [runs.csv](artifacts/r02/runs.csv), [transfers.csv](artifacts/r02/transfers.csv) và [readiness.json](artifacts/r02/readiness.json) là bộ hiện vật của R0.2. Các lượt truyền có hash/exit code/cleanup hợp lệ được tách khỏi ba phép đo byte chưa xác minh.

`rx-tx-overlap`, `setup-goodput-by-size` và `selected-batch-size` hiện ở trạng thái `blocked`. Các cột `first_byte_monotonic_ms`, `last_byte_monotonic_ms`, `setup_ms`, `goodput_bps` và overlap được để trống; không dùng tiến độ phần trăm hay kích thước staging như mốc payload đã xác minh.

Hiện chưa chọn batch mặc định. Chưa có kết luận makespan/goodput/overlap áp dụng cho batch 32, 64 hoặc 128 MiB. Xem [runbook Cổng 0](../docs/experiments.md#cổng-0--transport), [quy tắc lưu bằng chứng](../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) và [hồ sơ ngân sách theo cỡ batch](artifacts/r02/batch-profiles.json).

Ca không có bên gửi trả `TRANSPORT_TIMEOUT` sau khoảng 4500 ms. Báo cáo ghi cây tiến trình về 0, staging sạch và không publish dữ liệu. Lượt retry dùng cùng fixture 32 MiB với ID lần thử mới và xác minh đúng SHA-256. Lượt upload giới hạn 4M cũng xác minh đúng SHA-256.
