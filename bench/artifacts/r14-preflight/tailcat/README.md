# Profile Tailcat direct qua IPv6 · Issue #60

Profile này ghi các lượt A→B dùng Tailcat của Croc v11.6.5 ngày 28/11/2026 (UTC+7), tách khỏi profile relay ở [hồ sơ preflight](../README.md). Tailcat là mạng WireGuard userspace trong Croc. Dữ liệu đi qua DERP của Tailscale trước, rồi chuyển sang UDP trực tiếp khi hai đầu xuyên NAT được. `--transport derp` ở bên gửi tắt fallback sang relay dữ liệu của Croc. [Croc v11.6.5 · Data transport selection](https://github.com/schollz/croc/blob/v11.6.5/README.md#data-transport-selection) · [Issue #60](https://github.com/Hkoado/Ratatoss/issues/60)

## Các lượt A→B

Mốc và goodput đo theo đồng hồ B. Byte và SHA-256 kiểm tại đích.

| Lượt | Mạng A | Đường payload | Goodput A→B | Đích | Bằng chứng |
| --- | --- | --- | --- | --- | --- |
| 01:14 · chỉ A→B | Chưa có IPv6 | `derp` suốt lượt | 0,67–0,69 MiB/s | 32 MiB, SHA-256 khớp | [Kết quả](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7225308766) |
| 01:38 · chỉ A→B | Có IPv6 | `direct`, UDP/IPv6 | 2,43–2,65 MiB/s | 32 MiB, SHA-256 khớp | [Kết quả](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7225722367) · [Đối chiếu A](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7225744627) |
| 01:55 · A→B đồng thời B→C | Có IPv6 | `direct`, UDP/IPv6 | 3,22 MiB/s | 32 MiB, SHA-256 khớp tại B và C | [Số đo](2026-11-28-0155-concurrent.json) · [Đối chiếu A](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7226038404) |
| 02:11 · A→B đồng thời B→C, A đổi vị trí Wi-Fi | Có IPv6, tín hiệu 90% | Payload vào B qua UDP/IPv6. Chiều B→A qua DERP trong 4,15 s đầu | 5,47 MiB/s | 32 MiB, SHA-256 khớp tại B và C | [Số đo](2026-11-28-0211-concurrent.json) · [Đối chiếu A](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7226303986) |

Để so sánh, lượt relay Croc lúc 00:46 đạt 1,50 MiB/s. [Số đo relay](../2026-11-28-0046-wan.json)

Điều kiện mạng của lượt 01:14:
- A chỉ có IPv4.
- Trên IPv4, B có ánh xạ NAT phụ thuộc đích.
- B có IPv6 không NAT.

Croc v11.6.5 không link `tailscale.com/feature/portmapper`, nên Tailcat không dùng UPnP hay NAT-PMP. Đường trực tiếp chỉ mở được sau khi A có IPv6.

## Ca đồng thời 01:55

B và C chạy native trên **cùng một Mac**, nên mọi mốc dùng chung `time.monotonic_ns()` của máy này.

- **A→B:** Tailcat direct. Kênh ghép là `1.getcroc.com:9009`, cố định ở hai đầu.
- **B→C:** relay Croc native trên `::1`, với `--throttleUpload 8M --no-multi`.
  - RelayTap R0.2 nghe trên `127.0.0.1` và chuyển tiếp tới relay.
  - Sender B→C chờ sẵn trong phòng. C tham gia tại `rx_first`.

| Mốc | Nguồn | Loại byte |
| --- | --- | --- |
| `rx_first` | Lần đầu `st_blocks` của tệp nhận tại B tăng, lấy mẫu 5 ms | Ghi payload đầu tiên xuống tệp |
| `rx_last` | Dòng debug `finished receiving` của Croc tại B | Mốc tầng ứng dụng sau byte payload cuối |
| `tx_first`, `tx_last` | RelayTap trên cổng dữ liệu của relay B→C | Byte payload trong khung Croc, độ phân giải ns |

Kết quả:
- **Overlap 2,995434250 s.** B→C bắt đầu sau `rx_first` 162,016 ms và kết thúc trước `rx_last` 6,776 s. Vì vậy overlap bằng khoảng payload B→C và không phụ thuộc sai số của mốc RX.
- **Goodput:** A→B 3,22 MiB/s trên 9,933 s. B→C 10,68 MiB/s trên 2,995 s.
- **Tailcat:** hai đầu báo `path=direct streams=8`. A `sent=33599488`, B `received=33599488`.

[Số đo](2026-11-28-0155-concurrent.json) · [Kết quả thô của runner](2026-11-28-0155-concurrent-result.json) · [Bộ đếm socket](2026-11-28-0155-b-rx-sockets.csv)

**Byte payload và byte tầng socket ghi riêng.** Byte payload là số byte tệp tại đích và số byte RelayTap đếm. Byte tầng socket lấy từ `nettop` mỗi 1 s, theo từng socket của receiver A→B, và gồm cả header WireGuard, UDP và IP. Ở lượt này:

| Socket | Byte vào | Byte ra |
| --- | --- | --- |
| `udp6` | 37.032.176 | 2.452.448 |
| `tcp4` (kênh ghép Croc) | 11.362 | 6.861 |
| `udp4` | 64 | 328 |

Không có socket `tcp6` (DERP) nào mang dữ liệu. Bộ đếm socket chỉ dùng để xác định họ địa chỉ của luồng dữ liệu, không dùng để tính goodput.

**Lượt lặp lại 02:11.** Lượt này dùng cùng runner và profile, sau khi A đổi vị trí Wi-Fi. A→B đạt 5,47 MiB/s trên 5,855 s, overlap 2,995239208 s, B→C bắt đầu sau `rx_first` 147,5 ms.
- **Telemetry tại B:** chuyển từ `derp` sang `direct` ở `rx_first` + 4,148 s.
- **Bộ đếm socket:** payload vào B nằm trên `udp6` suốt khoảng payload. Chiều B→A, chủ yếu ACK, đi qua DERP `tcp6` trong khoảng 4,15 s đầu.
- **Tóm tắt Tailcat:** hai đầu báo `path=direct`, với `sent` và `received` cùng bằng 33.599.488.

[Số đo](2026-11-28-0211-concurrent.json) · [Kết quả thô](2026-11-28-0211-concurrent-result.json) · [Bộ đếm socket](2026-11-28-0211-b-rx-sockets.csv)

## Sai số của mốc RX

Hiệu chuẩn bằng [`calibrate_rx_marks.py`](runner/calibrate_rx_marks.py): ba lượt B→C 32 MiB qua relay Croc một luồng trên Mac. Mỗi lượt so mốc ứng viên ở đích với mốc dây của RelayTap. [Lượt 1](calibration/run1.json) · [Lượt 2](calibration/run2.json) · [Lượt 3](calibration/run3.json)

- **`rx_first`:** trễ +1,84 đến +4,00 ms so với byte payload đầu tiên, cộng tối đa 5 ms do chu kỳ lấy mẫu.
- **`rx_last`:** trễ +0,21 đến +0,44 ms so với byte payload cuối.
- **Cách đã loại:**
  - Kích thước tệp: Croc tạo sẵn tệp đủ 32 MiB trước payload.
  - `st_blocks` đủ 32 MiB: APFS cấp block trước khoảng 2 s.
  - Dòng tiến độ >0% đầu tiên: muộn khoảng 203 ms.
- **Giới hạn:** hiệu chuẩn chạy trên relay một luồng. Độ lệch **chưa kiểm chứng trên Tailcat 8 luồng**, vì không có mốc dây để đối chiếu UDP WireGuard đã mã hóa.

## Runner

[`run-concurrent.py`](runner/run-concurrent.py) giữ nguyên byte đã chạy lúc 01:55 (SHA-256 `d20ff3f8…4a030783`).
- **Output của Croc:** đi qua bộ lọc. Bộ lọc che mã và mật khẩu, bỏ dòng chứa `--pass` hoặc `CROC_SECRET`, xóa địa chỉ IP, và chỉ giữ dòng tiến độ, mốc và lỗi.
- **Mã A→B:** đọc từ một tệp riêng rồi xóa ngay. Runner từ chối nếu mã không đủ 43 ký tự.
- **Môi trường:** cần Python 3.11 cho RelayTap. Đường dẫn executable Croc và fixture là đường dẫn trên máy B.

[`calibrate_rx_marks.py`](runner/calibrate_rx_marks.py) (SHA-256 `5840d5fe…9b08e876`) đã được chạy dưới tên `obs-validate.py`.

## Giới hạn

- Goodput A→B vẫn dưới mục tiêu 10–50+ MiB/s.
- Chưa đo băng thông WAN độc lập (link rate, latency, loss) của A và B.
- B và C dùng chung một Mac, nên B→C không phản ánh đường mạng giữa hai máy.
- Đường Tailcat phụ thuộc NAT và IPv6 của mạng từng đầu.
