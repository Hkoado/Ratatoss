# Kế hoạch triển khai Ratatoss theo cổng

Các cổng 0–3 và điều kiện sản phẩm bám mục 8 của brief v1.3. Chính sách lịch và tham số dưới đây là đề xuất triển khai để thử trước, có thể đổi khi có dữ liệu. Trạng thái ban đầu của mọi cổng là **chưa nghiệm thu**. Kế hoạch chưa chứng minh hiệu năng.

| Cổng | Phạm vi | Bằng chứng để chuyển cổng |
|---|---|---|
| 0 | POC pinned Croc, 32/64/128 MiB, A→B đồng thời B→C | Phiên bản/relay, kết quả hash, khoảng truyền chồng lặp, phân bố setup/goodput và timeout tái hiện kèm xác nhận dọn tiến trình/tệp tạm. |
| 1 | MVP một ứng dụng, xác nhận nhận job, lịch cố định có pipeline và phục hồi | Demo A/B/C/D, A→B và B→C khác batch chồng lặp, C mất mạng/quay lại, mọi đích hash đúng, giữ batch hợp lệ, đóng/mở tab, B tạo job mới để A nhận. |
| 2 | PLARS cơ bản và đối chứng | Chạy lặp trên WAN chung, peer lệch tốc và peer rớt mạng. Báo makespan, byte A/WAN, setup, retry và điều kiện lịch động thua. |
| 3 | Mở rộng theo yêu cầu và kết quả cổng 2 | Mỗi tính năng có giả thuyết, ca thử và bằng chứng riêng. |

## Lịch cố định ban đầu

Với topology A nguồn, B/C cùng LAN đã đo, D remote, gán batch theo chỉ số: chẵn A→B rồi B→C, lẻ A→C rồi C→B. Đường A→D là mặc định của cấu hình demo. Cấu hình demo riêng có thể đặt B/C→D để quan sát overlap nếu tuyến đo thực tế phù hợp. Chọn batch theo thứ tự tăng dần trong tuyến, xử lý sự kiện xác minh để đánh thức bước forward. Nếu nguồn ưu tiên mất heartbeat, phiên lỗi hoặc lease hết hạn, chọn nguồn khả dụng đã xác minh trong danh sách fallback cấu hình, có A. Với đích offline, chờ sau khi kết nối lại và đối chiếu disk. Giữ slot RX/TX riêng và giới hạn tổng phiên, disk/CPU và đường chung theo cấu hình. Điều kiện phát việc là đích đã consent và còn thiếu, nguồn online có batch đã xác minh và không có lease hiệu lực cho khóa (job, đích, batch).

Một lần thử có ID riêng. Đích kiểm tra lại sự có mặt của batch trước khi bắt đầu để tránh truyền lại. ACK lặp không gây thêm tác động. ACK muộn hợp lệ có thể cập nhật availability nhưng chỉ ID tương ứng được ACK chuyển trạng thái. Thu hồi lần thử khi mất heartbeat hoặc lease hết hạn, dừng phiên theo adapter, xác định lại batch thiếu rồi cấp lease mới. Reconcile trên disk trước khi báo availability sau restart. Nếu controller gián đoạn, giữ batch hợp lệ và báo gián đoạn.

## PLARS cơ bản

1. Chạy vòng lặp khi xác minh, thay đổi heartbeat/tải hoặc theo tick. Lấy ứng viên từ batch thiếu tại đích đã consent, có nguồn giữ bản xác minh, đường hợp lệ, slot và ngân sách còn dư. Xét nút nghẽn theo cấu hình: uplink A, WAN chi nhánh, AP và relay.
2. Theo dõi EWMA goodput và setup theo cặp có hướng và loại đường. Khởi tạo theo probe hoặc tốc độ bảo thủ cấu hình. Giảm tốc độ dự kiến theo phần ngân sách còn lại của từng tài nguyên trên tuyến, giữ tổng dự trữ trong giới hạn. Đặt chi phí giao batch bằng thời gian đợi slot + setup + byte/goodput khả dụng + thời gian xác minh ước tính. Tài nguyên chưa rảnh tạo hàng chờ, không giả định throughput vô hạn.
3. Ước lượng thời điểm mỗi đích hoàn tất từ việc đang chạy, số batch thiếu và chi phí tốt nhất khả thi theo một mô phỏng hàng chờ tham lam có dự trữ. Xét đích có ETA cao nhất trước, chọn batch và nguồn có thời điểm giao sớm nhất. Khi ETA trong khoảng dung sai cấu hình, lần lượt ưu tiên ít byte WAN, ít byte A, rồi ID ổn định. Sau mỗi giao việc, cập nhật dự trữ trước khi xét slot kế tiếp. Ghi lý do chọn và snapshot đầu vào.
4. Giữ phiên đang chạy tới khi hoàn tất, có lỗi hoặc hết lease do mất tiến độ. Giữ kế hoạch cho việc chưa bắt đầu trong cooldown, trừ khi đường mất hoặc ETA cải thiện qua cả ngưỡng tuyệt đối và tương đối. Giá trị khởi điểm thử nghiệm: EWMA α=0,25, cooldown 10 giây, cải thiện tối thiểu 2 giây và 10%; hiệu chỉnh bằng thiết kế đo độc lập với bộ lần chạy báo cáo. Tắt nhân bản dự phòng và SafeExit.
5. Dùng đối chứng tĩnh cùng topology/slot để xác định hiệu quả lịch động. Tự chọn Direct/Gateway/Swarm sau khi đủ số đo; so sánh các chính sách dưới cùng ngân sách và áp dụng hysteresis khi chuyển.

## Mở rộng có điều kiện

SafeExit thường cần một bản đã ACK ngoài A cho mỗi piece. SafeExit chịu mất một peer cần hai bản trên hai peer độc lập ngoài A; chịu lỗi theo miền cần miền lỗi khác nhau. Đo chi phí mỗi chế độ với chế độ mặc định. Chỉ phát triển sau khi có mục tiêu và ca thử. Khi thử khôi phục controller, xác nhận reconcile qua restart và tiến trình sử dụng batch hợp lệ. Với bảo mật nâng cao, xác minh chữ ký manifest bằng khóa đã tin cậy và dùng giải pháp mã hóa payload chuẩn trước khi chia piece. Đánh giá đa nguồn, phát hiện nghẽn và điều chỉnh batch từng thay đổi so với PLARS cơ bản.

