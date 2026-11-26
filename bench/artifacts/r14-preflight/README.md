# Hồ sơ chuẩn bị lab A/B/C/D · Issue #60

Ngày kiểm fixture 2026-11-26 (UTC+07:00), trên Windows, theo hồ sơ tại `49a225c`. Đã xác minh sáu fixture tại workspace. Phiên đo B↔C trên hai máy thật đang bị chặn vì chưa có xác nhận đầu mút, quyền truy cập và lịch máy. [Issue #60](https://github.com/Hkoado/Ratatoss/issues/60) · [Runbook thử nghiệm](../../../docs/experiments.md)

## Kiểm kê đầu mút

Vai trò dưới đây theo kịch bản demo. Chốt định danh lab, hệ điều hành, quyền và lịch với người phụ trách từng máy trước phiên đo.

| Node | Vai trò dự kiến | Định danh lab / OS và build | Quyền / lịch (kèm múi giờ) | Trạng thái và lý do |
| --- | --- | --- | --- | --- |
| A | Nguồn fixture, TX sang B để tạo tải đồng thời | | | Bị chặn, chưa xác nhận máy nguồn và quyền chạy TX |
| B | Đích, nhận từ A và chuyển tiếp sang C, TX/RX trong phép đo B↔C | | | Bị chặn, chưa xác nhận máy, quyền TX/RX và kết nối LAN với C |
| C | Đích nhánh chuyển tiếp, RX/TX trong phép đo B↔C | | | Bị chặn, chưa xác nhận máy riêng, quyền TX/RX và kết nối LAN với B |
| D | Đích còn lại của demo | | | Bị chặn, chưa xác nhận máy đích và quyền cài/chạy gói |

Vị trí chạy controller xác định theo cấu hình demo #11. Xác nhận riêng quyền dùng relay và quyền xem số đếm mạng với người quản lý lab. Ghi vị trí truy cập fixture tại mỗi đầu mút khi cấp phát xong.

## Fixture đã đối chiếu

Đã đọc kích thước bằng `Get-Item` và tính SHA-256 bằng `Get-FileHash -Algorithm SHA256` trên từng file trong `fixture/` của workspace cục bộ. Sáu cặp kích thước và digest khớp [manifest #3](../../../spec/operations/croc-lab.md#fixture-tổng-hợp-tái-tạo-được). Thư mục này chứa file chưa theo dõi trong Git. Trên từng máy được cấp quyền, tạo lại bằng [script fixture](../../../scripts/make_croc_lab_fixtures.py) hoặc dùng bản sao đã cấp phát, rồi kiểm lại kích thước và hash trên máy đó.

| File | Byte | SHA-256 |
| --- | ---: | --- |
| `fixture/a-32mib.bin` | 33554432 | `25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a` |
| `fixture/a-64mib.bin` | 67108864 | `545a0e718c1a1584c397c853018a16581a31cd66377209041f0984778a4a6a67` |
| `fixture/a-128mib.bin` | 134217728 | `cdf2287f633d6558a33bcdbbfd6428708c8f869b3fc4ffb3cca88366703a353c` |
| `fixture/b-to-c-32mib.bin` | 33554432 | `7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679` |
| `fixture/b-to-c-64mib.bin` | 67108864 | `69befdfa85c9f9d3283797ebe5869630fd52bd685afa52f651246357930d6c84` |
| `fixture/b-to-c-128mib.bin` | 134217728 | `f9205ac9406aed59a117658ac37648e3c85a49a9b2a37a2a349a55101750b5f8` |

## Phiên đo B↔C

[Hồ sơ #40](../r02-preflight/README.md) dùng các tiến trình A/B/C trên một máy Windows qua IPv4 loopback. Dùng hồ sơ đó để tra pin và cách kiểm fixture. Phiên #60 cần bằng chứng mới từ LAN của lab.

1. Xác nhận B và C là hai máy riêng trong LAN dự kiến. Ghi topology đã lược bí mật, vai trò relay, interface và quy tắc tuyến áp dụng. Trên B/C và máy relay được sử dụng, lưu OS/build, kết quả `croc --version` và SHA-256 của executable thực tế. Ghi commit, thời điểm kèm múi giờ, cỡ fixture, số lượt, slot RX/TX và tải nền.
2. Chạy riêng B→C và C→B với cùng cỡ fixture, dùng thư mục nhận riêng. Sau đó chạy A→B đồng thời B→C bằng hai fixture độc lập cùng cỡ. Ghi mốc payload RX và TX trên cùng đồng hồ monotonic ở B để đo phần giao. So kích thước và SHA-256 ở hai đầu mỗi lần thử, ghi lỗi hoặc timeout và kết quả dọn phiên.
3. Trong từng khoảng chạy, đối chiếu peer trên socket, số byte tăng ở interface liên quan và số byte tăng ở relay. Ghi `direct`, `relay` hoặc `unknown` theo dấu hiệu quan sát được. Nếu thiếu dữ liệu phân loại, ghi lý do. Lưu lệnh đã lược bí mật, mốc, cấu hình và log chọn lọc cùng hiện vật, theo [quy tắc thu thập bằng chứng](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng).

| Ca | Trạng thái | Loại đường | Byte nhận / SHA-256 | Thời gian / overlap | Bằng chứng hoặc lý do |
| --- | --- | --- | --- | --- | --- |
| B→C riêng | `blocked` | | | | Chưa xác nhận B/C, quyền và lịch lab |
| C→B riêng | `blocked` | | | | Chưa xác nhận B/C, quyền và lịch lab |
| A→B đồng thời B→C | `blocked` | | | | Chưa xác nhận A/B/C, quyền và lịch lab |

## Bàn giao

| Bên nhận | Có thể dùng ngay | Còn thiếu |
| --- | --- | --- |
| [#9 · Smoke tích hợp](https://github.com/Hkoado/Ratatoss/issues/9) | Fixture xác minh và kiểm kê theo vai trò | OS/build, quyền và lịch cài/chạy trên từng máy, vị trí fixture trên các máy thử |
| [#11 · Demo bốn Node](https://github.com/Hkoado/Ratatoss/issues/11) | Kịch bản đo B↔C và fixture độc lập để chạy đồng thời | Hồ sơ đầu mút đã xác nhận, hiện vật B↔C, và ứng viên tích hợp từ #9/#10 để chạy `r14 same-installer-abcd` |
| [#12 · Đối chứng](https://github.com/Hkoado/Ratatoss/issues/12) | Digest fixture và danh sách cấu hình cần ghi | Topology, relay, pin Croc, slot RX/TX và bằng chứng đo thực tế để #12 khóa cấu hình. Ngân sách transport lấy từ [#6](https://github.com/Hkoado/Ratatoss/issues/6). [Checklist #43](../../../spec/operations/r22-run-checklist.md) |
