# Hợp đồng API Ratatoss

[openapi.json](openapi.json) đặc tả giao thức HTTPS giữa agent và controller tại `/v1`. URL máy chủ là địa chỉ mẫu. Có thể dùng tài liệu để triển khai controller và agent, dựng máy chủ giả lập hoặc kiểm tra JSON. [Giao thức điều khiển](../../docs/control-protocol.md) quy định quyền truy cập, vòng đời và thử lại. [Lưu trữ và phục hồi](../../docs/storage-and-recovery.md) quy định thứ tự ghi bền vững, cách tính hash manifest canonical và đối chiếu sau sự cố.

Đặc tả chốt tên trường, cấu trúc response và mã HTTP thành công ở những chỗ giao thức để mở. ID tài nguyên và khóa idempotency dùng UUIDv4. Mã ghi danh và token thiết bị dùng 64 ký tự hex thường, mã ghép dùng 32 ký tự hex thường. Trường `connection` của mỗi bên trong `GET /v1/pairs` độc lập với vòng đời cặp. Cặp `ACTIVE` có ID đầy đủ của thiết bị bên kia để chọn làm đích, còn `expires_at` ghi hạn xác nhận ban đầu.

RX nhận mã Croc từ `ready`, còn TX nhận từ snapshot khi lần giao ở trạng thái `RUNNING`. Các snapshot `OFFERED` và `RUNNING` của RX đều bỏ trường mã. Thử lại `ready` cùng khóa trong lease trả lại cùng mã và hạn với thời gian còn lại tại thời điểm trả lời. ACK khi lease còn hiệu lực chuyển lần giao sang `ACKED`. Kết quả `LATE_ACKNOWLEDGED` trên wire ghi nhận ACK muộn, giữ nguyên trạng thái đã lưu của lần giao.

JSON Schema kiểm tra cấu trúc, kiểu và ràng buộc cục bộ. Controller còn phải kiểm quyền trên tài nguyên, vòng đời, hạn lease, thứ tự thời gian, giới hạn theo cấu hình, hash canonical, độ phủ và kích thước các đoạn, tính hợp lệ của các thiết bị đích và sự nhất quán giữa receipt với inventory. Bộ giải mã phải từ chối khóa JSON lặp và Unicode không hợp lệ. Giữ bí mật mọi response chứa mã.

## Tệp mẫu theo route

Trong `openapi.json`, mỗi request hoặc mã response có mẫu ở `content.application/json.examples`. `value` là JSON mẫu có sẵn trong đặc tả và `x-example-file` trỏ tới tệp JSON tương ứng trong [examples](examples/). Các response lỗi dùng chung schema trong `components.responses`. Tra `responses` của từng route để biết những mã lỗi áp dụng.

| Phương thức và đường dẫn | HTTP thành công | Tên tệp mẫu trong `examples/` |
| --- | --- | --- |
| `POST /v1/devices/enroll` | 201 | `enroll-*` |
| `GET /v1/devices/me` | 200 | `device-me-response.json` |
| `POST /v1/pairs` | 201 | `pair-create-*` |
| `POST /v1/pairs/claim` | 200 | `pair-claim-*` |
| `GET /v1/pairs` | 200 | `pairs-claimed-response.json`, `pairs-active-response.json` |
| `POST /v1/pairs/{pair_id}/decision` | 200 | `pair-decision-request.json`, `pair-*-decision-response.json`, `pair-*-active-response.json`, `pair-active-response.json` |
| `DELETE /v1/pairs/{pair_id}` | 200 | `pair-revoke-response.json` |
| `POST /v1/jobs` | 201 | `job-create-*` |
| `GET /v1/offers` | 200 | `offers-list-response.json` |
| `GET /v1/offers/{offer_id}` | 200 | `offer-detail-response.json` |
| `POST /v1/offers/{offer_id}/decision` | 200 | `offer-accept-*`, `offer-peer-accept-*`, `offer-decline-*` |
| `POST /v1/offers/{offer_id}/withdraw` | 200 | `offer-withdraw-response.json` |
| `POST /v1/jobs/{job_id}/cancel` | 200 | `job-cancel-response.json` |
| `GET /v1/jobs/{job_id}/status` | 200 | `job-source-status-response.json`, `job-target-status-response.json` |
| `POST /v1/devices/me/heartbeat` | 200 | `heartbeat-*` |
| `POST /v1/jobs/{job_id}/reconcile` | 200 | `reconcile-*` |
| `GET /v1/devices/me/assignments` | 200 | `assignment-*-offered-response.json`, `assignment-*-running-response.json`, `assignment-clear-response.json` |
| `POST /v1/assignments/{id}/ready` | 200 | `assignment-ready-response.json`, `assignment-ready-replay-response.json`, `assignment-peer-ready-response.json` |
| `POST /v1/assignments/{id}/ack` | 200 | `ack-request.json`, `ack-response.json`, `ack-late-response.json`, `ack-peer-response.json` |
| `POST /v1/assignments/{id}/fail` | 200 | `assignment-fail-*` |
| `POST /v1/jobs/{job_id}/receipt` | 200 | `receipt-*` |

Các mã 400, 401, 404, 410 và 429 có mẫu `error-<mã>.json`. Mã 409 có mẫu `error-idempotency.json`.

## Chạy qua vòng đời bằng dữ liệu mẫu

Tệp request chứa phần thân JSON. Gửi `Content-Type: application/json` với request có body, bearer token của đúng thiết bị gọi API và khóa UUIDv4 trong `Idempotency-Key` khi route yêu cầu. Giữ nguyên khóa và payload khi thử lại cùng thao tác. Các mã ghi danh, token, mã ghép và mã Croc đều là dữ liệu tổng hợp. Khi phát lại với controller thử nghiệm, thay bằng ID và thông tin xác thực do controller đó cấp.

1. Dùng `enroll-source-*`, `enroll-target-*` và `enroll-peer-*` cho Atlas, Birch và Cedar. Atlas mở hai phiên ghép. Birch và Cedar claim bằng các mã riêng. Mỗi bên đọc chuỗi đối chiếu từ danh sách cặp, đối chiếu ngoài băng rồi gửi `pair-decision-request.json`. Lần xác nhận thứ nhất giữ cặp ở `CLAIMED`, lần thứ hai chuyển sang `ACTIVE`.
2. Atlas tạo job từ `job-create-request.json` cho Birch và Cedar. Mỗi đích chỉ liệt kê offer của mình, đọc manifest rồi chọn vị trí lưu cục bộ trước khi chấp nhận đúng digest. Birch dùng `offer-accept-*`, Cedar dùng `offer-peer-accept-*`. Các mẫu từ chối, rút lời, hủy job và hủy cặp minh họa các nhánh khác.
3. Cả ba thiết bị gửi heartbeat với boot ID riêng, sau đó gửi snapshot `reconcile-*` của chính mình. Atlas có batch duy nhất, còn inventory của hai đích đang trống. Trong quá trình giao, tiếp tục heartbeat và cập nhật số slot trống cùng ID của lần giao đang chạy.
4. Birch poll với vai trò RX rồi gọi ready. Dùng lại cùng khóa để nhận `assignment-ready-replay-response.json` với cùng mã Croc và hạn lease. Atlas nhận mã qua poll TX. Birch kiểm tra và ghi bền vững batch trong hạn lease. ACK đến controller sau hạn và nhận `ack-late-response.json`. Nếu scheduler đã cấp một lần giao thay thế, nó hủy lần giao thừa qua thao tác riêng. `assignment-clear-response.json` minh họa snapshot của Birch khi lần giao cũ đã rời tập đang hoạt động.
5. Atlas gửi batch cho Cedar qua lần giao riêng trong nhóm mẫu `assignment-peer-*`. Cedar ACK trong hạn lease và nhận `ack-peer-response.json`. Mỗi đích xác minh và công bố bền vững file hoàn chỉnh rồi gửi `receipt-request.json` bằng token riêng. Đọc hai mẫu trạng thái job sau receipt thứ hai. Nhánh lỗi lần giao dùng `assignment-fail-*`. Để tái hiện mẫu 409, gửi một payload hợp lệ nhưng khác payload đã gắn với khóa từng dùng trên cùng route và thiết bị.

[sample.txt](examples/sample.txt) có 17 byte, gồm cả LF cuối file. SHA-256 của file, piece duy nhất và batch duy nhất là `de541afdc888a29e740aa4fb394b67ff725f17279e083812fc61b85af73276ee`. Tính SHA-256 của manifest đã validate sau khi mã hóa bằng `json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")` sẽ được `166d130902115c21f249e2432f4cf605926cfdff345f38d573f13fea37e6b756`.

### Tích hợp manifest v1

Node dùng `Manifest.from_json(raw)` để đọc manifest độc lập. Với manifest lồng trong request hoặc response, Node và controller gọi `body = decode_manifest_object(raw_body)` trên byte UTF-8 gốc rồi gọi `Manifest.from_dict(body["manifest"])`. Cách này phát hiện khóa lặp cả ở vỏ request và trong từng segment trước khi tầng HTTP chuyển JSON thành từ điển. Route kiểm các trường còn lại và quyền truy cập theo hợp đồng của mình. [Mã dùng chung](../../ratatoss/manifest.py) · [Quy tắc lưu trữ](../../docs/storage-and-recovery.md#manifest-và-đối-tượng-trên-đĩa)

Dùng `Manifest.canonical_bytes()` để lưu metadata canonical và `Manifest.manifest_sha256()` để tính digest của metadata. `Manifest.sha256` là digest của toàn bộ payload. CLI `verify` đọc được các tệp manifest v1 dạng thụt lề của CLI `manifest` và dạng canonical.

## Mô-đun ghi danh và ghép cặp của controller

[`ratatoss/controller/`](../../ratatoss/controller/__init__.py) hiện thực `POST /v1/devices/enroll`, `GET /v1/devices/me`, `POST /v1/pairs`, `POST /v1/pairs/claim`, `GET /v1/pairs` và `POST /v1/pairs/{pair_id}/decision`. Route hủy cặp và mọi route job, offer, lease thuộc phần tích hợp control plane.

| Giao diện | Dùng khi |
| --- | --- |
| `create_router(connect=..., pair_code_key=...)` | Gắn các route trên vào ứng dụng controller. `connect` trả kết nối SQLite controller mới cho mỗi request. `pair_code_key` dài tối thiểu 32 byte, nằm ngoài DB và giữ ổn định qua restart để dựng lại mã ghép khi phát lại request tạo cặp. |
| `authenticate(connection, authorization_headers)` | Lấy `Device` của người gọi từ đúng một header `Authorization: Bearer <token>`. Trả `None` khi thiếu, sai định dạng, không tồn tại hoặc đã thu hồi. |
| `still_valid(connection, device)` | Kiểm lại đúng token của `Device` trong giao dịch ghi hiện tại. Gọi ngay sau `BEGIN IMMEDIATE`, trước tra cứu idempotency hay ghi. Trả `False` khi token đã bị thu hồi trong lúc request chờ khóa. |
| `active_pair_id(connection, a, b)` | Kiểm hai thiết bị có cặp `ACTIVE`. Gọi trong giao dịch tạo job cho từng đích. |
| `active_peer_ids(connection, device_id)` | Liệt kê thiết bị người gọi có thể chọn làm đích. |
| `issue_enrollment_code(connection, now_ms=...)` | Cấp mã ghi danh một lần, TTL 10 phút, để quản trị chia sẻ ngoài băng. |

DB chỉ giữ SHA-256 của mã ghi danh, token và mã ghép. Mã đối chiếu sáu chữ số chỉ trả qua API đã xác thực cho hai thành viên. Bản ghi idempotency giữ kết quả đã lọc, không chứa mã ghép hay mã đối chiếu. Phát lại tạo cặp trả lại mã khi phiên còn `OPEN`, trả `409` khi đã claim và `410` khi đã hết hạn. Phát lại quyết định trả kết quả đã commit theo quyền hiện tại. Kết quả `CLAIMED` chỉ trả lại mã đối chiếu nếu phiên vẫn `CLAIMED` và còn hạn. Phiên đã hết hạn trả `410`, còn phiên đã chuyển sang trạng thái khác trả `409`. Đọc `GET /v1/pairs` để lấy trạng thái hiện tại. Thao tác ghi đọc đồng hồ sau khi có khóa `BEGIN IMMEDIATE`, nên request phải chờ khóa qua `expires_at` vẫn bị từ chối. Tạo cặp, claim và quyết định cũng kiểm lại token ngay sau khi có khóa, trước tra cứu idempotency. Token bị thu hồi trong lúc request chờ khóa nhận `401`, không ghi thay đổi và không phát lại phản hồi đã lưu. Hạn TTL giữ độ chính xác mili giây trên wire. Yêu cầu tại đúng `expires_at` bị từ chối. Ghi danh với tên chứa NUL trả `400` và giữ mã cho lần thử lại. Router giới hạn tốc độ ghi danh theo nguồn, và giới hạn claim theo cả nguồn lẫn thiết bị, với ngưỡng mặc định 10 và 20 request mỗi phút.

## API loopback của starter hiện tại

[app.py](../../ratatoss/app.py) phục vụ các route chỉ đọc sau tại `http://127.0.0.1:8765` mặc định.

| Phương thức và đường dẫn | Response thành công |
| --- | --- |
| `GET /` | Trang HTML của starter |
| `GET /style.css` | Stylesheet CSS |
| `GET /api/health` | `{"status":"ok","mode":"starter","transport_enabled":false}` |

Starter chỉ nhận client loopback và giá trị Host khớp chính xác địa chỉ loopback đã cấu hình. Nếu request có header Origin thì giá trị phải khớp chính xác origin loopback. Request không qua kiểm tra nhận HTTP 403 với plain text `Forbidden`. Các route OpenAPI sinh tự động, Swagger UI và ReDoc của FastAPI đã tắt.
