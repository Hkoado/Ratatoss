# Quản trị đặc tả Ratatoss

## Thẩm quyền của nguồn

1. [Brief v1.3](../../docs/source/Ratatoss_Project_Brief_v1.3.md) quy định ý tưởng, phạm vi và tiêu chí sản phẩm. Với luồng ở mục 6.1, [giao thức điều khiển](../../docs/control-protocol.md) và [thiết kế UX](../../docs/ux.md) quy định phần cập nhật. Node ghi danh, ghép hai chiều, chọn đích đã ghép và gửi offer để từng đích xác nhận. Xem [ràng buộc khi triển khai](../../CONTRIBUTING.md#5-ràng-buộc-khi-triển-khai).
2. Các tài liệu khác trong [docs/](../../docs/) cụ thể hóa kiến trúc, lưu trữ, phục hồi và thử nghiệm trong phạm vi brief. Trong [plan/](../../plan/), kế hoạch, backlog và lời nhắc điều phối quá trình triển khai. Tham số đề xuất trong kế hoạch cần số đo phù hợp hoặc cấu hình đã khóa cho ca thử.
3. Đặc tả mới trong [spec/](../README.md) chi tiết hóa cách triển khai và dẫn nguồn đến mục liên quan. Một ADR chỉ có hiệu lực theo phạm vi chủ dự án đã phê duyệt. Khi tài liệu cùng cấp xung đột hoặc phạm vi của một cập nhật chưa rõ, ghi nhận xung đột và xin quyết định qua ADR.
4. Mã, kiểm thử và quan sát thực tế là nguồn về hành vi hiện tại. Khi hành vi lệch đặc tả, ghi rõ sai lệch và nguồn bằng chứng rồi xử lý theo yêu cầu đã duyệt.

## Bằng chứng và phạm vi sửa

- Giữ nguyên ý tưởng, cấu trúc và nội dung gốc. Trong công việc bổ sung đặc tả, giữ nguyên mọi byte và đường dẫn dưới `docs/` và `plan/`. Cấm sửa, xóa, di chuyển, đổi tên, thêm tệp hoặc định dạng lại trong hai cây thư mục đó.
- Mỗi tuyên bố về một yêu cầu phải trỏ đến tệp và mục nguồn. Chi tiết suy ra hoặc bổ sung phải được đánh dấu **đề xuất**, với căn cứ và phần cần xác nhận. Dữ liệu mẫu phải ghi rõ **ví dụ tổng hợp**.
- Cấm bịa kết quả chạy, SHA-256, số đo, trích dẫn, lệnh hoặc trạng thái nghiệm thu. Ghi **chưa chạy**, **bị chặn** hoặc **không xác định** khi thiếu bằng chứng. Chỉ báo kết quả đã quan sát kèm lệnh, phiên bản, điều kiện chạy và hiện vật liên quan. Giữ bí mật và dữ liệu người dùng ngoài log, ảnh và kết quả thử.
- Khi có xung đột hoặc cần thay đổi nguồn, lập ADR đề xuất riêng dưới `spec/governance/adr/`. Ghi các nguồn và mục xung đột, lý do, phương án, ánh xạ thay đổi cần duyệt, tác động và trạng thái **chờ phê duyệt**. Cần phê duyệt rõ ràng của chủ dự án cho từng thay đổi vào tài liệu gốc hoặc đường chuẩn. Ghi lại quyết định và phạm vi được duyệt trước khi áp dụng.
- Mọi thay đổi vào trình kiểm tra, manifest hoặc cách gọi trình kiểm tra cần được xem xét như thay đổi cơ chế bảo vệ. Cấm sửa trình kiểm tra hoặc tạo lại manifest chỉ để kết quả chuyển sang đạt. Khi có phê duyệt cập nhật đường chuẩn, đối chiếu từng khác biệt với ADR đã duyệt và lưu các phiên bản cũ, mới trong lịch sử xem xét.

## Xác minh đường chuẩn

Từ thư mục chứa `pyproject.toml`, chạy bằng Python 3.11 trở lên.

```powershell
python spec/governance/verify_originals.py
```

[Manifest](originals.sha256.json) dùng SHA-256 trên byte gốc của tất cả tệp trong hai thư mục. Trình kiểm tra đối chiếu SHA-256 của manifest với giá trị đã ghim, rồi kiểm tra tập đường dẫn và hash từng tệp. Mã thoát 0 biểu thị khớp, mã 1 biểu thị sai lệch và mã 2 biểu thị lỗi đọc, manifest không hợp lệ hoặc cách gọi sai. Sau mỗi thay đổi đặc tả, chạy kiểm tra và giữ kết quả quan sát.

Khi duyệt một thay đổi, dùng bản trình kiểm tra và manifest từ bản phát hành hoặc mốc Git tin cậy để xác minh cây đang duyệt. Giữ hai tệp cạnh nhau rồi truyền đường dẫn tuyệt đối hay tương đối tới cây đang duyệt. So sánh cả trình kiểm tra, manifest và cách gọi với mốc đã duyệt để phát hiện trường hợp cùng bị sửa.

```powershell
python <thu-muc-tin-cay>/verify_originals.py --root <thu-muc-Ratatoss-can-kiem-tra>
```

Hash bao gồm LF, CRLF, BOM và dòng cuối. Dùng bản sao nhị phân khi chuyển tệp. Với Git, thiết lập thuộc tính `-text` hữu hiệu cho `docs/**`, `plan/**`, `spec/governance/originals.sha256.json` và `spec/governance/verify_originals.py` trước khi đưa chúng vào index lần đầu. Quy định thuộc tính ở gốc kho khi chủ dự án duyệt hoặc dùng `.git/info/attributes` ở từng bản sao theo đường dẫn tính từ gốc kho. Kiểm tra `git check-attr text -- <đường-dẫn-tệp>` trả `unset` và chạy trình kiểm tra sau checkout. Nếu blob Git đã qua chuẩn hóa, khôi phục byte gốc từ hiện vật tin cậy trước khi dùng làm chứng cứ.
