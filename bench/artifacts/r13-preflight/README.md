# Hồ sơ chuẩn bị smoke tích hợp R1.3 · Issue #69

Hồ sơ này tổng hợp hiện vật preflight cho [issue #69](https://github.com/Hkoado/Ratatoss/issues/69) (sub-issue của [#60](https://github.com/Hkoado/Ratatoss/issues/60), bàn giao đầu vào cho [#9](https://github.com/Hkoado/Ratatoss/issues/9) theo [ADR 0002](../../../spec/governance/adr/0002-plars-integration-order.md) và [cấu hình readiness](../../../.github/issue-readiness.json)).

## Trạng thái các phép kiểm đầu vào

| Khóa kiểm tra | Trạng thái | Hiện vật | Ghi chú / Căn cứ |
| --- | --- | --- | --- |
| `test-nodes` | `pass` | [`test-nodes.json`](test-nodes.json) | Chốt máy A (Windows 11 Pro 23H2 `22631.6199` x64 của `@Hkoado`, đã kiểm ở `#40`/`#59`/`#60`) chạy 3 workspace Node `A/B/C` và 1 controller tách biệt trên loopback, kèm khung giờ `UTC+07:00`. |
| `integration-config` | `pass` | [`integration-config.json`](integration-config.json) | Chốt controller HTTPS `127.0.0.1:9443`, UI/API Node `127.0.0.1:8765–8767`, Croc v11.6.5 Windows x64 SHA-256 `1c59981c…`, relay IPv4 `127.0.0.1:19009–19010`, fixture `a-128mib.bin` / `a-64mib.bin`, `1 RX / 1 TX` và ngân sách R0.2 `64 MiB`. |

Tệp tổng hợp trạng thái: [`readiness.json`](readiness.json).

## Cấu hình và lịch smoke R1.3 đã chốt

| Hạng mục | Cấu hình chốt cho smoke R1.3 (`#9`) | Căn cứ trên `main` |
| --- | --- | --- |
| Máy thử & 4 vai trò tách biệt | Máy vật lý **A (Khoa / `@Hkoado`)** chạy 4 tiến trình tách biệt: `controller` (`127.0.0.1:9443`, `controller.sqlite3`), `node-A` (nguồn, `8765`), `node-B` (đích/forwarder `allow_forward: true`, `8766`), `node-C` (đích cuối `allow_forward: false`, `8767`). | [Kiến trúc](../../../docs/architecture.md), [Hồ sơ lab #60](../r14-preflight/README.md), [Preflight loopback](../r14-preflight/windows-loopback/report.json) |
| Quyền cài/chạy & lịch (`UTC+07:00`) | Đã xác nhận quyền cài/chạy trên máy A (đồng bộ với `#40`, `#59`, `#60`); khung giờ dự kiến `2026-11-29 09:00–22:00 UTC+07:00` (linh hoạt theo lịch triển khai `#9` của `@Hkoado` sau khi PR `#69` được duyệt merge). | [Phiếu lab #60](../r14-preflight/lab-session.md), [`test-nodes.json`](test-nodes.json) |
| Controller & biên mạng cục bộ | `ratatoss controller serve` trên `127.0.0.1:9443` (HTTPS, chứng thư SAN `IP:127.0.0.1`, CA riêng; `--pair-key-file` và khóa TLS sinh ngoài repo); mọi Node giữ UI/API cục bộ trên `127.0.0.1`; lịch cố định `A->B`, `B->C`, fallback `C<-A`. | [CLI controller](../../../ratatoss/__main__.py), [Config controller](../../../ratatoss/controller/config.py) |
| Profile mạng, Relay & Croc | Profile **`windows-ipv4-loopback`**: Croc `v11.6.5` Windows x64 SHA-256 `1c59981c97f704baba20c59018c1d19047b67ed9c5a70c460e13d1eb733da22e`, cờ khóa `--disable-clipboard --no-update-check`, relay `127.0.0.1:19009–19010`, truyền mã qua `CROC_SECRET` riêng của child process. | [Transport adapter](../../../ratatoss/transport.py), [Relay loopback](../r14-preflight/windows-loopback/relay.json) |
| Fixture, cỡ batch & giới hạn RX/TX | Ca chính: `fixture/a-128mib.bin` (`134217728` byte, SHA-256 `cdf2287f…`, `2 × 64 MiB` batch, `4 MiB` piece); ca phụ: `fixture/a-64mib.bin` (`67108864` byte, SHA-256 `545a0e71…`). Giới hạn **`1 RX / 1 TX`** mỗi node, `max_sessions = 2`, ngân sách R0.2 profile `"64"` (`min_goodput_bps = 100000000`, `lease_ms = 75000`, `adapter_timeout_ms = 75000`). | [Batch profiles R0.2](../r02/batch-profiles.json), [Bảng hash R2.2](../r22-preflight/fixture-hashes.json) |

## Lý do chọn cấu hình và phạm vi bàn giao

- **Tương thích trực tiếp với `main`:** [Transport adapter](../../../ratatoss/transport.py) hiện sử dụng `RelayProfile` IPv4 và pin `WINDOWS_X64_SHA256`, khớp hoàn toàn với `windows-ipv4-loopback` và bộ ngân sách R0.2 trong [`batch-profiles.json`](../r02/batch-profiles.json) (trong khi hỗ trợ Tailcat ở PR `#80` chưa merge và đầu mút D chưa có SHA-256 `croc.exe`).
- **Tách biệt ca smoke phát triển và ca demo đa máy:** Theo [ADR 0002](../../../spec/governance/adr/0002-plars-integration-order.md), `#9` chạy ca smoke lịch cố định để kiểm quyền, consent, ACK, lease và lưu bền; lab đa máy `B/C/D` từ `#60` tiếp tục phục vụ ca demo nghiệm thu `#11` sau khi tích hợp PLARS (`#10`).
- **Trạng thái chạy thực tế:** Ca smoke R1.3 **chưa chạy** trong phạm vi `#69` và sẽ được thực hiện tại `#9` sau khi PR bàn giao này được `@Hkoado` duyệt merge vào `main`.

## Thao tác kiểm tra và quy tắc lược bí mật

- Các tệp JSON trong thư mục này được chuẩn hóa xuống dòng `LF` (khai báo trong `.gitattributes`), không có UTF-8 BOM, và đối chiếu SHA-256 chữ thường bằng `hashlib.file_digest(..., "sha256")` qua hàm `report_blocker` trong [`.github/scripts/issue_readiness.py`](../../../.github/scripts/issue_readiness.py).
- Toàn bộ hiện vật đã lược token, mã Croc, mật khẩu relay (`--pass`), khóa riêng TLS/`--pair-key-file`, địa chỉ nhạy cảm và dữ liệu người dùng theo [runbook thử nghiệm](../../../docs/experiments.md).
