# Smoke adapter Tailcat Windows · Issue #78

Ngày 28/11/2026 (UTC+7). Hai tiến trình Ratatoss trên cùng máy Windows dùng Croc v11.6.5 đã ghim và fixture tổng hợp 32 MiB. [Cách chạy smoke](../../../spec/operations/croc-adapter-runbook.md#dùng-profile-ở-adapter-windows)

| Ca | Phiên bản cây mã | Kết quả |
| --- | --- | --- |
| [Tailcat, RX mở trước](tailcat-public-rx.json) | `27ef69e`, sạch | Kênh ghép `1.getcroc.com:9009`. Hai đầu báo `path=direct`, 8 luồng. TX gửi và RX nhận cùng 33.599.488 byte Tailcat. Đích nhận 33.554.432 byte tệp và khớp SHA-256. |
| [Tailcat, TX mở trước](tailcat-public-tx.json) | `27ef69e`, sạch | Cùng cấu hình. Hai đầu báo `path=direct`, 8 luồng, cùng số byte Tailcat và SHA-256 ở đích. |
| [Relay loopback](relay-loopback.json) | `27ef69e`, sạch | Đạt 5 ca gồm hai thứ tự mở, không có peer, timeout khi nhận dở và chạy lại với attempt mới. Ca thành công khớp SHA-256. |
| [Tailcat với kênh ghép loopback](tailcat-loopback-rx.json) | `375ad58`, sạch | RX mở trước. Hai child thoát mã 1, thiếu tóm tắt Tailcat và không có tệp đích. Các lần chẩn đoán cùng cấu hình có lỗi thiết lập kết nối giữa hai peer. |

Trong smoke Tailcat, `path` là trạng thái cuối tại đầu báo. Các mốc tiến độ là quan sát tầng ứng dụng. Hồ sơ này kiểm việc chọn profile, truyền 32 MiB, đối chiếu byte và SHA-256 qua adapter Windows. Đo lại qua hai máy riêng cần bộ đếm socket theo chiều để xác nhận họ địa chỉ và đường payload. [Hồ sơ WAN hai máy qua Croc CLI ở #60](../r14-preflight/tailcat/README.md)
