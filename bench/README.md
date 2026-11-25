# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.

## R0.2 · Kết quả Windows loopback

Ma trận chạy trên một máy Windows với ba đầu mút A/B/C, Croc v11.6.5 đúng SHA-256 đã ghim, relay IPv4 loopback và sáu fixture SHA-256 cố định. Các phiên ma trận dùng `--no-compress`, cờ upload `24M`, một kết nối dữ liệu mỗi phiên và khoảng chờ mở phiên 750 ms. A→B và B→C dùng fixture độc lập. Phạm vi kết luận là cấu hình loopback này. LAN/WAN nhiều máy chưa chạy. [Lab #40](artifacts/r02-preflight/README.md) · [Runbook Cổng 0](../docs/experiments.md#cổng-0--transport)

Hai điểm quan sát TCP ở B ghi mốc tại biên kết nối relay của tiến trình RX và TX trên cùng đồng hồ `monotonic_ns`. Runner nhận diện khung dữ liệu 32 KiB qua header của Croc trên cổng dữ liệu riêng. Mốc và bộ đếm chỉ tính vùng ciphertext tương ứng payload, loại header khung, nonce, offset, thẻ xác thực, bắt tay và ping. Listener chuyển tiếp TCP có thể ảnh hưởng thời gian và mốc được lấy theo lượt đọc socket. Hiện vật chỉ lưu mốc, tổng byte và số khung. Mỗi phiên chỉ dùng số đo khi tổng byte khớp fixture và đích đã xác minh SHA-256. [Observer](../scripts/croc_r02_tap.py) · [Data path của Croc](https://github.com/schollz/croc/blob/v11.6.5/src/croc/croc.go#L3867-L3947) · [Định dạng khung](https://github.com/schollz/croc/blob/v11.6.5/src/comm/comm.go#L200-L224) · [AES-GCM](https://github.com/schollz/croc/blob/v11.6.5/src/crypt/crypt.go#L47-L79)

Mỗi cỡ có ba lượt tuần tự và ba lượt đồng thời. Cả 18 lượt có đủ số đo và đúng hash. Cả chín lượt đồng thời có overlap dương tại B. Bảng dùng trung vị của các lượt đồng thời, trừ cột khoảng overlap. Số liệu từng lượt, phân bố theo chế độ và các ngân sách đã khóa nằm trong hiện vật. [Runs](artifacts/r02/runs.csv) · [Transfers](artifacts/r02/transfers.csv) · [Readiness](artifacts/r02/readiness.json) · [Hồ sơ theo cỡ](artifacts/r02/batch-profiles.json)

| Batch (MiB) | Setup B RX / TX (ms) | Goodput B RX / TX (Mb/s) | Overlap nhỏ nhất–lớn nhất (ms) | Makespan đồng thời (ms) | Ước tính cho 128 MiB/tuyến (ms) |
| --- | --- | --- | --- | --- | --- |
| 32 | 1253.0 / 202.1 | 753.4 / 817.8 | 139.1–252.1 | 2104 | 8416 |
| 64 | 1491.0 / 148.2 | 328.0 / 326.2 | 1527.1–1529.0 | 4106 | 8212 |
| 128 | 2502.6 / 385.5 | 231.4 / 247.3 | 2269.2–4336.2 | 10049 | 10049 |

**Cỡ batch ban đầu cho profile này là 64 MiB.** So sánh cùng 128 MiB mỗi tuyến bằng cách nhân makespan trung vị đồng thời với số batch cần chạy. Makespan của từng lượt kết thúc khi đích cuối xác minh SHA-256. Đây là ước tính từ các lượt một batch, với giả định mỗi batch mở phiên riêng và các cặp batch chạy nối tiếp. Cỡ 64 MiB có ước tính thấp nhất (8212 ms), hơn 32 MiB khoảng 2,4%. Hai khoảng ước tính tính từ min–max của các lượt có giao nhau, nên lựa chọn ban đầu cần kiểm chứng ở profile tiếp theo. Bảng giữ cả setup và goodput để thấy chi phí mở thêm phiên khi giảm cỡ batch. Chọn lại cỡ khi đổi cấu hình đường truyền hoặc đo cả pipeline.

Các ngân sách preflight trong hồ sơ là cấu hình đã khóa cho ca chạy. Quãng dài nhất từ khi tiến trình RX dừng đến khi kiểm hash và flush xong ghi nhận theo cỡ 32 MiB là 497.8 ms, 64 MiB là 843.1 ms, 128 MiB là 2118.1 ms. Khoản verify/commit cấu hình 200 ms thấp hơn các cực đại quan sát trong lab. Hồ sơ giữ riêng cấu hình đã chạy và số liệu thực tế để hiệu chỉnh ở profile tiếp theo.

Ca thiếu bên gửi trả `TRANSPORT_TIMEOUT` sau 5011 ms. Cây tiến trình về 0, staging sạch và chưa công bố tệp. Retry dùng cùng fixture A 32 MiB với ID lần thử mới và khớp SHA-256. Ca đường chậm dùng cờ upload `4M` và cũng khớp SHA-256. Các ca lỗi chạy trên loopback trực tiếp tới relay và giữ trống số đo byte.

- [Bằng chứng timeout](artifacts/r02/r02-timeout-reproduce-b72359/evidence.json)
- [Bằng chứng retry](artifacts/r02/r02-retry-32mib-9cf773/evidence.json)
- [Bằng chứng đường chậm](artifacts/r02/r02-slow_path-32mib-1425f1/evidence.json)
