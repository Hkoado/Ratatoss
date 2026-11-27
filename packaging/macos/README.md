# Ratatoss Starter cho macOS Apple Silicon

Tải artifact `Ratatoss-Starter-macos-arm64` từ workflow **macOS Starter** của PR. Giải nén ZIP để lấy DMG và manifest. So sánh kết quả `shasum -a 256 *.dmg` với `disk_image.sha256` trong manifest. Bản thử nghiệm có chữ ký ứng dụng ad-hoc, DMG chưa ký và chưa được Apple notarize. Gatekeeper có thể yêu cầu người dùng cho phép mở ứng dụng tải từ Internet.

Mở DMG trong Finder, chép `Ratatoss.app` vào thư mục `Applications` trong thư mục nhà (tạo nếu cần), rồi tháo ảnh đĩa. Mở ứng dụng để vào web. Mỗi lần mở lại sẽ mở web của cùng Node. Có thể xem địa chỉ hiện tại hoặc mở menu bằng Terminal.

```sh
~/Applications/Ratatoss.app/Contents/MacOS/Ratatoss --status
~/Applications/Ratatoss.app/Contents/MacOS/Ratatoss --terminal
```

Node giữ dữ liệu mặc định trong `~/Library/Application Support/Ratatoss`. Thư mục dữ liệu phải thuộc tài khoản đang chạy và có quyền `700`. Khi khởi động Node, launcher đọc `RATATOSS_NODE_DATA_DIR` và `RATATOSS_NODE_PORT`. Nếu cổng bận, hệ điều hành cấp một cổng loopback trống. Đóng tab hay menu vẫn giữ Node chạy trong phiên đăng nhập. Bản starter phục vụ giao diện cục bộ và mang theo Croc cho phần tích hợp #9.

## Build và kiểm tra

Từ gốc repo trên macOS arm64 với uv, chạy các lệnh sau. Build cần mạng để lấy phụ thuộc lần đầu. Bản cài mang theo runtime.

```sh
uv python install 3.11.18
uv venv --managed-python --python 3.11.18 .venv
uv pip install -r packaging/macos/requirements-build.txt
mkdir -p build/macos
curl -fL -o build/macos/croc.tgz \
  https://github.com/schollz/croc/releases/download/v11.6.5/croc_v11.6.5_macOS-ARM64.tar.gz
.venv/bin/python packaging/macos/build.py --croc-archive build/macos/croc.tgz
/usr/bin/python3 packaging/macos/smoke.py dist/macos/*.dmg
```

Script build đối chiếu SHA-256 của archive và binary Croc, đóng gói SQL, asset và giấy phép, rồi xác minh chữ ký bundle. Smoke dùng tài khoản thường, gắn DMG chỉ đọc, chép app vào thư mục nhà tạm và tháo DMG trước khi chạy. Hai launcher cạnh tranh cùng lúc ở cổng cấu hình đã bận. Node con kế thừa sandbox chặn kết nối ra ngoài loopback. Ca LaunchServices mở app như Finder và yêu cầu trình duyệt mặc định mở URL. CI chạy smoke trên một runner mới bằng chính artifact của job build.
