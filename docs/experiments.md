# Runbook thử nghiệm Ratatoss

Trạng thái ban đầu là **chưa chạy**. Candidate transport đã ghim cho cổng 0 là [Croc v11.6.5](https://github.com/schollz/croc/releases/tag/v11.6.5). Trước khi chạy, ghi phiên bản báo bởi executable, SHA-256 binary, OS, commit, relay và cấu hình mạng. Ghi đường dữ liệu `direct`, `relay` hoặc `unknown` theo bằng chứng. Đo đường LAN B↔C trước; địa chỉ IP riêng hoặc cùng SSID không đủ để xác nhận đường trực tiếp.

## Cổng 0 · Transport

1. Tạo fixture riêng cho 32, 64 và 128 MiB, lưu byte và SHA-256. Dùng cùng binary và cấu hình relay trên A/B/C. Chạy một phiên A→B cho từng cỡ và ghi thời gian từ mở phiên đến byte đầu, byte tốt chia theo thời gian truyền hữu ích, hash và mã thoát.
2. Chuẩn bị trên B fixture độc lập cho B→C. Chạy A→B và B→C đồng thời với mã phiên riêng. Đồng hồ B dùng chung cho hai khoảng RX/TX. Bằng chứng cần khoảng hoạt động thực giao nhau với độ dài dương và hash đúng ở cả đích. Chạy tối thiểu ba lần cho mỗi cỡ ở chế độ tuần tự và đồng thời. Ghi cỡ được chọn và đánh đổi setup/goodput.
3. Thử timeout có thể tái hiện bằng cách dùng một phiên nhận có đối tác chưa khởi chạy. Nếu có ca đang truyền, cắt đường trong môi trường thử rồi xác nhận timeout. Ghi deadline, trạng thái cây tiến trình sau hủy, tệp dở, cleanup và lần truyền lại thành công với ID riêng. Thất bại nếu tiến trình còn chạy hoặc dữ liệu dở được publish.

## Cổng 1 · Demo bốn node

1. Cài cùng gói demo lên A/B/C/D. Một node chạy controller theo cấu hình demo. Ghi danh, ghép A với từng đích và xác nhận ghép trên hai đầu. Tạo job ở A qua UI cục bộ và chọn thiết bị B/C/D theo danh sách đã ghép. Mỗi đích mở offer dành cho thiết bị của mình, kiểm tra thông tin, xác nhận vị trí lưu và cho phép chuyển tiếp trên các đích dùng trong ca pipeline. Xác minh log điều khiển chưa cấp việc truyền cho đích đang chờ xác nhận.
2. Dùng file nhiều batch và cùng cấu hình batch đã chọn ở cổng 0. Chứng minh B forward batch k cho C sau khi k đã được xác minh/lưu bền và trong khi B vẫn nhận batch j khác từ A. Từ thời gian monotonic trên B, tính overlap bằng min(kết thúc RX, kết thúc TX) trừ max(bắt đầu RX, bắt đầu TX). Thu dòng thời gian A→C và tuyến D, cùng bằng chứng B↔C trực tiếp nếu quan sát được. 
3. Khi C đã xác minh ít nhất một batch và còn việc đang truyền, ngắt mạng C. Ghi trigger, heartbeat/lease, retry, đích/nguồn chọn lại và tiến độ B/D trong lúc C offline. Sau khi kết nối lại, kiểm tra reconcile và đối chiếu danh sách batch xác minh trước sự cố với các lần RX thành công sau đó. Danh sách giao lại cho C không được chứa batch đã xác minh từ trước và còn nguyên. Cả B/C/D phải báo hash toàn file trùng A.
4. Trong một lần truyền, đóng/mở tab cùng agent. Lưu bằng chứng job vẫn tiến triển. Tạo job khác ở B, xác nhận nhận ở A và so SHA-256 toàn file. Kiểm tra khởi động lại node từ disk và một batch bị hỏng trong ca lỗi riêng. Batch hỏng phải thành missing/retry; batch bên cạnh hợp lệ được giữ. Lưu thêm kết quả timeout, duplicate ACK, late ACK và bão hòa slot/backpressure theo tick.

## Cổng 2 · So sánh

| Cấu hình | Chính sách |
|---|---|
| Direct | A gửi nguyên file riêng đến từng đích theo giới hạn slot chung. |
| Gateway nguyên file | B xác minh đủ file từ A trước khi gửi nguyên file riêng đến C/D. |
| Fixed Split | A gieo batch chẵn/lẻ đến B/C, sau đó B/C trao đổi khi hai phần đầu vào đã đủ; D nhận A theo tuyến đặt trước. |
| Gateway pipeline | Giữ B làm gateway; mỗi batch B xác minh được đưa vào hàng gửi C/D lập tức theo lịch cố định. |
| PLARS | Cùng batch và ngân sách với lịch tĩnh khớp điều kiện, chọn nguồn/đích theo ETA và tải. |

Thêm biến thể lịch cố định với cùng topology, batch size, cây tuyến cho phép, nút nghẽn và mức RX/TX với PLARS để cô lập hiệu ứng quyết định động. Nếu cùng topology nhưng khác giao thức/mức song song, giải thích tác động khi đọc kết quả.

- Chuẩn bị fixture hash cố định và cấu hình ghi được cho mỗi kịch bản. Khóa CPU/disk, slot, link rate/latency/loss, quan hệ bottleneck, relay, phiên bản, file và cấu hình quyền. Dùng một lần warmup không tính và ít nhất năm lần đo theo thứ tự chính sách xáo trộn với seed lưu lại. Tạo job và state mới mỗi lần, áp dụng cùng quy trình làm lạnh hoặc làm ấm cache.
- Hồ sơ tối thiểu gồm WAN B/C chung với LAN nhanh, B/C lệch tốc, C rớt mạng, D có đường A trực tiếp tốt. Thêm LAN/AP bận và băng thông bão hòa để kiểm tra zero byte dự phòng theo cấu hình mặc định. Ghi trigger lỗi định trước và thời điểm thực tế, cùng khoảng offline, ví dụ theo offset từ start đồng bộ sau consent.
- Giữ mọi run, kể cả timeout, hash sai và run thiếu số đo. Ghi trạng thái và lý do. Báo số lần đạt/tổng, median và khoảng min–max của run đạt, từng số đo thô và trường hợp lịch động chậm hơn. Makespan thiếu khi chưa đủ đích xác minh; ghi giới hạn quan sát và trạng thái tương ứng.
- So sánh tùy chọn với hệ thống ngoài chỉ sau khi khóa cùng môi trường và viết rõ khác biệt. Thử SafeExit riêng khi triển khai cổng 3.

## Thu thập và lưu bằng chứng

- `runs.csv` là một dòng mỗi run. `transfers.csv` là một dòng mỗi lần thử. Dùng trường rỗng cho số đo thiếu và ghi lý do trong notes. `status` nhận `pass`, `fail`, `timeout`, `blocked` hoặc `not_run`. Lưu log đã lược bí mật, cấu hình, số liệu giao diện/relay, trạng thái hash theo đích và script chạy dưới mã run.
- `makespan_ms` là từ thời điểm phát lệnh chạy sau consent đến ACK xác minh toàn file đích cuối cùng trên đồng hồ monotonic controller. Ghi thời điểm xác minh theo từng đích để kiểm tra. Với nguyên file, mỗi đích vẫn phải xác minh hash trước khi tính xong.
- Setup từ lúc bắt đầu phiên ở đầu mút quan sát đến byte đầu. Goodput là byte payload đã xác minh chia cho thời lượng từ byte đầu đến byte cuối. Nếu không có marker đáng tin cậy, để trống setup/goodput và mô tả sự kiện thay thế trong notes. Báo phân bố setup theo cỡ và số phiên. Kiểm tra overlap bằng cùng một đồng hồ monotonic, không lấy trừ trực tiếp timestamp từ hai máy.
- Payload nguồn A gồm byte do A thực sự gửi, kể cả retry, báo riêng byte mạng quan sát và interface. WAN bytes là số đếm hướng và biên đo đã định nghĩa, lưu giá trị theo từng WAN/relay. Tránh cộng hai đầu cùng một hop. Với relay, ghi các leg và phạm vi đã cộng. Timestamp, đơn vị, bộ đếm và phương pháp đo đi kèm log.
- Retry bytes là byte payload thực gửi lại sau lần thất bại cho cùng đích/batch, gồm phần trùng đã đi trên mạng, xác định từ offset hoặc telemetry. Nếu chỉ biết byte của lần thử lại, ghi chỉ số proxy trong notes. Recovery time là từ trigger lỗi đến ACK batch hữu ích đầu tiên của job sau sự cố. Trong ca có đích cần phục hồi cụ thể, ghi thêm ACK đầu tiên tại đích sau reconnect.
- Utilization là tốc độ TX/RX của từng peer so với ngân sách đã khóa trong cùng cửa sổ, ghi riêng theo hướng. Byte dự phòng là payload của tác vụ đánh dấu chỉ để dự phòng. Dùng log để phân biệt tác vụ giao batch còn thiếu.
