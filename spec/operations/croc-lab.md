# Hồ sơ lab Croc · Issue #3

Issue #3 · LAB, đầu vào tuyến `transport` · Đối chiếu [Brief §8 giai đoạn 0](../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-0--kiểm-chứng-croc), [kế hoạch cổng 0](../../plan/ASTRA_PLAN.md), [backlog R0.1–R0.2](../../plan/BACKLOG.md), [runbook thử nghiệm §Cổng 0](../../docs/experiments.md#cổng-0--transport) và [runbook adapter](croc-adapter-runbook.md). Phạm vi thay đổi gồm hồ sơ này và [script tạo fixture](../../scripts/make_croc_lab_fixtures.py).

## Binary đã kiểm chứng

| Thuộc tính | Giá trị |
| --- | --- |
| Hệ điều hành thử | Windows 11 Pro x64, build 22631 |
| Asset | `croc_v11.6.5_Windows-64bit.zip` |
| SHA-256 archive từ metadata phát hành | `ae5b9d249099ff159f6a4b91824a2bf7d2b32f0dd77342aef51b34154aa4fffb` |
| SHA-256 archive tải về | `ae5b9d249099ff159f6a4b91824a2bf7d2b32f0dd77342aef51b34154aa4fffb` |
| SHA-256 executable giải nén, tự đo | `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e` |
| Kết quả `--version` | `croc version 11.6.5` |

Lấy digest archive từ trường `digest` của đúng asset trong API phát hành upstream. Dùng `Get-FileHash -Algorithm SHA256 -LiteralPath <zip>` để so trước khi giải nén và chạy. Sau khi giải nén, dùng cùng lệnh trên `croc.exe` và đối chiếu lại tại mỗi đầu. Smoke kiểm lại SHA-256 executable trước khi chạy và dùng đường dẫn tuyệt đối đến cùng executable cho cả ba tiến trình. [Release v11.6.5](https://github.com/schollz/croc/releases/tag/v11.6.5) · [Metadata release](https://api.github.com/repos/schollz/croc/releases/tags/v11.6.5) · [Asset Windows x64](https://github.com/schollz/croc/releases/download/v11.6.5/croc_v11.6.5_Windows-64bit.zip)

## Fixture tổng hợp tái tạo được

Script dùng thư viện chuẩn Python 3.11+. Đối số là thư mục mới có thư mục cha đã tồn tại. Chạy lệnh bên dưới sau khi vào thư mục chứa mã dự án và thay đường dẫn thư mục cha nếu ổ mặc định thiếu chỗ. Dành ít nhất 448 MiB trên ổ của thư mục đích cho mỗi bộ. Chọn hai thư mục riêng ngoài repo nếu kiểm tra tái tạo. Mỗi khối 1 MiB lấy từ SHAKE-256 của seed ASCII gồm định danh bộ, tên file và chỉ số khối từ 0. Tên khác cho ba fixture B→C tạo dữ liệu độc lập với ba fixture của A ở cùng cỡ.

```powershell
$fixtureParent = [IO.Path]::GetTempPath()
$fixtures = Join-Path $fixtureParent ("croc-fixtures-" + [guid]::NewGuid().ToString("N"))
python scripts/make_croc_lab_fixtures.py $fixtures
```

Hai lần tạo thực tế bằng Python 3.14.2 trên Windows x64 cho kết quả giống nhau. Sau mỗi lần, kích thước được đối chiếu bằng `Get-Item -LiteralPath <file>` và SHA-256 trên file đã ghi bằng `Get-FileHash -Algorithm SHA256 -LiteralPath <file>`.

| Nguồn | Tệp | Byte | SHA-256 |
| --- | --- | ---: | --- |
| A | `a-32mib.bin` | 33 554 432 | `25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a` |
| A | `a-64mib.bin` | 67 108 864 | `545a0e718c1a1584c397c853018a16581a31cd66377209041f0984778a4a6a67` |
| A | `a-128mib.bin` | 134 217 728 | `cdf2287f633d6558a33bcdbbfd6428708c8f869b3fc4ffb3cca88366703a353c` |
| B | `b-to-c-32mib.bin` | 33 554 432 | `7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679` |
| B | `b-to-c-64mib.bin` | 67 108 864 | `69befdfa85c9f9d3283797ebe5869630fd52bd685afa52f651246357930d6c84` |
| B | `b-to-c-128mib.bin` | 134 217 728 | `f9205ac9406aed59a117658ac37648e3c85a49a9b2a37a2a349a55101750b5f8` |

## Smoke chuẩn bị Windows

Kết quả quan sát ngày 2026-11-21 trên cây xuất phát từ `e71faab`. A (TX), B (RX) và relay là ba tiến trình riêng trên cùng một máy. Profile `lab-windows-loopback` dùng TCP IPv4 loopback. Cả hai đầu chỉ chạy với dữ liệu tổng hợp.

- Executable đã trả mã 0 cho `--version`, `--help`, `send --help` và `relay --help` trong môi trường chỉ có `SystemRoot`. Help xác nhận có các cờ dùng bên dưới. [Nguồn CLI tại tag](https://github.com/schollz/croc/blob/v11.6.5/src/cli/cli.go)
- Smoke dùng argv dạng mảng, `shell=False`, `CREATE_NO_WINDOW`, stdin/stdout/stderr đến `DEVNULL` cho các tiến trình truyền và relay. Mỗi tiến trình có cwd, `CROC_CONFIG_DIR`, `TMP` và `TEMP` riêng. Mật khẩu ngẫu nhiên `CROC_PASS` nằm trong môi trường riêng của ba child. Mã dùng một lần `CROC_SECRET` chỉ nằm trong môi trường riêng của TX/RX. [Nguồn thư mục cấu hình tại tag](https://github.com/schollz/croc/blob/v11.6.5/src/utils/utils.go#L64-L85)
- Relay bind `127.0.0.1`. `netstat -ano -p TCP` xác nhận PID relay chỉ có hai TCP listener `127.0.0.1:19009` và `127.0.0.1:19010`. Kết nối TCP đến cả hai cổng thành công trước khi chạy TX/RX. [Nguồn bind relay tại tag](https://github.com/schollz/croc/blob/v11.6.5/src/tcp/tcp.go#L237-L264)
- TX bắt đầu với một bản sao `a-32mib.bin`. RX bắt đầu trong thư mục trống, được mở trước TX với khoảng chờ cấu hình 750 ms. Trên pin này, `--ip` trỏ RX thẳng vào relay loopback và bỏ qua khám phá peer, còn `send --no-local` ngăn TX mở relay riêng. `--transport relay` khóa chế độ dữ liệu của TX. [Nguồn nhận kết nối tại tag](https://github.com/schollz/croc/blob/v11.6.5/src/croc/croc.go#L2045-L2093)

Các mảng argv đã chạy dưới đây dùng ký hiệu `CROC` cho đường dẫn tuyệt đối đến executable. Khi lặp lại, chọn cổng trống, giữ địa chỉ loopback và thay nhất quán ở cả ba vai trò.

```text
Relay [CROC, "--disable-clipboard", "--no-update-check", "relay", "--host", "127.0.0.1", "--ports", "19009,19010"]
RX    [CROC, "--disable-clipboard", "--no-update-check", "--ip", "127.0.0.1:19009", "--yes"]
TX    [CROC, "--disable-clipboard", "--no-update-check", "--relay", "127.0.0.1:19009", "send", "--no-local", "--transport", "relay", "a-32mib.bin"]
```

| Quan sát | Kết quả |
| --- | --- |
| Mã thoát TX và RX | `0` và `0` |
| Thư mục RX sau khi child kết thúc | Một file `a-32mib.bin` |
| Kích thước hai đầu | 33 554 432 byte mỗi đầu |
| SHA-256 hai đầu | `25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a` |
| Dọn phiên | Ba child đã được đợi kết thúc, relay bị dừng bởi harness và staging tạm được dọn |

Đây là bằng chứng chuẩn bị đầu vào R0.1. RX dùng `--ip` trong smoke này để giới hạn kết nối ở relay loopback. R0.1 còn phải xác nhận mảng argv RX dùng `--relay` theo [runbook adapter](croc-adapter-runbook.md#hợp-đồng-child-process). Phân loại đường truyền theo telemetry là **không xác định** vì smoke chỉ ghi nhận listener và khả năng kết nối, chưa thu số đếm byte theo giao diện hoặc relay. Các ca trên máy độc lập, B→C, D, LAN/WAN, TX mở trước, timeout, Windows Job Object, cách ly file dở, kiểm clipboard và benchmark đủ số lần đều **chưa chạy**. Trạng thái cổng 0 **chưa nghiệm thu**.

## Bàn giao môi trường

- A và B đã truyền thật ở profile `lab-windows-loopback` dưới dạng hai tiến trình cùng máy. C và D cùng các profile LAN/WAN còn chờ môi trường nhiều máy. Chạy lại smoke bằng binary khóa SHA-256 và fixture tái tạo khi đổi máy.
- Bằng chứng đã lược bí mật của smoke nằm trong hồ sơ này. Khi chạy R0.1–R0.2, lưu cấu hình đã lược bí mật, mốc, log chọn lọc và bản CSV dưới thư mục `bench/artifacts/<run-id>/` của bản sao làm việc hoặc trong kho hiện vật nội bộ, rồi dẫn vị trí từ issue. Chỉ công bố hiện vật được phép. [Quy tắc lưu bằng chứng](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)
- Ở lab nhiều máy, chốt cấu hình và đo riêng LAN B↔C trước khi chạy demo. Đối chiếu peer trên socket, phần tăng bộ đếm byte của interface và phần tăng bộ đếm của relay trong cùng khoảng chạy để phân biệt đường trực tiếp và relay. Ghi **không xác định** khi thiếu dấu hiệu cần thiết. Dùng cùng đồng hồ monotonic ở B để chứng minh overlap. [Runbook cổng 0](../../docs/experiments.md#cổng-0--transport)
