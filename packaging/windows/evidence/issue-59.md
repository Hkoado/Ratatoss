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
| Cài và mở offline qua Start Menu trên Windows 11 x64 sạch | Ca riêng trên VM đạt ngày 2026-11-26. Xem kết quả bên dưới. |

## Nghiệm thu offline trên VM sạch · 2026-11-26

**Đạt.** VM VirtualBox 7.2.6 cài mới Windows 11 Enterprise LTSC Evaluation x64 24H2, build `26100.1742`. Tất cả adapter mạng ảo tắt trong suốt ca. Kiểm tra trước cài đặt ghi nhận 0 adapter đang hoạt động, 0 route mặc định, tài khoản chuẩn không thuộc nhóm Administrators và chưa cài riêng Python, Croc hay Ratatoss.

Bộ cài được build lại từ commit `25b31bb72b059c8cd608d545a13fe21923d3a116` của PR #62 với Python 3.14.2, PyInstaller 6.22.3, Inno Setup 6.7.4 và Croc v11.6.5 đã ghim. SHA-256 quan sát trong VM khớp [manifest của bản đem thử](issue-59.clean-vm.manifest.json) là `0e16366314ac3c0573b161416c3148ef30f93a688a3c61be673047667aef00bc`. Authenticode báo `NotSigned`.

| Ca | Kết quả quan sát |
| --- | --- |
| Cài offline theo tài khoản chuẩn | Chạy bộ cài từ file chép cục bộ với `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` để giữ cổng trước lần mở Node đầu tiên. Setup trả mã 0 trong tài khoản chuẩn, không nâng quyền. Hai shortcut có trong Start Menu của tài khoản thử và dùng thư mục làm việc ngoài thư mục cài. |
| Mở đồng thời khi cổng cấu hình bận | Giữ độc quyền `127.0.0.1:8765`, rồi mở hai shortcut **Ratatoss** và **Ratatoss Terminal**. Chỉ một listener Node xuất hiện trên cổng thay thế `49673`. Mục **2** của Terminal hiển thị đúng URL và trạng thái chưa kết nối điều phối. |
| Web, Terminal và tài nguyên ngoại tuyến | Hoàn tất màn hình chào Edge bằng tùy chọn không đăng nhập. Shortcut Web và mục **1** của Terminal mở hai tab Ratatoss cùng địa chỉ `http://127.0.0.1:49673/`. HTML và CSS trả HTTP 200, giao diện hiển thị đầy đủ và Node tạo DB trong hồ sơ tài khoản. |
| Đóng rồi mở lại | Chọn **3** trong Terminal và đóng trình duyệt. Mở lại shortcut Web vẫn hiển thị Ratatoss trên cổng `49673`, cùng tiến trình Node và một listener. HTML trả HTTP 200. |
| Host và Origin | Health trả 200 với Host và Origin của cổng thực tế. Host dùng `8765`, Origin dùng `8765` và Origin ngoài loopback đều trả 403. |
| Croc và giấy phép | Binary đi kèm trả `croc version 11.6.5`. SHA-256 của binary khớp manifest và có đủ 46 tệp giấy phép được liệt kê. |

## Chạy lại smoke bản đã cài · 2026-11-26

Chạy trên máy kiểm thử Windows với Python 3.14.2 và bản cài tạm khớp [manifest](issue-59.clean-vm.manifest.json). Đặt `RATATOSS_TEST_WINDOWS_APP` trỏ vào bản cài rồi chạy `python -B -m unittest discover -s packaging/windows -v`. Cả 5 ca đạt trong 3 lượt liên tiếp. Kiểm tra sau mỗi lượt xác nhận không còn Node hoặc launcher của bản cài tạm.

Trong ca tái hiện race, một Node dùng cùng executable được mở sau khi smoke nhả mutex kiểm tra ban đầu và trước khi worker của smoke bắt đầu. Smoke báo không tạo được DB fixture. Node bên ngoài Job của smoke vẫn phản hồi HTTP sau khi smoke dọn dẹp. Kiểm tra sau khi kết thúc ca không còn tiến trình của bản cài tạm. Riêng bộ kiểm thử repo đạt 138 ca và trình kiểm tra tài liệu gốc xác minh 9 tệp.

## Mở Ratatoss từ màn hình cuối của bộ cài · 2026-11-26

**Đạt.** Chạy trên một VM Windows 11 Enterprise LTSC Evaluation x64 24H2 mới, build `26100.1742`, với tài khoản chuẩn. Kiểm tra trước khi cài ghi nhận 0 adapter mạng hoạt động, 0 route mặc định, chưa cài Python hoặc Croc riêng và chưa có Ratatoss hay tiến trình Node. SHA-256 của bộ cài trong VM khớp [manifest](issue-59.clean-vm.manifest.json), `0e16366314ac3c0573b161416c3148ef30f93a688a3c61be673047667aef00bc`.

Chạy Setup qua giao diện, giữ thư mục mặc định theo tài khoản và chọn **Finish** khi **Mở Ratatoss** đang được đánh dấu. Setup trả mã 0 và tự mở Edge trong VM. Sau màn hình chào Edge, chọn tiếp tục offline và không đăng nhập. Tab Ratatoss do bộ cài mở hiển thị giao diện có định kiểu tại `http://127.0.0.1:8765/`. Có đúng một listener Node. HTTP trả 200 cho HTML (963 byte, `text/html`) và CSS (848 byte, `text/css`).

VM không có adapter mạng, thư mục chia sẻ, clipboard chia sẻ hay kéo thả. Trong 1.289 mẫu theo dõi máy host, không thấy tiến trình Setup, Web hay Terminal của Ratatoss. Trạng thái host trước và sau ca giống nhau về bản cài, dữ liệu mặc định, shortcut và mục gỡ cài đặt. Trong lúc Node của VM chạy, host không có listener trên cổng `8765`.

Bàn giao qua [#9](https://github.com/Hkoado/Ratatoss/issues/9) cho bản tích hợp và các ca vòng đời phiên ở [#13](https://github.com/Hkoado/Ratatoss/issues/13).

## Chạy lại sau khi gộp main và sửa review · 2026-11-26

Build từ commit `d6f5e91` trên Windows 11 Pro x64 23H2, build `22631.6199`, bằng Python 3.14.2, PyInstaller 6.22.3 và Inno Setup 6.7.4. Cài theo tài khoản vào thư mục thử trên ổ D với `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`. Môi trường này đã có Python. SHA-256 của installer đem thử khớp [manifest mới](issue-59.review.manifest.json), `95fa1dff9c86c3e11b97a5df7c11f2ae922b0fa815e80673a75f428b3f67667f`. Installer có trạng thái `NotSigned`.

| Ca | Kết quả quan sát |
| --- | --- |
| Smoke bản đã cài | 8/8 ca đạt qua `python -m unittest discover -s packaging/windows -v` với `RATATOSS_TEST_WINDOWS_APP` trỏ vào bản cài thử. Smoke kiểm tra đích, thư mục làm việc và tham số của hai shortcut. Hai executable chạy đồng thời từ thư mục khác, dùng cùng Node và cổng loopback thay thế. HTML, CSS, health, Host/Origin và SQLite đạt. |
| Kiểm tra ACL | Dùng lại DB riêng thành công. Launcher từ chối thư mục hoặc DB cấp quyền cho Everyone, giữ nguyên nội dung DB và hiển thị hướng dẫn bằng tiếng Việt. |
| Croc và giấy phép | Croc đã cài báo `croc version 11.6.5`. SHA-256 của binary và đủ 46 tệp giấy phép khớp với manifest. |
| Hồi quy và dọn dẹp | 208 kiểm thử repo đạt. 9 tệp gốc, schema Node/controller, bản dựng UI Kit và điểm vào CLI controller đã được kiểm tra. Sau khi gỡ bản thử, không còn shortcut, đăng ký gỡ cài đặt hay tiến trình Node của ca thử. |
| Cài offline trên VM sạch với installer mới | Chưa chạy. Hai ca VM ở trên ghi nhận installer trước khi sửa review, theo manifest riêng của bản đó. |
