# Kiến trúc Ratatoss Node

Tài liệu này đặc tả MVP của [Ratatoss Project Brief v1.3](source/Ratatoss_Project_Brief_v1.3.md). Mỗi máy dùng cùng một bản Ratatoss Node, có thể tạo job, nhận file và chuyển tiếp. Một thiết bị có thể giữ các vai trò khác nhau giữa các job. Job có đúng một controller. Khi một máy chạy cả Node lẫn controller, hai thành phần vẫn dùng listener và vùng lưu trữ riêng.

| Thành phần | Trách nhiệm |
|---|---|
| Node (Python, FastAPI) | Phục vụ HTML/CSS/JS cùng API trên `127.0.0.1`, quản lý định danh, offer và tùy chọn cục bộ, điều khiển worker RX/TX, giữ tiến độ trên đĩa. Đóng tab không dừng Node. |
| Controller (FastAPI, SQLite) | Ghi nhận thiết bị và ghép cặp, manifest/offer/đồng ý, heartbeat, tình trạng batch, lease phân công và receipt. Agent chủ động gọi HTTPS. |
| TransportAdapter | Chạy Croc phiên bản ghim cho một batch giữa hai node, có thư mục làm việc riêng, timeout, dừng cây tiến trình và phân loại kết quả đã lọc bí mật. |
| Kho Node | Nhập file nguồn theo luồng, kiểm tra manifest, lưu batch bất biến, ghép và công bố file cuối, ghi outbox để gửi lại ACK/receipt. |

## Biên mạng và quyền

- UI local ở loopback, kiểm tra Host đúng địa chỉ/cổng đã bind. Mọi thao tác đổi trạng thái yêu cầu Origin đúng và phiên local kèm token CSRF. Trang UI dùng cùng origin với API. Cổng HTTPS controller độc lập và có thể truy cập từ LAN demo hoặc Internet. Không expose API local ra LAN.
- Quản trị viên cấu hình URL HTTPS và trust store riêng cho controller rồi cấp mã ghi danh ngoài băng cho từng node. Demo LAN dùng CA riêng được cài trước trên các máy, cùng chứng thư có SAN khớp địa chỉ HTTPS. Triển khai Internet dùng chứng thư từ CA tin cậy. Kết nối sai hostname, lỗi chuỗi hoặc hết hạn phải dừng. Quyền thiết bị thuộc token riêng của nó.
- Ghép cặp hai phía xác nhận, rồi gửi offer có đích là thiết bị cụ thể. Đích xem thông tin và đồng ý riêng cho từng offer. Việc đồng ý nhận và cho phép chuyển tiếp là hai lựa chọn; chuyển tiếp chỉ áp dụng giữa thành viên đã đồng ý của cùng job. Nguồn công bố rõ trước khi gửi rằng thiết bị được phép chuyển tiếp có thể đọc dữ liệu batch.
- Controller giữ metadata và bí mật điều phối ngắn hạn. Croc truyền batch theo cặp, có thể dùng relay ở đường dữ liệu. Mã Croc tách riêng từng lần giao và chỉ cấp hai đầu. Peer chuyển tiếp thấy plaintext. Mô hình MVP tin controller và các thiết bị được chọn cho job. Chi tiết quyền và lưu trạng thái ở [Giao thức](control-protocol.md) và [Lưu trữ](storage-and-recovery.md).

## Luồng dữ liệu

1. Nguồn nhập file vào kho Node, tính manifest và công bố job khi bản nguồn đã lưu bền vững. Offer giữ nguyên manifest đã công bố.
2. Đích chấp nhận offer và chuẩn bị dung lượng tại chỗ. Controller xét đích đã đồng ý, online, đã đối chiếu dữ liệu, còn slot và còn thiếu batch.
3. Một lần giao có lease, thư mục staging và phiên Croc riêng. Đích kiểm tra batch và từng piece rồi ghi bền vững. ACK xác nhận quyền dùng batch để chuyển tiếp. Tiến trình batch kế tiếp có thể tiếp tục chạy đồng thời.
4. Đích kiểm SHA-256 toàn file và công bố file ở vị trí người dùng đã chọn trước khi ghi receipt hoàn tất. Nguồn xem kết quả từng thiết bị. Một đích hoàn tất có thể tiếp tục chuyển tiếp theo quyền đã cấp.

## Điều phối MVP

- Dùng kế hoạch cố định theo cấu hình mạng đã kiểm chứng, với danh sách nguồn ưu tiên cho từng đích và batch. Ví dụ B nhận batch chẵn từ A, C nhận batch lẻ từ A, mỗi bên ưu tiên lấy phần còn thiếu từ bên kia sau ACK, D ưu tiên A. Khi một nguồn ưu tiên offline, quá số lần thử, hoặc chưa có batch sau thời gian chờ cấu hình, chọn nguồn đã xác minh trong danh sách fallback, gồm A. Khi chưa có nguồn khả dụng thì đợi, giữ phần đích đã nhận.
- Phân công theo vòng công bằng giữa các đích đủ điều kiện và theo batch ID tăng dần trong mỗi đích, bỏ qua cặp đã có lần giao hiệu lực. Giới hạn RX/TX độc lập (khởi điểm cấu hình demo: 1 RX và 1 TX/node), giới hạn tải phiên trên controller và queue local hữu hạn. Khi hết dung lượng, worker bận hoặc Node chưa đối chiếu xong, Node không giữ thêm slot. Giới hạn 1 RX và 1 TX vẫn cho phép pipeline hai chiều.
- Sau lỗi có thể thử lại, chờ theo cấp số nhân 1/2/4/8/16/30 giây kèm jitter, tối đa 3 lần liên tiếp cho mỗi (nguồn, đích, batch). Sau ngưỡng, ưu tiên nguồn kế; khi hết nguồn, hiện chờ và mở lại sau 60 giây hoặc khi inventory/kết nối thay đổi. Lỗi đích hết dung lượng khóa RX cho đến khi Node báo đủ dung lượng. Khi mất quyền hoặc hủy job, dừng lần giao và loại khỏi hàng đợi.
- Ra quyết định khi có ACK mới, heartbeat/lease đổi trạng thái và ở tick định kỳ. Chỉ điều phối chuyển batch cho đích còn thiếu. Nhân bản dự phòng mặc định tắt. Lịch cố định vẫn giao lại khi mất mạng và tiếp tục dựa vào các batch đã xác minh.
- Đo thực nghiệm Croc và chạy MVP trên bốn máy trước khi bật lịch thích ứng. Giai đoạn sau đo goodput từng tuyến, ngân sách liên kết dùng chung và ETA để so sánh Direct, Gateway và Swarm. SafeExit, khôi phục service controller tự động, chữ ký manifest và mã hóa xuyên hop thuộc phạm vi mở rộng.
