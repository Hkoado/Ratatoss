<img src="spec/ui-kit/assets/ratatoss-logo.webp" alt="Logo sóc Ratatoss" width="144">

# Ratatoss

Ratatoss là dự án phân phối một tệp cho nhiều người nhận. Thiết kế dùng Croc để truyền từng batch và cho phép thiết bị chuyển tiếp batch đã xác minh trong khi vẫn nhận các batch khác. Mục tiêu là giảm thời gian đến khi người nhận cuối cùng xác minh xong tệp.

Bản khởi đầu chạy được gồm công cụ tạo và kiểm tra manifest SHA-256, giao diện tiếng Việt chỉ đọc trên loopback, và giao diện lập trình cho lớp truyền tải. Croc, tạo job, mời thiết bị, điều phối và tiếp tục truyền sau gián đoạn đang ở giai đoạn thiết kế. Chưa có kết quả benchmark.

## Chạy trên PowerShell

Cần Python 3.11 trở lên. Mở PowerShell tại thư mục chứa `pyproject.toml`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m ratatoss
```

Mở [giao diện Ratatoss](http://127.0.0.1:8765/). Giao diện chỉ phục vụ tại `127.0.0.1` và hiển thị các mục **Gửi**, **Hoạt động** và **Thiết bị**. Dùng `Ctrl+C` để dừng.

```powershell
# Trong cửa sổ PowerShell khác, khi ứng dụng đang chạy
Invoke-RestMethod http://127.0.0.1:8765/api/health

# Nếu cổng mặc định đã được dùng, khởi chạy với cổng khác
.\.venv\Scripts\python.exe -m ratatoss serve --port 8877
```

## Tạo và xác minh manifest

```powershell
# Mỗi lần chạy dùng một thư mục tạm riêng ngoài repo
$demo = Join-Path ([IO.Path]::GetTempPath()) ("ratatoss-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $demo -Force | Out-Null
$file = Join-Path $demo "tep-mau.bin"
$manifest = Join-Path $demo "tep-mau.manifest.json"
$batch = Join-Path $demo "batch-1.bin"

# Tạo tệp mẫu 10 byte, gồm 4 piece và 2 batch khi dùng kích thước dưới đây
[IO.File]::WriteAllBytes($file, [Text.Encoding]::ASCII.GetBytes('abcdefghij'))
.\.venv\Scripts\python.exe -m ratatoss manifest $file --piece-size 3 --batch-size 6 --output $manifest
.\.venv\Scripts\python.exe -m ratatoss verify $file $manifest

# Kiểm tra batch có chỉ số 1, tương ứng với 4 byte cuối của tệp mẫu
[IO.File]::WriteAllBytes($batch, [Text.Encoding]::ASCII.GetBytes('ghij'))
.\.venv\Scripts\python.exe -m ratatoss verify $batch $manifest --batch 1
```

Kích thước mặc định là 4 MiB mỗi piece và 64 MiB mỗi batch. Tham số kích thước nhận số byte. `--output` yêu cầu đường dẫn mới. Khi bỏ qua tham số này, lệnh in JSON ra đầu ra chuẩn. Chỉ số batch bắt đầu từ 0. Lệnh `verify` trả mã 0 khi khớp, 1 khi nội dung sai và 2 khi gặp lỗi đọc hoặc manifest thiếu hợp lệ.

## Kiểm tra trước khi mở PR

Chạy từ thư mục gốc sau khi cài dự án. Các lệnh kiểm tra starter, tài liệu gốc, schema SQLite và tính đồng bộ của UI Kit.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe spec/governance/verify_originals.py
.\.venv\Scripts\python.exe spec/db/validate.py
.\.venv\Scripts\python.exe spec/ui-kit/scripts/build_preview.py --check
```

## Tài liệu dự án

| Tài liệu | Nội dung |
| --- | --- |
| [Đề bài v1.3](docs/source/Ratatoss_Project_Brief_v1.3.md) | Yêu cầu và phạm vi gốc |
| [Kiến trúc](docs/architecture.md) | Thành phần và luồng dữ liệu |
| [Giao thức điều khiển](docs/control-protocol.md) | Điều phối và vòng đời phân công |
| [Lưu trữ và khôi phục](docs/storage-and-recovery.md) | Manifest, xác minh và tiếp tục truyền |
| [Giao diện](docs/ux.md) | Luồng dùng Ratatoss Node |
| [Thử nghiệm](docs/experiments.md) | Kịch bản, đối chứng và số đo |
| [Backlog](plan/BACKLOG.md) | Ticket, phụ thuộc, ranh giới tệp và tiêu chí nghiệm thu |
| [Quy tắc làm việc nhóm](CONTRIBUTING.md) | Phân việc qua issue, tên nhánh, PR, review và quyền merge |
| [MAPDOCS](MAPDOCS.md) | Bản đồ tài liệu theo issue |
| [Sơ đồ hoạt động (PDF)](output/pdf/Ratatoss-so-do-luong-hoat-dong.pdf) | Ghép thiết bị, truyền batch và phục hồi |

Xem [đặc tả triển khai và quy tắc bảo toàn tài liệu gốc](spec/README.md).
