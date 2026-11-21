# Lab A/B/C cho R0.2

Issue #40 · tuyến `transport` · bàn giao cho #6. Ba đầu mút chạy Croc trong ba vùng làm việc riêng trên một máy Windows x64. Relay và các phiên chạy qua IPv4 loopback. Lab này dùng để bắt đầu phát triển runner và chạy ca transport cùng cấu hình; LAN, WAN và hiệu năng nhiều máy cần các cấu hình thử tương ứng. [Backlog R0.2](../../../plan/BACKLOG.md) · [Runbook cổng 0](../../../docs/experiments.md#cổng-0--transport) · [Pin Croc và fixture](../../../spec/operations/croc-lab.md)

## Chạy lại

Dùng Croc v11.6.5 Windows x64 đã kiểm SHA-256 theo hồ sơ lab. Từ thư mục gốc repo, tạo sáu fixture tổng hợp vào thư mục mới. Chạy preflight và ghi hiện vật ra một thư mục mới ngoài repo.

```powershell
$labRoot = Join-Path $env:TEMP ("ratatoss-lab-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $labRoot | Out-Null
$fixtures = Join-Path $labRoot 'fixtures'
python scripts/make_croc_lab_fixtures.py $fixtures
python -m scripts.croc_r02_preflight --croc 'C:\lab\croc.exe' --fixtures $fixtures --output (Join-Path $labRoot 'evidence')
```

Hai ca A→B và B→C dùng fixture 32 MiB riêng. Preflight kiểm SHA-256 tệp nhận, mã thoát, dọn tiến trình và listener loopback. Các định danh trong `endpoints.json` là hash của vùng làm việc mỗi đầu mút trong lượt chạy. `network.json` ghi cấu hình khóa của lượt thử. Các giá trị ngân sách lease lấy từ cấu hình smoke và chưa được hiệu chỉnh bằng số đo R0.2. [Runbook adapter](../../../spec/operations/croc-adapter-runbook.md)

`report.json` giữ SHA-256, kích thước và mốc hoạt động của tiến trình. Các mốc này chưa đủ để tính overlap payload, setup hoặc goodput. #6 thu các số đo đó, chạy đủ cỡ và lượt lặp, sau đó chọn batch theo bằng chứng.
