# Phiếu chạy lab thật A/B/C/D · Issue #60

#60 · R1.4 · `integration`. Chủ dự án chốt dùng hai đầu Croc B/C trên máy Huy cho preflight #60. Phiếu dùng thứ tự thử của Huy và bố trí bốn vai trò trên ba máy vật lý. [Quyết định #60](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224307861) · [Kế hoạch của Huy](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224072188) · [Brief §8 giai đoạn 1](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-1--mvp-phân-phối-và-phục-hồi) · [Ánh xạ R1.4/R2.1](../../../spec/governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog)

## Xác nhận đầu mút

| Node | Vai trò trong phiên | Máy vật lý và đầu mối | Điều kiện còn thiếu |
| --- | --- | --- | --- |
| A | TX từ máy Khoa sang B | Khoa · Windows 11 Pro 23H2 (22631.6199), x64, đề xuất dùng cho A | Tuyến giữa A và B, relay nếu dùng, lịch chung UTC+7 |
| B | RX từ A, TX sang C, thu mốc payload | Huy · Mac arm64, macOS 27.0.1 (26A434) | Xác nhận profile và observer cho phiên có A, lịch chung UTC+7 |
| C | RX từ B hoặc TX chiều ngược | Cùng Mac của Huy, thư mục và phiên Croc riêng | Xác nhận profile cho phiên có A và pin tương ứng với môi trường chạy |
| D | Đích của ca bốn Node khi cần | Bảo · máy riêng, đề xuất dùng cho D | Xác nhận OS/build, kiến trúc, quyền cài/chạy và giờ UTC+7 cho ca có D |

OS/build của Mac do Huy cung cấp. Build Windows và kiến trúc hệ điều hành đã được kiểm từ registry và API của máy chuẩn bị. B/C dùng chung Mac nên ghi topology `same-host` kèm loopback hoặc bridge quan sát được, và loại đường Croc theo từng phiên.

## Đầu vào đã kiểm ngày 2026-11-28 (UTC+7)

Trên Windows, tại cây xuất phát từ `98edb713a18145d72a799a876ea4374d5476ca4a`, dùng Python 3.14.2 chạy `python scripts/make_croc_lab_fixtures.py <thư-mục-mới>`. Đọc lại độ dài và SHA-256 từ tệp bằng `Path.stat()` và `hashlib.file_digest()`. Cả sáu fixture ở 32/64/128 MiB khớp [bảng byte và SHA-256 của #3](../../../spec/operations/croc-lab.md#fixture-tổng-hợp-tái-tạo-được). Bản cục bộ ở `build/issue-60-inputs/fixture/` của workspace chuẩn bị. Người trực A/B/C có thể tái tạo trong thư mục thử riêng rồi ghi vị trí đã được cấp quyền dưới bí danh của mỗi máy.

Đã tải hai gói chính thức, tính SHA-256 archive bằng `Get-FileHash -Algorithm SHA256`, đối chiếu trường `digest` trong metadata phát hành rồi giải nén và tính SHA-256 executable. Đã chạy `croc.exe --version` trên Windows và nhận `croc version 11.6.5`. Bản macOS được kiểm đến bước giải nén trên máy chuẩn bị. Nếu Huy chạy native trên Mac, kiểm lại bản macOS tại máy. Nếu chạy trong container, ghi pin executable Linux của container. [Metadata Croc v11.6.5](https://api.github.com/repos/schollz/croc/releases/tags/v11.6.5)

| Nền tảng | Gói chính thức | SHA-256 archive khớp upstream | SHA-256 executable đã giải nén |
| --- | --- | --- | --- |
| Windows x64 | `croc_v11.6.5_Windows-64bit.zip` | `ae5b9d249099ff159f6a4b91824a2bf7d2b32f0dd77342aef51b34154aa4fffb` | `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e` |
| macOS arm64 | `croc_v11.6.5_macOS-ARM64.tar.gz` | `b6a6da6c6a21bd5a3723003295cf232da281d3767687f5731725c6c4360e1015` | `56d4c1845f2638217c6e8fe2464e3db19db518a0772b570aafbef61af0125a54b` |

## Kết quả Croc đã có

- **Mac của Huy, Docker internal bridge, relay.** Hai lượt B→C và C→B đều nhận đúng 33.554.432 byte và SHA-256. Ca có ba đầu A/B/C cùng Mac ghi overlap payload tại B là 2.993.906.501 ns và hash đúng ở B/C. Runner dùng Croc Linux arm64 v11.6.5. Hiện vật ghi digest executable, cổng relay, giới hạn upload, cấu hình luồng và bốn mốc tại B. [Hiện vật PR #68](https://github.com/Hkoado/Ratatoss/blob/00c939181a370d7d299c785a3eba0f918c032e0d/bench/artifacts/r14-preflight/docker-rehearsal.json)
- **Windows của Khoa, loopback IPv4, relay.** Ngày 2026-11-28 (UTC+7), chạy `python -m scripts.croc_r02_preflight --croc <croc.exe> --fixtures <fixture> --output <thư-mục-mới>` bằng Python 3.14.2 với pin Windows ở trên. A→B và B→C đều nhận đúng 33.554.432 byte và SHA-256. Child TX/RX thoát mã 0 và đã dọn đủ tiến trình. Lần chạy chỉ thu mốc vòng đời tiến trình. [Kết quả](windows-loopback/report.json) · [Profile mạng](windows-loopback/network.json) · [Cấu hình Croc](windows-loopback/profile.json) · [Relay](windows-loopback/relay.json)

## Trình tự tại lab

1. Huy dùng lại hai ca B↔C nếu giữ profile Docker trên Mac như PR #68. Nếu đổi profile, chạy lại hai chiều trước khi ghép A. Kiểm lại executable và fixture trên đúng môi trường chạy. Trên Windows dùng `Get-Item -LiteralPath $fixture` và `Get-FileHash -Algorithm SHA256 -LiteralPath $croc,$fixture`. Trên Mac dùng `stat -f '%z' "$fixture"` và `shasum -a 256 "$croc" "$fixture"`. Ghi phiên bản từ đúng executable.
2. Chốt đường A→B và relay nếu dùng, cùng giờ UTC+7. Ghi thời điểm, commit, interface, topology theo bí danh, relay được phép và cổng, tải nền, cỡ fixture, số lượt, slot RX/TX, timeout, cấu hình nén/đa luồng/giới hạn tốc độ và cờ Croc đã lược bí mật. Tách staging và `CROC_CONFIG_DIR` theo vai trò. Dùng mã phiên riêng trong môi trường của từng child theo [runbook adapter](../../../spec/operations/croc-adapter-runbook.md#hợp-đồng-child-process).
3. **Đề xuất** giữ 32 MiB cho phiên chung như ca đã chạy trên Mac. Mở RX trước TX theo thứ tự đã chốt, dùng hai fixture độc lập cùng cỡ. Nếu B/C ở Docker internal bridge trong phiên có A, xác nhận cách B truy cập tuyến hoặc relay của A và kiểm observer trên cả hai luồng trước khi đo.

| Thứ tự | Ca | Fixture nguồn nếu dùng 32 MiB | Kiểm tại đích | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | B→C trên Mac | `b-to-c-32mib.bin` | C ghi byte và SHA-256 | `pass` · Docker bridge qua relay, PR #68 |
| 2 | C→B trên Mac | `b-to-c-32mib.bin` đã xác minh hoặc tái tạo trên C | B ghi byte và SHA-256 | `pass` · Docker bridge qua relay, PR #68 |
| 3 | A từ Windows → B đồng thời B→C trên Mac | `a-32mib.bin` trên A và `b-to-c-32mib.bin` trên B | B và C kiểm riêng từng tệp | `blocked` · Chờ lịch chung và tuyến giữa hai máy |

Tại B, kiểm observer trên chính profile lab trước khi dùng. Ghi socket dữ liệu theo PID và phiên, interface và bộ đếm relay gắn được với từng luồng. `netstat -ano -p tcp` trên Windows hoặc `lsof -nP -a -p "$croc_pid" -iTCP` trên Mac cho ảnh chụp socket tại thời điểm quan sát. Lọc theo PID Croc và thay địa chỉ bằng bí danh trước khi lưu. Đối chiếu socket với bộ đếm và đường payload để ghi `direct`, `relay` hoặc `unknown` theo [hồ sơ lab](README.md#phiên-đo-bc).

Trong ca 3, B ghi `rx_first`, `rx_last`, `tx_first`, `tx_last` của payload trên cùng đồng hồ monotonic và đối chiếu byte quan sát với fixture ở cả hai đích. Ghi phương pháp, đơn vị và độ phân giải của observer. Chỉ tính overlap khi đủ bốn mốc tin cậy. Với profile direct, xác minh cách nhận diện frame theo cấu hình thực tế trước khi chấp nhận mốc. Tổng byte giao diện và thời lượng tiến trình chỉ cung cấp bối cảnh. Khi chưa xác minh observer, để trống các chỉ số cần mốc payload và ghi lý do. [Quy tắc thu thập](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) · [Hồ sơ lab](README.md#phiên-đo-bc)

## Biên bản và bàn giao

Với mỗi lần thử, lưu mã run, ca, thời gian, profile đã khóa, trạng thái, mã thoát và kết quả dọn phiên. Với từng luồng, lưu hash/byte tại đích, socket/interface/relay theo bí danh, mốc tại B và lý do thiếu số đo. Lưu dưới `bench/artifacts/r14-preflight/` và liên kết từ #60. Giữ nguyên số đo trống cho ca chưa chạy. Chia sẻ thông tin truy cập qua kênh riêng và loại token, mã Croc, mật khẩu và dữ liệu người dùng khỏi hiện vật.

| Bên nhận | Đầu vào bàn giao sau phiên |
| --- | --- |
| [#9](https://github.com/Hkoado/Ratatoss/issues/9) | Máy smoke và quyền/lịch đã xác nhận, vị trí fixture, pin Croc, profile và relay. Điều kiện readiness theo [#69](https://github.com/Hkoado/Ratatoss/issues/69). |
| [#11](https://github.com/Hkoado/Ratatoss/issues/11) | Hồ sơ đầu mút A/B/C/D và bằng chứng B↔C cho ca `r14 same-installer-abcd`. |
| [#12](https://github.com/Hkoado/Ratatoss/issues/12) | Fixture, topology/relay đã quan sát, digest theo nền tảng và profile RX/TX. Dùng ngân sách transport từ [#6](https://github.com/Hkoado/Ratatoss/issues/6). |

Đã có bằng chứng B↔C cùng Mac. Ca ghép A qua tuyến giữa hai máy và ca bốn Node có D vẫn đang chờ điều phối. Khi bàn giao, ghi rõ số máy vật lý và topology tương ứng với từng kết quả. [Quy tắc lưu bằng chứng](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)
