# Giao thức điều khiển v1

API agent–controller dùng HTTPS và JSON UTF-8 tại `/v1`. Có một phiên bản protocol chính trên đường dẫn. Thời gian trên wire là UTC RFC 3339, kích thước là byte, hash SHA-256 viết thường ở dạng hex. `device_id`, `pair_id`, `job_id`, `offer_id`, `assignment_id` và mã yêu cầu là UUID ngẫu nhiên. Controller cấp định danh tài nguyên. Agent tạo mã yêu cầu và giữ nguyên khi gửi lại.

## Ghi danh và ghép cặp

| Route | Quyền và hiệu ứng |
|---|---|
| `POST /devices/enroll` | Node gửi mã ghi danh 256 bit dùng một lần cùng tên hiển thị. Quản trị cấp ngoài băng với TTL 10 phút, giữ hash và tiêu thụ nguyên tử khi cấp ID + token riêng 256 bit. Mã mất vì timeout sau khi tiêu thụ được thay bằng mã quản trị cấp lại; thu hồi token/node mồ côi trước khi cấp lại. |
| `GET /devices/me` | Token của Node trả định danh và tên của chính nó. |
| `POST /pairs` | Node đã ghi danh mở phiên ghép, nhận mã ngẫu nhiên 128 bit và TTL 10 phút. Người dùng chia sẻ mã ngoài băng. |
| `POST /pairs/claim` | Node đã ghi danh khác dán mã để gắn vào phiên. Claim lấy mã một lần và trả định danh giao dịch, chưa cấp quyền. |
| `GET /pairs` | Liệt kê phiên của thiết bị, thông tin xác nhận và cặp đã kích hoạt. Với claim hợp lệ trả tên, hậu tố ID hai máy và cùng một chuỗi đối chiếu sáu chữ số ngẫu nhiên. |
| `POST /pairs/{pair_id}/decision` | Mỗi bên bấm xác nhận sau khi đối chiếu chuỗi ngoài băng, hoặc từ chối. Cặp chỉ `ACTIVE` khi cả hai xác nhận trong TTL, kết thúc ngay nếu có từ chối. Cấm tự ghép và chỉ có một cặp ACTIVE cho mỗi cặp thiết bị. |
| `DELETE /pairs/{pair_id}` | Một trong hai bên có thể hủy ghép. Chặn offer mới và chuyển offer đang chờ sang `REVOKED`. Các quyết định đã chấp nhận vẫn thuộc job của chúng, có nút rút riêng. |

Từ sau ghi danh, request gửi `Authorization: Bearer <device_token>`. Controller chỉ lưu SHA-256 của token ngẫu nhiên, tra cứu thiết bị và kiểm quyền cho mọi tài nguyên. Node lưu token trong kho bí mật HĐH hoặc file riêng ACL chỉ tài khoản chạy Node đọc được. Thu hồi token chặn mọi request, hết hiệu lực các lần giao của thiết bị và giữ dữ liệu cục bộ. Bí mật, mã ghép và mã Croc không đi qua URL, log, UI tiến độ hoặc metrics. Trả lỗi chung khi mã sai/hết hạn và giới hạn tốc độ ghi danh/claim theo nguồn và danh tính nếu có.

## Job và consent

`POST /jobs` của nguồn tạo một job từ bản manifest đã lưu bền vững, với một offer cho từng thiết bị đang ghép ACTIVE. Tất cả offer gắn với manifest hash và nguồn cố định. Dùng tên file hiển thị đơn, giới hạn trường và kích thước manifest theo cấu hình bản đóng gói. Controller xác minh digest, cấu trúc, tổng độ dài, offset, batch và đối tượng nhận trước commit. Tính `manifest_sha256` theo [quy tắc canonical](storage-and-recovery.md#manifest-và-đối-tượng-trên-đĩa). TTL offer mặc định 24 giờ, tính từ commit. Chỉ nguồn xem toàn bộ danh sách đích.

```json
{
  "manifest": {
    "version": 1, "name": "empty.bin", "size": 0,
    "piece_size": 4194304, "batch_size": 67108864,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "pieces": [], "batches": []
  },
  "target_device_ids": ["c074d7d2-7181-4e04-b6ef-731decff09a5"]
}
```

| Route | Quyền và hiệu ứng |
|---|---|
| `GET /offers` | Chỉ liệt kê offer gửi đến chính thiết bị; gồm tên nguồn, tên file, dung lượng, thời hạn và trạng thái. |
| `GET /offers/{offer_id}` | Đích xem manifest và hash chính xác để chuẩn bị vị trí lưu và xác nhận. |
| `POST /offers/{offer_id}/decision` | Đích gửi `{"decision":"ACCEPT","manifest_sha256":"<64 hex>","allow_forward":false}` hoặc `{"decision":"DECLINE"}`. `ACCEPT` chỉ từ `PENDING` trước TTL, với hash khớp, sau khi Node đã lưu quyết định và đích lưu cục bộ. |
| `POST /offers/{offer_id}/withdraw` | Đích rút tham gia khi đã nhận lời nhưng chưa hoàn tất. Cấm giao mới và đánh dấu các lần giao còn hiệu lực của đích (cả RX/TX) là `CANCELED`. |
| `POST /jobs/{job_id}/cancel` | Nguồn chấm dứt job mở, thu hồi offer còn chờ và dừng phân công. Receipt hợp lệ đã ghi vẫn hiển thị. |
| `GET /jobs/{job_id}/status` | Nguồn thấy từng đích, số byte đã xác minh, receipt và trạng thái job. Đích chỉ thấy phần của mình và metadata cần cho job. |

Vòng đời offer là `PENDING → ACCEPTED | DECLINED | EXPIRED | REVOKED`, rồi `ACCEPTED → WITHDRAWN | VERIFIED | CANCELED`. Offline là lớp trạng thái kết nối độc lập. Controller đóng khi mọi offer đã kết thúc. Kết quả `COMPLETE` khi mọi đích có receipt; `PARTIAL` khi chỉ một phần có receipt; `NO_DELIVERY` khi không có receipt; `CANCELED` khi nguồn đóng chủ động, kèm kết quả từng đích. Job vẫn mở nếu đích ACCEPTED chưa hoàn tất và mất mạng. Một đích đã VERIFIED vẫn có thể chuyển tiếp trong thời gian job mở nếu đã đồng ý.

## Phân công và báo cáo

| Route | Hợp đồng |
|---|---|
| `POST /devices/me/heartbeat` | 5 giây/lần khi online. Gửi `boot_id`, slot RX/TX còn trống và `active_assignment_ids`. Controller trả thời gian và trạng thái kết nối. Sau 20 giây không có heartbeat đánh dấu offline, vô hiệu lần giao liên quan. Đổi boot hoặc kết nối lại sau offline yêu cầu reconcile trước khi được giao việc. |
| `POST /jobs/{job_id}/reconcile` | Nguồn hoặc đích đã đồng ý gửi ảnh chụp đầy đủ `{"boot_id":"<UUID>","verified_batch_ids":[0,2]}` sau kiểm đĩa. Controller thay tập batch của đúng thiết bị trong một transaction. Batch bị hỏng khi đang chạy cũng lập tức chặn TX local và đồng bộ lại. |
| `GET /devices/me/assignments` | Poll 1 giây khi có slot hoặc đang chạy. Chỉ trả lần giao còn hiệu lực có thiết bị làm một đầu. Trả snapshot đầy đủ cùng `role`, hai ID thiết bị, `job_id`, `batch_id`, `assignment_id`, SHA-256 manifest, hạn lease, thời gian lease còn lại và tham chiếu cấu hình relay. |
| `POST /assignments/{id}/ready` | Đích xác nhận đã giữ slot và staging. Controller cấp mã Croc cho đích qua response và cho nguồn trong lần poll kế tiếp. Nguồn chỉ chạy khi nhận mã, đích khởi động RX ngay; adapter xử lý giới hạn thời gian đợi hai đầu. |
| `POST /assignments/{id}/ack` | Đích báo hash batch sau commit tại node. ACK thành công là bằng chứng batch có thể dùng làm nguồn. |
| `POST /assignments/{id}/fail` | Cả hai đầu có thể báo lỗi có mã như `NO_SLOT`, `NO_SPACE`, `TRANSPORT_TIMEOUT`, `CORRUPT`. Controller kiểm trạng thái hiện hành và kết thúc lần giao, giải phóng slot. |
| `POST /jobs/{job_id}/receipt` | Đích gửi `{"manifest_sha256":"<64 hex>","file_sha256":"<64 hex>","size":0}` sau kiểm SHA-256 toàn file và commit file cuối. Controller kiểm dữ liệu khớp manifest, đích đã đồng ý và có đủ batch trong registry, ghi một receipt cho mỗi job/đích. |

Lease khởi đầu 30 giây cho chuẩn bị. Khi RX báo ready, controller cấp hạn chạy 180 giây; giá trị được cấu hình và hiệu chỉnh từ chứng cứ thử Croc. Node dùng hạn sớm hơn giữa timeout adapter và lease, tính trên monotonic clock theo khoảng thời gian controller trả về. Node dừng Croc và bỏ vùng staging chưa commit khi hết hạn hoặc lần giao biến mất khỏi snapshot đầy đủ. Khi đứt HTTPS, Node có thể giao xong phiên đã cấp mã trong giới hạn lease và giữ ACK trong outbox. Không mở phiên mới khi không nhận được lease hợp lệ.

```json
{
  "assignment_id": "19e49ea6-5790-44d0-a5a6-6a3e95d0f85f",
  "job_id": "d809bf2c-ad5a-4d45-a72d-937ac69b6a4c",
  "batch_id": 2, "role": "RX", "state": "OFFERED",
  "source_device_id": "720843f4-b360-48f5-9200-5afa2372d2f7",
  "target_device_id": "c074d7d2-7181-4e04-b6ef-731decff09a5",
  "lease_expires_at": "2026-11-18T12:00:30Z",
  "lease_remaining_ms": 30000,
  "manifest_sha256": "1111111111111111111111111111111111111111111111111111111111111111",
  "relay_profile": "demo-lan"
}
```

## Thử lại và lỗi API

Agent gửi `Idempotency-Key` cho thay đổi bền vững. Controller giữ hiệu ứng theo khóa `(device_id, method, route, key)` và digest payload trong thời gian job hoặc pair còn tồn tại, trả kết quả cũ khi lặp cùng payload và `409` nếu khác. `ready` lặp phải dùng cùng mã phiên và chỉ trả trong lease đang hiệu lực; không tái kích hoạt thời hạn. Response lỗi có dạng `{"error":{"code":"STATE_CONFLICT","message":"..."}}`. Dùng `400` cho payload sai định dạng, `401` nếu chưa xác thực, `404` cho tài nguyên ngoài phạm vi, `409` cho xung đột vòng đời, `410` cho offer/lease đã hết hạn và `429` khi quá giới hạn. Node retry lỗi mạng, `429` và `5xx` với backoff 1–30 giây có jitter, tôn trọng `Retry-After`; lỗi consent hoặc quyền phải hiển thị.

Một ACK đúng đích và hash đến muộn vẫn có thể bổ sung availability cho đích còn quyền tham gia. Nó chỉ thay trạng thái lần giao cùng ID nếu lease đó còn hiệu lực. Nếu đã có lần giao mới cho batch đó, scheduler hủy lần mới qua hành động độc lập vì batch đã có. ACK cũ đã được xử lý chỉ trả kết quả trước, không thêm lại batch sau reconcile đã loại. Sau reboot/reconnect, Node gửi reconcile trước, sau đó chỉ phát lại ACK của batch hiện còn hợp lệ và receipt còn chờ.
