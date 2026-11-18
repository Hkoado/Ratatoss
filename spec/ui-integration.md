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
