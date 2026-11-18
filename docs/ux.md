# Giao diện Ratatoss Node

Mỗi máy mở cùng giao diện local khi khởi động Node. Thanh điều hướng gồm **Thiết bị**, **Gửi**, **Nhận** và **Tiến độ**. Người dùng có thể đóng tab rồi mở lại và thấy phiên đang chạy. Node tiếp tục chạy trong nền. Thoát Node dừng Croc trên máy đó và giữ dữ liệu đã xác minh.

## Thiết bị

- Lần đầu mở, người dùng đặt tên và nhập mã ghi danh được cấp. Hiển thị tên và hậu tố ID riêng, trạng thái kết nối controller và nút thử lại khi mất mạng.
- Chọn **Ghép thiết bị**, rồi tạo mã hoặc nhập mã được chia sẻ. Sau claim, hai máy cùng thấy tên, hậu tố ID của nhau và chuỗi đối chiếu. Người dùng so sánh chuỗi qua kênh họ đang dùng để liên lạc, sau đó cả hai bấm **Xác nhận**. Danh sách thiết bị chỉ cho chọn đích khi cả hai đã xác nhận.
- Hiển thị cặp đang chờ, hạn mã và trạng thái bị từ chối hoặc hết hạn. **Hủy ghép** ngưng offer mới và thu hồi offer còn chờ giữa hai máy. Giải thích ngay trong hộp thoại rằng job đã đồng ý có thể được rút ở màn hình tiến độ.

## Gửi

1. Chọn một file và các thiết bị đã ghép. Hiển thị tổng dung lượng, tên + hậu tố ID từng đích và mô tả rằng thiết bị nhận có thể chọn cho phép chuyển tiếp, cho phép thiết bị đó đọc dữ liệu batch.
2. Bấm **Gửi lời mời**. UI theo dõi quá trình nhập file vào kho và tính hash, rồi chuyển sang bảng đích khi controller xác nhận tạo job. Lỗi dung lượng, mất kết nối hoặc file đã thay đổi được hiển thị ở bước tương ứng.
3. Hiển thị từng đích **Chờ đồng ý**, **Đã đồng ý**, **Đang nhận**, **Mất kết nối**, **Đã xác minh**, **Từ chối**, **Hết hạn**, **Đã rút** hoặc **Đã hủy**, với trạng thái chuyển tiếp khi có. **Hủy lượt gửi** là hành động nguồn, giữ kết quả các đích đã hoàn tất.

## Nhận

1. Hộp thư tự liệt kê offer gửi đến thiết bị này. Chọn thẻ để xem người gửi, tên file, dung lượng và thời hạn.
2. Chọn vị trí lưu do Node quản lý và tên đích an toàn. Mặc định dùng thư mục nhận đã cấu hình và tên đã xử lý cho HĐH. Chọn thư mục từ cấu hình local thông qua Node; browser file picker chỉ dùng nhập file nguồn. Hiển thị đủ dung lượng dự kiến cho staging, kho batch và file ghép theo volume. Nếu vị trí trùng file đã có, yêu cầu tên khác.
3. Chọn **Chấp nhận** hoặc **Từ chối**. Tùy chọn **Cho phép chuyển tiếp trong lượt gửi này** mặc định tắt, độc lập với quyết định nhận file. Hiển thị rõ tệp sẽ lưu ở đâu và thiết bị nào là nguồn công bố. UI lưu quyết định cục bộ trước khi gửi và hiển thị **Đang gửi xác nhận** đến khi controller phản hồi. Khi offer hết hạn hoặc bị thu hồi, dừng quy trình và giữ lý do trên thẻ.
4. Sau khi chấp nhận, Node tự tải, kiểm và ghép. **Rút khỏi lượt gửi** dừng RX/TX liên quan khi xác nhận, giữ batch cục bộ đến lúc dọn kho. Nếu mất controller, hiện yêu cầu rút đang chờ đồng bộ và ngừng worker của job tại máy này ngay.

## Tiến độ và khả năng phục hồi

- Hiển thị byte **đã xác minh** / tổng byte ở phần chính. Dùng chỉ báo riêng cho đang tải, đang kiểm, đang chuyển tiếp và đang ghép. Số byte đã xác minh có thể giảm nếu lần đối chiếu phát hiện hỏng. Chỉ hiển thị **Đã xác minh** và vị trí file sau khi file cuối đã công bố ở Node. Nếu receipt còn chờ, ghi **Đã lưu trên máy · chờ báo người gửi**.
- Dùng nhãn **Mất kết nối máy** khi một peer offline, **Mất kết nối điều phối** khi chính Node không gọi được controller, và **Chờ nguồn có batch** khi mọi nguồn hợp lệ cho một batch đang vắng. Khi quay lại, hiển thị **Đang kiểm tra dữ liệu đã lưu** rồi cập nhật từ số byte còn hợp lệ. Chỉ hiện ETA nếu có cơ sở đo cho phiên và có thể ghi **Đang ước tính**.
- Nếu một đích bị lỗi vị trí hoặc dung lượng, cho đổi đích cục bộ hoặc thử lưu lại trên batch đang giữ. Cho xem lý do ngắn đã lọc bí mật, giữ nguyên các kết quả đã hoàn tất. Job mở với máy offline vẫn hiện **Đang chờ**. Job kết thúc với một phần đích verified hiển thị **Hoàn tất một phần**, kèm số đích xác minh trên tổng số đích và lý do cho từng đích còn lại.
- Dùng văn bản bên cạnh chỉ báo tiến độ, thông báo thay đổi có thể đọc bằng công nghệ hỗ trợ và giữ tiêu điểm trong bước xác nhận. UI chỉ lấy trạng thái qua API loopback, không nhận token controller hoặc mã Croc.
