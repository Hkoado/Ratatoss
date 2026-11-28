# Hồ sơ chuẩn bị smoke tích hợp R1.3 · Issue #69

Hồ sơ này tổng hợp hiện vật preflight cho [issue #69](https://github.com/Hkoado/Ratatoss/issues/69) (sub-issue của [#60](https://github.com/Hkoado/Ratatoss/issues/60), bàn giao đầu vào cho [#9](https://github.com/Hkoado/Ratatoss/issues/9) theo [ADR 0002](../../../spec/governance/adr/0002-plars-integration-order.md) và [cấu hình readiness](../../../.github/issue-readiness.json)).

## Trạng thái các phép kiểm đầu vào

| Khóa kiểm tra | Trạng thái | Hiện vật | Ghi chú / Lý do còn thiếu |
| --- | --- | --- | --- |
| `test-nodes` | `blocked` | [`test-nodes.json`](test-nodes.json) | Đã đối chiếu OS/build, kiến trúc và vị trí fixture của A/B/C/D từ `#60`. Còn chờ `@Hkoado` và người phụ trách máy chốt danh sách máy/vai trò cho ca smoke `#9`, quyền cài/chạy ứng viên và khung giờ kèm múi giờ `UTC+07:00`. |
| `integration-config` | `blocked` | [`integration-config.json`](integration-config.json) | Đã đối chiếu Croc v11.6.5 (A, B/C), 6 fixture đã xác minh SHA-256 và ngân sách tham chiếu R0.2 từ `#6`/`#60`. Còn chờ `@Hkoado` chốt vị trí controller/cổng, profile mạng/relay + cờ Croc khóa, fixture chọn dùng, giới hạn slot RX/TX và SHA-256 executable Croc tại D nếu D tham gia. |

Tệp tổng hợp trạng thái: [`readiness.json`](readiness.json).

## Dữ liệu đã đối chiếu và tái dùng từ `#6` và `#60`

- **Đầu mút A/B/C/D** (từ [hồ sơ #60](../r14-preflight/README.md) và [phiếu chạy lab](../r14-preflight/lab-session.md)):
  - **A (Khoa)**: Windows 11 Pro 23H2, build `22631.6199`, `x64` · Croc v11.6.5 SHA-256 `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e` · đủ 6/6 fixture trong `fixture/`.
  - **B và C (Huy, chung 1 Mac)**: macOS `27.0.1 (26A434)` / container Linux `7.0.14-linuxkit` (`arm64` / `aarch64`) · Croc v11.6.5 SHA-256 `56d4c1845f2638217c6e8fe2464e3db19db518a0772b570aafbe61af0125a54b` (macOS native) và `93648f374ef5dcdb9e64d78ca9729f13af3e723312db44278970695be877f2d2` (Linux arm64 container) · đủ 6/6 fixture trong cache cục bộ ngoài repo.
  - **D (Bảo)**: Windows 11 Pro 25H2, build `26200.9974`, `x64` · đã nhận và kiểm SHA-256 `a-32mib.bin` bằng Croc v11.6.5; chưa ghi SHA-256 executable Croc và quyền/lịch cài ứng viên `#9`.
- **Fixture đã xác minh SHA-256 (6/6)**: khớp [bảng hash R2.2](../r22-preflight/fixture-hashes.json) (`a-32mib.bin`, `a-64mib.bin`, `a-128mib.bin`, `b-to-c-32mib.bin`, `b-to-c-64mib.bin`, `b-to-c-128mib.bin`).
- **Ngân sách tham chiếu R0.2** (từ [batch-profiles.json](../r02/batch-profiles.json)): cỡ batch ưu tiên `64 MiB`, `min_goodput_bps = 100000000`, `lease_ms = 75000`, `adapter_timeout_ms = 75000`, `verify_commit_ms = 200`, `margin_ms = 200`.

## Các đầu mục chờ `@Hkoado` xác nhận để chuyển sang `pass`

1. **Tập máy và vai trò nguồn/đích (`test-nodes`)**: chốt những máy nào tham gia ca smoke lịch cố định của `#9` (A/B/C/D hay tập con) và vai trò từng máy.
2. **Quyền cài/chạy và lịch chạy (`test-nodes`)**: xác nhận quyền cài/chạy ứng viên tích hợp `#9` và khung giờ kèm múi giờ `UTC+07:00` cho các máy được chọn.
3. **Vị trí Controller (`integration-config`)**: máy chạy controller, địa chỉ/cổng kết nối giữa các Node, giữ UI/API cục bộ bind `127.0.0.1`.
4. **Profile mạng & Relay (`integration-config`)**: chọn profile (loopback, relay nội bộ/công cộng hay Tailcat IPv6) và khóa cờ Croc cho ca smoke; bổ sung SHA-256 executable Croc tại D nếu D tham gia.
5. **Fixture & giới hạn RX/TX (`integration-config`)**: chốt fixture dùng cho ca smoke và giới hạn slot RX/TX áp dụng.

## Thao tác kiểm tra và quy tắc lược bí mật

- Các tệp JSON trong thư mục này được chuẩn hóa xuống dòng `LF` (khai báo trong `.gitattributes`) và đối chiếu SHA-256 chữ thường bằng `hashlib.file_digest(..., "sha256")` qua hàm `report_blocker` trong [`.github/scripts/issue_readiness.py`](../../../.github/scripts/issue_readiness.py).
- Toàn bộ hiện vật đã lược token, mã Croc, mật khẩu relay (`--pass`), địa chỉ nhạy cảm và dữ liệu người dùng theo [runbook thử nghiệm](../../../docs/experiments.md).
