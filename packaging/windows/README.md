# Bộ cài Ratatoss Starter cho Windows 11 x64

[Issue #59](https://github.com/Hkoado/Ratatoss/issues/59) thuộc R1.3, tuyến `node-ui`. Bộ cài chạy starter qua trình duyệt mặc định và cung cấp menu Terminal. Ghi danh, ghép thiết bị và truyền file thuộc luồng tích hợp của [#9](https://github.com/Hkoado/Ratatoss/issues/9). Vòng đời phiên và thao tác thoát Node trong bản tích hợp được bàn giao qua #9 cho [#13](https://github.com/Hkoado/Ratatoss/issues/13).

Nguồn triển khai gồm [Brief §6.1](../../docs/source/Ratatoss_Project_Brief_v1.3.md#61-một-ứng-dụng-giao-diện-web-chạy-tại-máy), [kiến trúc Node §Biên mạng và quyền](../../docs/architecture.md#biên-mạng-và-quyền), [đặc tả bộ cài §Hợp đồng launcher](../../spec/operations/windows-installer.md#hợp-đồng-launcher) và [tích hợp UI](../../spec/ui-integration.md).

## Cài và mở

1. Chạy `Ratatoss-Setup-<version>-win-x64.exe` trong tài khoản Windows đang dùng. Bộ cài mặc định ghi vào `%LOCALAPPDATA%\Programs\Ratatoss`.
2. Chọn **Mở Ratatoss** khi cài xong hoặc mở **Ratatoss** từ Start Menu. Trình duyệt hiển thị giao diện trên địa chỉ `127.0.0.1`.
3. Mở **Ratatoss Terminal**, dùng phím **1** để mở web, **2** để xem địa chỉ và trạng thái, **3** để đóng menu. Node tiếp tục chạy khi đóng tab hoặc menu.

Gỡ bộ cài qua **Settings → Apps → Installed apps**. Dữ liệu mặc định trong `%LOCALAPPDATA%\Ratatoss` được giữ lại.

## Build

Cần Python **3.14.2 x64**, [Inno Setup **6.7.4**](https://github.com/jrsoftware/issrc/releases/tag/is-6_7_4) và [archive Croc **v11.6.5** cho Windows x64](https://github.com/schollz/croc/releases/tag/v11.6.5). Xác nhận Inno Setup từ bản phân phối chính thức trước khi cài. Chạy từ gốc repo bằng PowerShell.

```powershell
py -3.14 -m venv .venv
.venv\Scripts\python -m pip install -r packaging/windows/requirements-build.txt
.venv\Scripts\python -m pip check
$iscc = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'
$crocZip = Join-Path $PWD 'build\croc_v11.6.5_Windows-64bit.zip'
New-Item -Path (Split-Path $crocZip) -ItemType Directory -Force | Out-Null
Invoke-WebRequest -UseBasicParsing -OutFile $crocZip -Uri 'https://github.com/schollz/croc/releases/download/v11.6.5/croc_v11.6.5_Windows-64bit.zip'
.venv\Scripts\python packaging/windows/build.py --iscc $iscc --croc-archive $crocZip
```

Điều chỉnh `$iscc` theo nơi cài compiler. Recipe so SHA-256 của archive và `croc.exe`, đọc phiên bản từ binary, đóng gói thông báo giấy phép, rồi ghi SHA-256 và trạng thái Authenticode của installer vào manifest. Bản `onedir`, installer và manifest nằm trong `dist/windows/`. Trong bản cài, đường dẫn để #9 nối adapter là `Path(sys.executable).with_name("croc.exe")`.

## Kiểm tra trên máy build

```powershell
.venv\Scripts\python -m unittest discover -s packaging/windows -v
python spec/governance/verify_originals.py
```

Sau khi cài, đặt `$env:RATATOSS_TEST_WINDOWS_APP = Join-Path $env:LOCALAPPDATA 'Programs\Ratatoss'` và chạy lại bộ test launcher. Smoke mở shortcut **Ratatoss** từ Start Menu cùng lúc với executable Terminal, dùng thư mục làm việc bên ngoài bộ cài và dữ liệu tạm. Tài khoản thử cần bắt đầu khi Node chưa chạy. Smoke mở các tab loopback bằng trình duyệt mặc định.

## Nghiệm thu trên máy sạch

1. Chuẩn bị Windows 11 x64 sạch với tài khoản chuẩn chưa cài Python và Croc. Lưu phiên bản Windows, đối chiếu SHA-256 installer với manifest và ngắt kết nối mạng của máy thử. Cài từ file đã chép cục bộ. Xác nhận không có yêu cầu nâng quyền và cả hai shortcut chỉ xuất hiện trong Start Menu tài khoản thử.
2. Chạy kịch bản cổng bận trước lần mở Node đầu tiên. Bỏ chọn **Mở Ratatoss** ở màn hình cuối của installer rồi chạy đoạn PowerShell sau. Giữ cửa sổ PowerShell mở trong cả ca.

   ```powershell
   $busy = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 8765)
   $busy.Server.ExclusiveAddressUse = $true
   $busy.Start()
   $shortcuts = Join-Path ([Environment]::GetFolderPath('Programs')) 'Ratatoss'
   Start-Process (Join-Path $shortcuts 'Ratatoss.lnk')
   Start-Process (Join-Path $shortcuts 'Ratatoss Terminal.lnk')
   ```

3. Trong Terminal chọn **2**, ghi cổng thực tế rồi chọn **1**. Hai tab phải mở cùng địa chỉ và tải HTML/CSS. Chọn **3**, đóng các tab, mở lại shortcut **Ratatoss** và kiểm tra địa chỉ vẫn giữ nguyên. Xác nhận `Get-NetTCPConnection -LocalAddress 127.0.0.1 -State Listen -LocalPort $port` cho một listener, với `$port` là cổng vừa đọc.
4. Với cổng thực tế, kiểm API trả `200` cho Host và Origin hợp lệ. Thay Host hoặc Origin bằng cổng bận để nhận `403`. Sau ca dùng `$busy.Stop()`.

   ```powershell
   curl.exe --noproxy '*' -s -o NUL -w '%{http_code}' -H "Origin: http://127.0.0.1:${port}" "http://127.0.0.1:${port}/api/health"
   curl.exe --noproxy '*' -s -o NUL -w '%{http_code}' -H 'Host: 127.0.0.1:8765' "http://127.0.0.1:${port}/api/health"
   curl.exe --noproxy '*' -s -o NUL -w '%{http_code}' -H 'Origin: http://127.0.0.1:8765' "http://127.0.0.1:${port}/api/health"
   ```

5. Lưu manifest và kết quả từng bước. Chỉ lưu phiên bản, SHA-256, mã HTTP, cổng của ca thử, số listener và quan sát giao diện đã lược thông tin cá nhân.
