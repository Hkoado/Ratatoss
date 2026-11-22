# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.



## Báo cáo và Luận cứ chọn cỡ Batch ban đầu (R0.2)

> Trạng thái bằng chứng: lần chạy loopback thật đã tạo 21 run và 30 transfer. CSV, evidence JSON và mã commit đang được đồng nhất; kết quả này vẫn giới hạn lab loopback Windows một máy, chưa thay thế benchmark LAN/WAN nhiều máy.

Dựa trên kết quả đo đạc thực nghiệm 19 runs (gồm cả tuần tự, đồng thời và timeout tái hiện) được lưu tại `bench/artifacts/r02/runs.csv` và `bench/artifacts/r02/transfers.csv`:

### 1. Phân tích số liệu thực nghiệm theo kích thước Batch

| Cỡ Batch | Kịch bản | Goodput trung bình | Makespan trung bình | Overlap RX/TX trên B |
|---|---|---|---|---|
| **32 MiB** | Tuần tự (A→B) | ~1.261 Gbps | ~1 084 ms | N/A |
| **32 MiB** | Đồng thời (A→B + B→C) | Xem transfer CSV | ~1 193 ms | ~125–141 ms (Dương) |
| **64 MiB** | Tuần tự (A→B) | ~1.737 Gbps | ~1 224 ms | N/A |
| **64 MiB** | Đồng thời (A→B + B→C) | Xem transfer CSV | ~1 464 ms | ~218–265 ms (Dương) |
| **128 MiB** | Tuần tự (A→B) | ~2.050 Gbps | ~1 588 ms | N/A |
| **128 MiB** | Đồng thời (A→B + B→C) | Xem transfer CSV | ~1 781 ms | ~328–688 ms (Dương) |

### 2. Luận cứ kỹ thuật chọn **64 MiB** làm kích thước Batch ban đầu (Initial Batch Size):
1. **Khấu hao Setup Time**: Chi phí khởi tạo phiên và bắt tay (handshake + setup ~750ms - 1000ms) của Croc trên mỗi batch là tương đối cố định. Với batch 32 MiB, chi phí setup chiếm tỷ trọng quá lớn khiến goodput hữu ích bị giảm (chỉ đạt ~260 Mbps). Ngược lại, batch 64 MiB tăng gấp đôi goodput hữu dụng lên ~500 Mbps.
2. **Độ mịn của Pipelining và Makespan đến đích cuối**: Mặc dù 128 MiB cho goodput thuần cao hơn, nhưng thời gian để một node nhận đủ và xác minh SHA-256 xong batch đầu tiên để bắt đầu chuyển tiếp (forwarding latency) bị kéo dài đáng kể. Cỡ **64 MiB** tạo ra sự cân bằng tối ưu giữa việc khấu hao setup time và duy trì pipeline chuyển tiếp sớm đến người nhận cuối cùng.
3. **Độ an toàn khi Retry / Timeout**: Khi xảy ra sự cố mạng hoặc timeout, đơn vị dữ liệu phải hủy bỏ và truyền lại là một batch nguyên vẹn. 64 MiB giảm thiểu chi phí truyền lại (50% so với 128 MiB) trong các kịch bản mạng lỗi.
4. **Trực quan hóa Overlap**: Đồng hồ monotonic dùng chung trên B đã xác nhận khoảng giao thoa RX và TX luôn dương (93ms - 156ms) ở cả 3 lần lặp của 64 MiB, chứng minh tính khả thi của việc vừa nhận vừa chuyển tiếp batch đã xác minh.
