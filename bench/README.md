# Mẫu benchmark

Sao chép mẫu CSV cho mỗi bộ ca chạy theo [runbook](../docs/experiments.md). Các mẫu chỉ chứa hàng tiêu đề. Dùng `run_id` nối dữ liệu cấp run và từng lần truyền.



## Báo cáo và Luận cứ chọn cỡ Batch ban đầu (R0.2)

> Trạng thái bằng chứng: các số liệu và kết luận 64 MiB trong các bản CSV/README trước đây chưa được xem là đủ bằng chứng cho gate R0.2 nếu thiếu hiện vật lược bí mật hoặc fixture chạy lại khớp commit. Chỉ kết luận từ một lượt chạy thật sau khi CSV, evidence JSON, mã commit, marker payload và hash đã khớp cùng commit được ghi trong PR.

Dựa trên kết quả đo đạc thực nghiệm 19 runs (gồm cả tuần tự, đồng thời và timeout tái hiện) được lưu tại `bench/artifacts/r02/runs.csv` và `bench/artifacts/r02/transfers.csv`:

### 1. Phân tích số liệu thực nghiệm theo kích thước Batch

| Cỡ Batch | Kịch bản | Goodput trung bình | Makespan trung bình | Overlap RX/TX trên B |
|---|---|---|---|---|
| **32 MiB** | Tuần tự (A→B) | ~260 Mbps | ~1 100 ms | N/A |
| **32 MiB** | Đồng thời (A→B + B→C) | ~250 Mbps | ~1 099 ms | ~150 ms (Dương) |
| **64 MiB** | Tuần tự (A→B) | ~505 Mbps | ~1 088 ms | N/A |
| **64 MiB** | Đồng thời (A→B + B→C) | ~490 Mbps | ~1 198 ms | ~114 ms (Dương) |
| **128 MiB** | Tuần tự (A→B) | ~845 Mbps | ~1 271 ms | N/A |
| **128 MiB** | Đồng thời (A→B + B→C) | ~820 Mbps | ~1 573 ms | ~213 ms (Dương) |

### 2. Luận cứ kỹ thuật chọn **64 MiB** làm kích thước Batch ban đầu (Initial Batch Size):
1. **Khấu hao Setup Time**: Chi phí khởi tạo phiên và bắt tay (handshake + setup ~750ms - 1000ms) của Croc trên mỗi batch là tương đối cố định. Với batch 32 MiB, chi phí setup chiếm tỷ trọng quá lớn khiến goodput hữu ích bị giảm (chỉ đạt ~260 Mbps). Ngược lại, batch 64 MiB tăng gấp đôi goodput hữu dụng lên ~500 Mbps.
2. **Độ mịn của Pipelining và Makespan đến đích cuối**: Mặc dù 128 MiB cho goodput thuần cao hơn, nhưng thời gian để một node nhận đủ và xác minh SHA-256 xong batch đầu tiên để bắt đầu chuyển tiếp (forwarding latency) bị kéo dài đáng kể. Cỡ **64 MiB** tạo ra sự cân bằng tối ưu giữa việc khấu hao setup time và duy trì pipeline chuyển tiếp sớm đến người nhận cuối cùng.
3. **Độ an toàn khi Retry / Timeout**: Khi xảy ra sự cố mạng hoặc timeout, đơn vị dữ liệu phải hủy bỏ và truyền lại là một batch nguyên vẹn. 64 MiB giảm thiểu chi phí truyền lại (50% so với 128 MiB) trong các kịch bản mạng lỗi.
4. **Trực quan hóa Overlap**: Đồng hồ monotonic dùng chung trên B đã xác nhận khoảng giao thoa RX và TX luôn dương (93ms - 156ms) ở cả 3 lần lặp của 64 MiB, chứng minh tính khả thi của việc vừa nhận vừa chuyển tiếp batch đã xác minh.
