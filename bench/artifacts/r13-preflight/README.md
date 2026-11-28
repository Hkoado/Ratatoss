# Hồ sơ chuẩn bị smoke tích hợp R1.3 · Issue #69

Hồ sơ này tổng hợp hiện vật preflight cho [issue #69](https://github.com/Hkoado/Ratatoss/issues/69) (sub-issue của [#60](https://github.com/Hkoado/Ratatoss/issues/60), bàn giao đầu vào cho [#9](https://github.com/Hkoado/Ratatoss/issues/9) theo [ADR 0002](../../../spec/governance/adr/0002-plars-integration-order.md) và [cấu hình readiness](../../../.github/issue-readiness.json)).

## Trạng thái các phép kiểm đầu vào

| Khóa kiểm tra | Trạng thái | Hiện vật | Ghi chú / Lý do còn thiếu |
| --- | --- | --- | --- |
| `test-nodes` | `blocked` | [`test-nodes.json`](test-nodes.json) | Đã soạn đầy đủ phương án máy A (Windows 11 Pro 23H2 `22631.6199` x64) chạy 3 workspace Node `A/B/C` và 1 controller tách biệt trên loopback. Còn chờ `@Hkoado` xác nhận trực tiếp trên `#69` về máy, quyền cài/chạy 4 tiến trình và khung giờ `UTC+07:00` để gắn `evidence_ref` trước khi chuyển `pass`. |
| `integration-config` | `blocked` | [`integration-config.json`](integration-config.json) | Đã khóa đặc tả controller (`routes` `A->B`, `A->C`, `B->C`; `lan_peers = [B, C]`; `fallbacks = {}`; link `loopback`), Croc v11.6.5 Windows x64, relay `127.0.0.1:19009–19010`, fixture `a-128mib.bin` / `a-64mib.bin`, `1 RX / 1 TX` và ngân sách R0.2 `64 MiB`. Còn chờ `@Hkoado` xác nhận trên `#69` và gắn `confirmation_ref` trước khi chuyển `pass`. |

Tệp tổng hợp trạng thái: [`readiness.json`](readiness.json).

## Cấu hình và lịch smoke R1.3 đề xuất (chờ `@Hkoado` xác nhận trên `#69`)

| Hạng mục | Cấu hình đề xuất cho smoke R1.3 (`#9`) | Căn cứ trên `main` |
| --- | --- | --- |
| Máy thử & 4 vai trò tách biệt | Máy vật lý **A (Khoa / `@Hkoado`)** chạy 4 tiến trình tách biệt: `controller` (`127.0.0.1:9443`, `controller.sqlite3`), `node-A` (nguồn, `8765`), `node-B` (đích/forwarder `allow_forward: true`, `8766`), `node-C` (đích cuối `allow_forward: false`, `8767`). | [Kiến trúc](../../../docs/architecture.md), [Hồ sơ lab #60](../r14-preflight/README.md), [Preflight loopback](../r14-preflight/windows-loopback/report.json) |
| Quyền cài/chạy & lịch (`UTC+07:00`) | Đề xuất khung giờ `2026-11-29 09:00–22:00 UTC+07:00`; trạng thái `pending` chờ `@Hkoado` xác nhận quyền chạy 4 tiến trình, CA cục bộ và giờ chạy trực tiếp trên `#69`. | [Phiếu lab #60](../r14-preflight/lab-session.md), [`test-nodes.json`](test-nodes.json) |
| Controller & lịch cố định (`FixedSchedule`) | `ratatoss controller serve` trên `127.0.0.1:9443` (HTTPS, SAN `IP:127.0.0.1`, CA riêng; bí mật sinh ngoài repo); Node giữ UI/API `127.0.0.1`. Cấu hình TOML: `max_sessions = 2`, `lan_peers = ["B", "C"]`, link `loopback` (`max_sessions = 2`, benchmark `../r02/batch-profiles.json` profile `"64"`), `routes`: `A->B`, `A->C`, `B->C`, `fallbacks = {}` (`origin A` là fallback mặc định trong `FixedSchedule.sources()`). | [CLI controller](../../../ratatoss/__main__.py), [Config controller](../../../ratatoss/controller/config.py), [Schedule](../../../ratatoss/controller/schedule.py) |
| Profile mạng, Relay & Croc | Profile **`windows-ipv4-loopback`**: Croc `v11.6.5` Windows x64 SHA-256 `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e`, cờ khóa `--disable-clipboard --no-update-check`, relay `127.0.0.1:19009–19010`, truyền mã qua `CROC_SECRET` riêng của child process. | [Transport adapter](../../../ratatoss/transport.py), [Relay loopback](../r14-preflight/windows-loopback/relay.json) |
| Fixture, cỡ batch & giới hạn RX/TX | Ca chính: `fixture/a-128mib.bin` (`134217728` byte, SHA-256 `cdf2287f…`, `2 × 64 MiB` batch, `4 MiB` piece); ca phụ: `fixture/a-64mib.bin` (`67108864` byte, SHA-256 `545a0e71…`). Giới hạn **`1 RX / 1 TX`** mỗi node, `max_sessions = 2`, ngân sách R0.2 profile `"64"` (`min_goodput_bps = 100000000`, `lease_ms = 75000`, `adapter_timeout_ms = 75000`). | [Batch profiles R0.2](../r02/batch-profiles.json), [Bảng hash R2.2](../r22-preflight/fixture-hashes.json) |

### Nguồn mong đợi theo `FixedSchedule.sources()` cho `a-128mib.bin` (`origin = A`, `B.allow_forward = true`, `C.allow_forward = false`)

| Đích | Batch 0 (chẵn) | Batch 1 (lẻ) | Hành vi mong đợi khi `issue_assignments` chạy |
| --- | --- | --- | --- |
| **B** | `('A',)` | `('C', 'A')` | Cả 2 batch nhận từ **A** (`A->B`); batch 1 bỏ qua C vì không có route `C->B` và C không cho chuyển tiếp. |
| **C** | `('B', 'A')` | `('A',)` | **Điều kiện quan sát `B->C`:** B phải đồng ý nhận (`ACCEPT`), bật `allow_forward = true` và `reconcile` **trước C** → assignment đầu tiên là `A->B`, sau khi B ACK batch 0 mới cấp `B->C`. Nếu C đồng ý và `reconcile` khi B còn chờ đồng ý/chưa `reconcile` (hoặc B lỗi/offline), `A->C` là hành vi fallback hợp lệ. Batch 1 nhận thẳng `A->C`. |

> **Điều kiện thứ tự cho ca chính (`#9`):** Để kiểm chứng được chặng chuyển tiếp `B->C` với `FixedSchedule` và SQLite registry, thực hiện `ACCEPT` (`allow_forward = true`) và `reconcile` cho **B trước C**; khi B chưa sẵn sàng, controller cấp `A->C` theo đúng fallback hợp lệ.

## Các đầu mục chờ `@Hkoado` xác nhận trên `#69` để chuyển sang `pass`

1. **Xác nhận máy A, quyền cài/chạy 4 tiến trình và khung giờ `UTC+07:00` (`test-nodes`)**: comment xác nhận trực tiếp trên [issue #69](https://github.com/Hkoado/Ratatoss/issues/69) để gắn link làm `evidence_ref` và cập nhật `install_run_permission_for_r13`.
2. **Xác nhận cấu hình controller/lịch `FixedSchedule`, profile `windows-ipv4-loopback`, fixture và `1 RX / 1 TX` (`integration-config`)**: gắn link comment xác nhận của `@Hkoado` vào `confirmation_ref` của 3 khối cấu hình.

## Lý do chọn phương án đề xuất và phạm vi bàn giao

- **Tương thích trực tiếp với `main`:** [Transport adapter](../../../ratatoss/transport.py) hiện sử dụng `RelayProfile` IPv4 và pin `WINDOWS_X64_SHA256`, khớp hoàn toàn với `windows-ipv4-loopback` và bộ ngân sách R0.2 trong [`batch-profiles.json`](../r02/batch-profiles.json) (trong khi hỗ trợ Tailcat ở PR `#80` chưa merge và đầu mút D chưa có SHA-256 `croc.exe`).
- **Tách biệt ca smoke phát triển và ca demo đa máy:** Theo [ADR 0002](../../../spec/governance/adr/0002-plars-integration-order.md), `#9` chạy ca smoke lịch cố định để kiểm quyền, consent, ACK, lease và lưu bền; lab đa máy `B/C/D` từ `#60` tiếp tục phục vụ ca demo nghiệm thu `#11` sau khi tích hợp PLARS (`#10`).
- **Trạng thái chạy thực tế:** Ca smoke R1.3 **chưa chạy** trong phạm vi `#69` và chỉ mở khóa `#9` sau khi có xác nhận của `@Hkoado` để chuyển `readiness.json` sang `pass`.

## Thao tác kiểm tra và quy tắc lược bí mật

- Các tệp JSON trong thư mục này được chuẩn hóa xuống dòng `LF` (khai báo trong `.gitattributes`), không có UTF-8 BOM, và đối chiếu SHA-256 chữ thường bằng `hashlib.file_digest(..., "sha256")` qua hàm `report_blocker` trong [`.github/scripts/issue_readiness.py`](../../../.github/scripts/issue_readiness.py).
- Toàn bộ hiện vật đã lược token, mã Croc, mật khẩu relay (`--pass`), khóa riêng TLS/`--pair-key-file`, địa chỉ nhạy cảm và dữ liệu người dùng theo [runbook thử nghiệm](../../../docs/experiments.md).
