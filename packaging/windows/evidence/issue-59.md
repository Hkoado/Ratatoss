# Smoke bộ cài starter · Issue #59

Ngày 2026-11-25. Máy build và chạy smoke dùng Windows 11 Pro x64 23H2, build `22631.6199`. Tiến trình thử dùng token mức Medium với nhóm Administrators ở chế độ deny-only. Máy đã có Python. Ca chạy giữ kết nối hệ thống.

## Build và kiểm tra

```powershell
.venv\Scripts\python packaging/windows/build.py --iscc $iscc --croc-archive $crocZip
Start-Process -FilePath $installer -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART' -WindowStyle Hidden -Wait
$env:RATATOSS_TEST_WINDOWS_APP = Join-Path $env:LOCALAPPDATA 'Programs\Ratatoss'
.venv\Scripts\python -m unittest discover -s packaging/windows -v
.venv\Scripts\python -m unittest discover -s tests
python spec/governance/verify_originals.py
```

`$iscc` và `$crocZip` là các đầu vào đã ghim trong [hướng dẫn build](../README.md#build). `$installer` là đường dẫn đến file `Ratatoss-Setup-0.1.0-win-x64.exe` trong `dist/windows/`. [Manifest thực tế](issue-59.manifest.json) ghi phiên bản công cụ, runtime, Croc, SHA-256 và trạng thái Authenticode `NotSigned`.

| Ca | Kết quả quan sát |
| --- | --- |
| Build PyInstaller `onedir` và Inno Setup | Build thành công. SHA-256 của installer khớp manifest. |
| Cài theo tài khoản trên máy build | Setup trả mã 0. Bản cài có đăng ký gỡ trong HKCU. Cả hai shortcut Start Menu trỏ đúng launcher, với thư mục làm việc là LocalAppData. |
| Tài nguyên và DB từ bản đã cài | Smoke chạy ngoài thư mục bản cài với PATH chỉ có System32 và đã bỏ PYTHONHOME/PYTHONPATH. Node trả HTTP 200 cho HTML, CSS và health endpoint. DB được tạo với application ID và schema version đúng. |
| Cổng cấu hình bận và mở đồng thời | Smoke giữ cổng cấu hình với socket độc quyền, mở shortcut Web từ Start Menu cùng lúc với executable Terminal. Cả hai dùng cùng Node trên cổng loopback khác. Lựa chọn **2** hiển thị cổng thực tế và trạng thái chưa kết nối điều phối. Lựa chọn **1** gọi trình duyệt mặc định. Sau khi đóng menu và mở lại Web, Terminal báo cùng cổng. |
| Host/Origin theo cổng thực tế | Health trả 200 với origin thực tế. Host hoặc Origin dùng cổng cấu hình đã bận trả 403. Origin ngoài loopback trả 403. |
| Croc và giấy phép | `croc.exe --version` từ bản đã cài trả `croc version 11.6.5`. SHA-256 executable đã cài khớp manifest. Kiểm thấy đủ 46 tệp giấy phép liệt kê trong manifest. |
| Hồi quy và tài liệu gốc | 5 kiểm thử launcher và bản cài đạt. 138 kiểm thử repo đạt. Kiểm tra byte gốc của 9 tệp trong `docs/` và `plan/` đạt. |
| Cài và mở offline qua Start Menu trên Windows 11 x64 sạch | **Chưa chạy.** Chưa có máy hoặc VM sạch. Dùng [ca nghiệm thu](../README.md#nghiệm-thu-trên-máy-sạch) với manifest của bộ cài đem thử. |

Bàn giao qua [#9](https://github.com/Hkoado/Ratatoss/issues/9) cho bản tích hợp và các ca vòng đời phiên ở [#13](https://github.com/Hkoado/Ratatoss/issues/13).
