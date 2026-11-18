# Đặc tả Ratatoss

## Kế hoạch Astra

1. Đối chiếu brief, thiết kế và kế hoạch gốc để xác định phạm vi của API, cơ sở dữ liệu và vận hành.
2. Đặt đặc tả triển khai trong `spec/` và lập bộ đối chiếu SHA-256 cho toàn bộ tệp gốc trong `docs/` và `plan/`.
3. Kiểm tra tính nhất quán của đặc tả với nguồn, ghi rõ điểm chưa có bằng chứng và xác minh các tệp gốc sau khi hoàn tất.

## Triển khai Sol

| Mục | Phạm vi |
| --- | --- |
| [Quản trị](governance/README.md) | Thứ tự thẩm quyền, quy tắc bằng chứng, quy trình đề xuất thay đổi và kiểm tra tệp gốc |
| [API](api/) | Hợp đồng giao tiếp |
| [Cơ sở dữ liệu](db/) | Mô hình dữ liệu và các bất biến khi lưu trữ |
| [Vận hành](operations/) | Cấu hình, triển khai và kiểm tra vận hành |
| [Bộ cài Windows](operations/windows-installer.md) | Đóng gói, mở Web/CLI bằng shortcut, cập nhật và nghiệm thu trên máy sạch |
| [Tích hợp giao diện](ui-integration.md) | UI Kit v1.2, điểm mở demo và thứ tự ưu tiên khi nối giao diện với Node |

Các mục trong `spec/` ghi rõ nguồn và phân biệt yêu cầu gốc, quyết định đã duyệt, đề xuất triển khai và kết quả đã kiểm chứng. Trước khi sử dụng hoặc sửa đặc tả, áp dụng [quy tắc quản trị](governance/README.md).
