# Tích hợp UI Kit v1.2

[UI Kit](ui-kit/README.md) nằm nguyên cấu trúc dưới `spec/ui-kit/`. Mở [bản HTML gộp](ui-kit/Ratatoss_UI_Preview.html) để xem offline, hoặc mở [index.html](ui-kit/index.html) khi cần thử bản nguồn cùng CSS, JS và ảnh đi kèm. Dữ liệu, tiến độ và tuyến truyền trong bộ mẫu là mô phỏng.

| Công việc | Tài liệu hoặc tệp chính |
| --- | --- |
| Bố cục, tương tác và trạng thái hiển thị | [UI Spec](ui-kit/docs/UI_SPEC.md), [Screen Blueprints](ui-kit/docs/SCREEN_BLUEPRINTS.md) |
| Màu sắc, kích thước, responsive và logo | [Design Tokens](ui-kit/docs/DESIGN_TOKENS.md), [Component Dimensions](ui-kit/docs/COMPONENT_DIMENSIONS.md), [CSS tokens](ui-kit/tokens.css), [assets](ui-kit/assets/) |
| Bàn giao cho agent | [Agent Handoff](ui-kit/docs/AGENT_HANDOFF.md), [Frontend Contracts](ui-kit/docs/FRONTEND_CONTRACTS.ts) |
| Quyền, xác minh file, trạng thái job và hợp đồng dữ liệu | [Brief v1.3](../docs/source/Ratatoss_Project_Brief_v1.3.md), [giao thức điều khiển](../docs/control-protocol.md), [OpenAPI](api/openapi.json) và [quy tắc quản trị](governance/README.md) |

Khi triển khai giao diện thật, dùng UI Kit làm chuẩn hình thức và luồng tương tác. Brief v1.2 kèm UI Kit lưu nguồn thiết kế của bản mẫu. Brief v1.3 và đặc tả dự án quy định hành vi sản phẩm. API `/v1` là hợp đồng controller dự kiến. Web chạy trong trình duyệt kết nối qua API cục bộ của Node như [kiến trúc](../docs/architecture.md) mô tả. Dùng các kiểu TypeScript trong kit làm view model đề xuất. Tra hợp đồng trước khi ánh xạ trường hoặc gọi API.

Dùng runtime và điểm vào hiện tại của dự án cho đến khi có quyết định kiến trúc mới. Các màn hình cần dữ liệu thật phải đọc trạng thái từ Node. Hiển thị dữ liệu mô phỏng với nhãn **DEMO**, và chỉ hiển thị **Đã xác minh** khi có xác nhận theo hợp đồng. Luồng mở web từ bản cài tuân theo [đặc tả bộ cài Windows](operations/windows-installer.md).

## Màn Nhận và Tiến độ (#70)

Mở trực tiếp [`ratatoss/static/preview/transfer.html`](../ratatoss/static/preview/transfer.html)
trong trình duyệt qua `file://`. Chọn ca Nhận và Tiến độ độc lập. Bấm **Chấp nhận**
hoặc **Từ chối** trong ca chờ quyết định để xem **Đang gửi xác nhận**. Ca đã chấp
nhận có bước xác nhận **Rút khỏi lượt gửi**. Nhãn **DEMO** luôn hiển thị. Dữ liệu
mẫu và hiệu ứng các nút chỉ dùng trong phiên mở trang.

### View model cho #9

Nạp `transfer-ui.css` và `transfer-ui.js` dưới dạng tệp ngoài. Gắn lớp
`rt-transfer` vào vùng chứa chung, thêm `rt-transfer-light` khi dùng nền sáng.
Gọi `window.RatatossTransferUI.renderOffer(root, view)` hoặc
`window.RatatossTransferUI.renderProgress(root, view)` trên hai vùng DOM riêng.
Mỗi lần gọi hiển thị lại từ snapshot. #9 giữ view model, xử lý hành động và
truyền trạng thái mới từ Node. Script thường cho phép cùng bộ render chạy
khi trình duyệt chặn ES module trên `file://`.

| View | Trường | Ý nghĩa |
| --- | --- | --- |
| `OfferView` | `offer_id`, `source_name`, `file_name`, `size_bytes`, `expires_at` | ID offer, tên nguồn công bố, tên tệp, số byte và thời hạn ISO. Hiển thị thời hạn theo múi giờ của trình duyệt. |
| `OfferView` | `save_location`, `reason` | Vị trí lưu do Node quản lý và lý do hiển thị đã lọc bí mật. Chưa có giá trị thì truyền `null`. |
| `OfferView` | `state`, `ui`, `allow_forward` | Trạng thái offer `PENDING\|ACCEPTED\|DECLINED\|EXPIRED\|REVOKED`, trạng thái UI `idle\|sending\|error` và tùy chọn chuyển tiếp mặc định `false`. Dùng thẻ `ACCEPTED` khi còn có thể rút. |
| `ProgressView` | `job_id`, `total_bytes`, `verified_bytes` | ID job, tổng byte và byte đã xác minh. Sau đối chiếu, snapshot có thể trả ít byte đã xác minh hơn snapshot trước. |
| `ProgressView` | `activity`, `connection`, `rechecking` | Danh sách hoạt động từ `downloading\|verifying\|forwarding\|assembling`, trạng thái kết nối `ok\|peer_offline\|controller_offline\|waiting_source` và cờ đang kiểm tra lại dữ liệu. |
| `ProgressView` | `receipt`, `file_verified`, `location` | `pending\|sent`, cờ Node đã xác minh và công bố tệp cuối, vị trí tệp hoặc `null`. Trạng thái xác minh và vị trí phụ thuộc vào `file_verified`. |
| `ProgressView` | `eta`, `outcome` | ETA có cơ sở đo, theo mili-giây, `"estimating"` hoặc `null`. Kết quả job là `open\|partial\|complete`. |
| `ProgressView` | `recipient_results` (tùy chọn) | Với `partial`, snapshot của nguồn có thể kèm mảng `{device_name, file_verified, reason?}` để hiện số đích đã xác minh và lý do của các đích còn lại. Bỏ trường này khi người xem chỉ có quyền xem phần của mình. |

| Sự kiện phát từ `root`, có bubble | `event.detail` | Xử lý tại #9 |
| --- | --- | --- |
| `ratatoss:offer-decision` | `{offer_id, decision, allow_forward}` | `decision` là `ACCEPT` hoặc `DECLINE`. Khi chấp nhận, Node lưu vị trí và quyết định, lấy hash manifest theo offer và gửi `allow_forward`. Khi từ chối, Node chỉ gửi `decision` trong body controller. |
| `ratatoss:offer-withdraw` | `{offer_id}` | Phát sau khi xác nhận rút. Node xử lý dừng RX/TX và đồng bộ với điều phối theo giao thức. |

### CSP và đóng gói

- #9 cần phục vụ JS và CSS theo route cùng origin qua loopback, rồi thêm
  `script-src 'self'` vào CSP hiện có. DOM nhận tên thiết bị, tên tệp, đường dẫn
  và lý do dưới dạng văn bản. Hai renderer chỉ hiển thị snapshot và phát sự kiện.
- Wheel lấy hai asset dùng thật từ glob `static/*`. Hai tệp dưới
  `static/preview/` nằm ngoài glob này. PyInstaller của macOS chép cả
  thư mục `ratatoss/static/`, gồm preview **DEMO**. Các route hiện tại của
  starter phục vụ `/` và `/style.css`.
