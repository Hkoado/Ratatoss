# Phiếu chạy lab thật A/B/C/D · Issue #60

#60 · R1.4 · `integration`. Phiếu bổ sung cho [hồ sơ lab](README.md), theo [sơ đồ và thứ tự chạy Huy chốt](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224072188). Căn cứ [Brief §8 giai đoạn 1](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-1--mvp-phân-phối-và-phục-hồi), [ánh xạ R1.4/R2.1](../../../spec/governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog) và [quy tắc lưu bằng chứng](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng).

## Xác nhận đầu mút

| Máy | Vai trò trong phiên | OS/build và đầu mối đã biết | Quyền, lịch và đầu vào còn thiếu |
| --- | --- | --- | --- |
| A | Windows ở mạng ngoài, TX sang B | Chờ xác nhận máy và người trực | `blocked` · OS/build, kiến trúc, cách chạy đã cấp quyền, tuyến WAN hoặc relay, giờ chạy UTC+7 |
| B | Windows cùng LAN với C, RX từ A và TX sang C | Chờ Bảo xác nhận máy của mình là A hay B | `blocked` · Máy B riêng với C, OS/build, kiến trúc, quyền chạy và quan sát socket/bộ đếm, giờ chạy UTC+7 |
| C | Mac cùng LAN với B, RX từ B rồi TX về B | Huy · macOS 27.0.1 (26A434), arm64, theo bình luận của Huy | `blocked` · Xác nhận B/C cùng LAN, khung giờ UTC+7, pin và vị trí fixture trên máy C trước khi chạy |
| D | Đích còn lại của demo #11 | Chờ xác nhận máy và người trực | `blocked` · OS/build, kiến trúc, quyền cài/chạy và giờ chạy UTC+7 |

Máy Windows dùng để chuẩn bị hồ sơ báo Windows 11 Pro 23H2, build 22631.6199, x64 theo registry và kiến trúc hệ điều hành. Vai trò A/B của máy này đang chờ xác nhận trên [issue #60](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224172107).

## Đầu vào đã kiểm ngày 2026-11-28 (UTC+7)

Trên Windows, tại cây xuất phát từ `98edb713a18145d72a799a876ea4374d5476ca4a`, dùng Python 3.14.2 chạy `python scripts/make_croc_lab_fixtures.py <thư-mục-mới>`. Đọc lại độ dài và SHA-256 từ tệp bằng `Path.stat()` và `hashlib.file_digest()`. Cả sáu fixture ở 32/64/128 MiB khớp [bảng byte và SHA-256 của #3](../../../spec/operations/croc-lab.md#fixture-tổng-hợp-tái-tạo-được). Bản cục bộ ở `build/issue-60-inputs/fixture/` của workspace chuẩn bị. Người trực A/B/C có thể tái tạo trong thư mục thử riêng rồi ghi vị trí đã được cấp quyền dưới bí danh của mỗi máy.

Đã tải hai gói chính thức, tính SHA-256 archive bằng `Get-FileHash -Algorithm SHA256`, đối chiếu trường `digest` trong metadata phát hành rồi giải nén và tính SHA-256 executable. Đã chạy `croc.exe --version` trên Windows và nhận `croc version 11.6.5`. Bản Mac được kiểm đến bước giải nén trên máy chuẩn bị. Huy sẽ kiểm `croc --version` và SHA-256 trên chính Mac C. [Metadata Croc v11.6.5](https://api.github.com/repos/schollz/croc/releases/tags/v11.6.5)

| Nền tảng | Gói chính thức | SHA-256 archive khớp upstream | SHA-256 executable đã giải nén |
| --- | --- | --- | --- |
| Windows x64 | `croc_v11.6.5_Windows-64bit.zip` | `ae5b9d249099ff159f6a4b91824a2bf7d2b32f0dd77342aef51b34154aa4fffb` | `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e` |
| macOS arm64 | `croc_v11.6.5_macOS-ARM64.tar.gz` | `b6a6da6c6a21bd5a3723003295cf232da281d3767687f5731725c6c4360e1015` | `56d4c1845f2638217c6e8fe2464e3db19db518a0772b570aafbef61af0125a54b` |

## Trình tự tại lab

1. Chốt B/C là hai máy riêng trên LAN dự kiến, người trực, quyền và lịch. Sau khi có quyền, kiểm lại executable và fixture trên đúng máy chạy. Trên Windows dùng `Get-Item -LiteralPath $fixture` và `Get-FileHash -Algorithm SHA256 -LiteralPath $croc,$fixture`. Trên Mac dùng `stat -f '%z' "$fixture"` và `shasum -a 256 "$croc" "$fixture"`. Ghi phiên bản từ đúng executable trên từng máy.
2. Trước khi truyền, ghi thời điểm UTC+7, commit, interface, topology theo bí danh, relay được phép và cổng, tải nền, cỡ fixture, số lượt, slot RX/TX, timeout, cấu hình nén/đa luồng/giới hạn tốc độ và cờ Croc đã lược bí mật. Mở staging riêng từng vai trò. Dùng mã phiên riêng trong môi trường của từng child theo [runbook adapter](../../../spec/operations/croc-adapter-runbook.md#hợp-đồng-child-process).
3. **Đề xuất** bắt đầu với 32 MiB như diễn tập của Huy. Khóa cùng cỡ cho cả hai chiều và hai luồng của ca đồng thời. Mở RX trước TX theo thứ tự đã chốt. Áp dụng cấu hình đã thống nhất cho lab, đối chiếu [cấu hình Docker](https://github.com/Hkoado/Ratatoss/pull/68) khi chọn observer.

| Thứ tự | Ca | Fixture nguồn nếu dùng 32 MiB | Kiểm tại đích | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | B→C | `b-to-c-32mib.bin` | C ghi byte và SHA-256 | `blocked` · Chờ B/C, quyền và lịch |
| 2 | C→B | `b-to-c-32mib.bin` đã xác minh hoặc tái tạo trên C | B ghi byte và SHA-256 | `blocked` · Chờ B/C, quyền và lịch |
| 3 | A→B đồng thời B→C | `a-32mib.bin` trên A và `b-to-c-32mib.bin` trên B | B và C kiểm riêng từng tệp | `blocked` · Chờ A/B/C, quyền, lịch và tuyến WAN/relay |

Tại B, kiểm observer trên chính profile lab trước khi dùng. Ghi socket dữ liệu theo PID và phiên, interface và bộ đếm relay gắn được với từng luồng. `netstat -ano -p tcp` trên Windows hoặc `lsof -nP -a -p "$croc_pid" -iTCP` trên Mac cho ảnh chụp socket tại thời điểm quan sát. Lọc theo PID Croc và thay địa chỉ bằng bí danh trước khi lưu. Đối chiếu socket với bộ đếm và đường payload để ghi `direct`, `relay` hoặc `unknown` theo [hồ sơ lab](README.md#phiên-đo-bc).

Trong ca 3, B ghi `rx_first`, `rx_last`, `tx_first`, `tx_last` của payload trên cùng đồng hồ monotonic và đối chiếu byte quan sát với fixture ở cả hai đích. Ghi phương pháp, đơn vị và độ phân giải của observer. Chỉ tính overlap khi đủ bốn mốc tin cậy. Với profile direct, xác minh cách nhận diện frame theo cấu hình thực tế trước khi chấp nhận mốc. Tổng byte giao diện và thời lượng tiến trình chỉ cung cấp bối cảnh. Khi chưa xác minh observer, để trống các chỉ số cần mốc payload và ghi lý do. [Quy tắc thu thập](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) · [Hồ sơ lab](README.md#phiên-đo-bc)

## Biên bản và bàn giao

Với mỗi lần thử, lưu mã run, ca, thời gian, profile đã khóa, trạng thái, mã thoát và kết quả dọn phiên. Với từng luồng, lưu hash/byte tại đích, socket/interface/relay theo bí danh, mốc tại B và lý do thiếu số đo. Lưu dưới `bench/artifacts/r14-preflight/` và liên kết từ #60. Giữ nguyên số đo trống cho ca chưa chạy. Chia sẻ thông tin truy cập qua kênh riêng và loại token, mã Croc, mật khẩu và dữ liệu người dùng khỏi hiện vật.

| Bên nhận | Đầu vào bàn giao sau phiên |
| --- | --- |
| [#9](https://github.com/Hkoado/Ratatoss/issues/9) | Máy smoke và quyền/lịch đã xác nhận, vị trí fixture, pin Croc, profile và relay. Điều kiện readiness theo [#69](https://github.com/Hkoado/Ratatoss/issues/69). |
| [#11](https://github.com/Hkoado/Ratatoss/issues/11) | Hồ sơ đầu mút A/B/C/D và bằng chứng B↔C cho ca `r14 same-installer-abcd`. |
| [#12](https://github.com/Hkoado/Ratatoss/issues/12) | Fixture, topology/relay đã quan sát, digest theo nền tảng và profile RX/TX. Dùng ngân sách transport từ [#6](https://github.com/Hkoado/Ratatoss/issues/6). |

Phiên lab thật và số đo B↔C đang **bị chặn** ở đầu vào A/B/C, quyền và lịch máy. Bằng chứng chạy thử Docker nằm ở [PR #68](https://github.com/Hkoado/Ratatoss/pull/68).
