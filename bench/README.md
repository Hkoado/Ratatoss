# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Ma trận chạy trên một máy Windows với ba đầu mút A/B/C, Croc v11.6.5 đúng SHA-256 đã ghim, relay IPv4 loopback và sáu fixture SHA-256 cố định. Các phiên ma trận dùng `--no-compress`, cờ upload `24M`, một kết nối dữ liệu mỗi phiên và khoảng chờ mở phiên 750 ms. A→B và B→C dùng fixture độc lập. Phạm vi kết luận là cấu hình loopback này. LAN/WAN nhiều máy chưa chạy. [Lab #40](artifacts/r02-preflight/README.md) · [Runbook Cổng 0](../docs/experiments.md#cổng-0--transport)

Hai điểm quan sát TCP ở B ghi mốc tại biên kết nối relay của tiến trình RX và TX trên cùng đồng hồ `monotonic_ns`. Runner nhận diện khung dữ liệu 32 KiB qua header của Croc trên cổng dữ liệu riêng. Mốc và bộ đếm chỉ tính vùng ciphertext tương ứng payload, loại header khung, nonce, offset, thẻ xác thực, bắt tay và ping. Listener chuyển tiếp TCP có thể ảnh hưởng thời gian và mốc được lấy theo lượt đọc socket. Hiện vật chỉ lưu mốc, tổng byte và số khung. Mỗi phiên chỉ dùng số đo khi tổng byte khớp fixture và đích đã xác minh SHA-256. [Observer](../scripts/croc_r02_tap.py) · [Data path của Croc](https://github.com/schollz/croc/blob/v11.6.5/src/croc/croc.go#L3867-L3947) · [Định dạng khung](https://github.com/schollz/croc/blob/v11.6.5/src/comm/comm.go#L200-L224) · [AES-GCM](https://github.com/schollz/croc/blob/v11.6.5/src/crypt/crypt.go#L47-L79)

Mỗi cỡ có ba lượt tuần tự và ba lượt đồng thời. Cả 18 lượt có đủ số đo và đúng hash. Cả chín lượt đồng thời có overlap dương tại B. Bảng dùng trung vị của các lượt đồng thời, trừ cột khoảng overlap. [Runs](artifacts/r02/runs.csv) · [Transfers](artifacts/r02/transfers.csv) · [Readiness](artifacts/r02/readiness.json) · [Hồ sơ theo cỡ](artifacts/r02/batch-profiles.json)

- `setup_ms` tính từ lúc tiến trình ở điểm quan sát B khởi động đến byte đầu. Với RX, điểm bắt đầu là B_rx, nên số này gồm khoảng chờ bên gửi A_tx. Runner đặt khoảng chờ 750 ms trước khi mở bên gửi. Đây là cấu hình lab, chưa được xác nhận là chi phí mở phiên trong hệ thống thật.
- Hồ sơ tính thêm thời gian từ lúc tiến trình gửi khởi động đến byte đầu ở B cho cả hai tuyến. A→B dùng mốc bắt đầu A_tx và B→C dùng mốc bắt đầu B_tx. Ba đầu mút dùng chung đồng hồ của máy Windows. Chỉ số này đặt hai tuyến trên cùng loại mốc.
- Goodput chịu ảnh hưởng trực tiếp của cờ `24M`. Croc v11.6.5 dùng tốc độ khoảng 24 MiB/s và cấp sẵn credit 24 MiB khi mỗi tiến trình gửi mới khởi động. Với batch ngắn, lượng credit ban đầu chiếm tỷ lệ payload lớn hơn, làm goodput đo được cao hơn. [Limiter của Croc v11.6.5](https://github.com/schollz/croc/blob/v11.6.5/src/croc/croc.go#L459-L488)

| Batch (MiB) | Setup từ lúc mở B RX (ms) | Từ lúc mở sender A→B / B→C đến byte đầu tại B (ms) | Goodput B RX / TX (Mb/s) | Overlap nhỏ nhất–lớn nhất (ms) | Makespan đồng thời (ms) |
| --- | --- | --- | --- | --- | --- |
| 32 | 1253.0 | 322.6 / 202.1 | 753.4 / 817.8 | 139.1–252.1 | 2104 |
| 64 | 1491.0 | 330.8 / 148.2 | 328.0 / 326.2 | 1527.1–1529.0 | 4106 |
| 128 | 2502.6 | 950.9 / 385.5 | 231.4 / 247.3 | 2269.2–4336.2 | 10049 |

**64 MiB là lựa chọn ban đầu cho profile Windows loopback này.** So sánh cùng 128 MiB mỗi tuyến bằng cách nhân makespan trung vị đồng thời tới SHA-256 của đích cuối với số cặp batch cần chạy. Mô hình giả định mỗi batch mở phiên mới và các cặp batch chạy nối tiếp. Khoảng min–max quy đổi của 32 và 64 MiB giao nhau. Hàng đầu dùng cấu hình đã đo. Ba hàng sau là phép tính độ nhạy, áp dụng một khoản thời gian cố định vào makespan mỗi lượt trước khi nhân theo số batch.

| Ước tính makespan cho 128 MiB mỗi tuyến (ms) | 32 MiB | 64 MiB | 128 MiB | Thấp nhất |
| --- | --- | --- | --- | --- |
| Cấu hình đã đo | 8416 | 8212 | 10049 | 64 MiB |
| Bỏ credit đầu phiên (+1000 ms mỗi lượt) | 12416 | 10212 | 11049 | 64 MiB |
| Bỏ khoảng chờ mở sender (−750 ms mỗi lượt) | 5416 | 6712 | 9299 | 32 MiB |
| Bỏ cả hai (+250 ms mỗi lượt) | 9416 | 8712 | 10299 | 64 MiB |

Thứ hạng có thể đổi khi thay đổi cách khởi động phiên. Phép tính độ nhạy chỉ minh họa ảnh hưởng của hai tham số này. Ma trận bỏ cờ throttle và LAN/WAN nhiều máy chưa chạy. Phân bố mới được tính từ các lượt ở `ac30ef2`. CSV và hiện vật từng lượt giữ nguyên.

Các ngân sách preflight trong hồ sơ là cấu hình đã khóa cho ca chạy. Quãng dài nhất từ khi tiến trình RX dừng đến khi kiểm hash và flush xong ghi nhận theo cỡ 32 MiB là 497.8 ms, 64 MiB là 843.1 ms, 128 MiB là 2118.1 ms. Khoản verify/commit cấu hình 200 ms thấp hơn các cực đại quan sát trong lab. Hồ sơ giữ riêng cấu hình đã chạy và số liệu thực tế để hiệu chỉnh ở profile tiếp theo.

Ca thiếu bên gửi trả `TRANSPORT_TIMEOUT` sau 5011 ms. Cây tiến trình về 0, staging sạch và chưa công bố tệp. Retry dùng cùng fixture A 32 MiB với ID lần thử mới và khớp SHA-256. Ca đường chậm dùng cờ upload `4M` và cũng khớp SHA-256. Các ca lỗi chạy trên loopback trực tiếp tới relay và giữ trống số đo byte.

- [Bằng chứng timeout](artifacts/r02/r02-timeout-reproduce-b72359/evidence.json)
- [Bằng chứng retry](artifacts/r02/r02-retry-32mib-9cf773/evidence.json)
- [Bằng chứng đường chậm](artifacts/r02/r02-slow_path-32mib-1425f1/evidence.json)
