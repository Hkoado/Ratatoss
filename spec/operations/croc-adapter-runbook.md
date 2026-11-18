# Runbook adapter Croc thật

## Khóa bản thử

Dùng binary upstream [Croc v11.6.5](https://github.com/schollz/croc/releases/tag/v11.6.5) cho cổng 0 và làm ứng viên MVP. Chọn asset đúng OS/kiến trúc, đối chiếu SHA-256 gói với nguồn phát hành nếu có, ghi digest executable sau giải nén, và đối chiếu lại sau khi cài lên từng node. Digest tự tính để nhận diện binary cần được ghi riêng với digest kiểm chứng từ nhà phát hành. Dùng đường dẫn tuyệt đối tới binary trong thư mục chỉ tài khoản quản trị bản cài có quyền sửa. Trước khi thử, ghi `--version`, `--help`, `send --help` và `relay --help` từ đúng executable, chạy với môi trường sạch. Dừng khi lệch phiên bản, digest đã khóa hoặc cú pháp xác nhận. Không dùng cơ chế tự cập nhật cho ca chạy đã khóa.

Giữ upstream nguyên bản cho MVP. Nếu pin không đáp ứng ràng buộc về bí mật, staging, vòng đời tiến trình hoặc chạy song song, đánh dấu ca bị chặn, tái hiện trên fixture nhỏ và tìm cấu hình hoặc bản upstream phù hợp. Chỉ xem xét fork khi có ca lỗi tái hiện, yêu cầu cổng cụ thể, không có cách đáp ứng qua adapter hoặc upstream và có người bảo trì bản vá, cùng tiêu chí quay lại upstream. Phân biệt dữ liệu đo từ binary khác pin.

## Hợp đồng child process

- Tạo argv dạng mảng và gọi với `shell=False`. Không dùng shell, đường dẫn lấy từ payload, `PATH` để tìm binary, hoặc file `.cmd`/`.bat` để thay executable Windows. Dùng cwd riêng theo assignment: TX giữ đúng một file batch thông thường theo tên ASCII do adapter sinh, RX bắt đầu trong thư mục trống riêng cùng filesystem với kho batch. Cố định tên batch ứng với assignment, kiểm đúng tên và loại sau khi worker dừng. Chặn symlink/reparse point, giới hạn dung lượng và kiểm quyền cả cha lẫn con.
- Kiểm tra trên pin rằng cả TX lẫn RX dùng mã định trước qua `CROC_SECRET` trong môi trường riêng từng child. Không đặt mã vào argv, URL, clipboard, file cấu hình, môi trường toàn agent, trace hoặc lịch sử shell. Relay có mật khẩu dùng cơ chế môi trường child đã xác nhận của pin, kiểm `CROC_PASS` ở cả relay và client. Dùng môi trường allowlist có các biến hệ điều hành tối thiểu cần thiết và tách kho cấu hình mặc định Croc theo worker hoặc tài khoản/PID supervisor đã đo, để cờ nhớ cấu hình, proxy và identity từ phiên tương tác không ảnh hưởng chạy thử. Môi trường child vẫn có thể bị tài khoản cùng quyền hoặc quản trị đọc trên một số hệ thống. Worker chạy bằng tài khoản giới hạn, hiện vật kiểm thử chỉ chứa canary vô hại.
- Sau khi xác thực help, dùng `--disable-clipboard` ở vị trí cờ toàn cục để chặn clipboard và kiểm `--no-update-check` để chặn cập nhật trong ca ghim. TX dùng lệnh con `send` với một file staging. RX dùng tùy chọn xác nhận tự động `--yes` chỉ sau consent ở Node và chỉ trong thư mục staging riêng. Không dùng chế độ overwrite, remember, QR, text, shell hay truyền thư mục. Xác nhận hành vi `--yes` khi stdout là pipe, tránh nhầm file nhận trên disk với payload stdout. Kiểm thử bằng output được drain đồng thời và có giới hạn. Gắn stdin không tương tác và fail khi prompt bất ngờ, không phát chuỗi trả lời mù. Không lưu output thô vì TX có thể in mã Croc. Chỉ phát sự kiện có trường allowlist.

| Nền tảng | Phải xác nhận bằng executable ghim |
|---|---|
| Windows | `CROC_SECRET` hoạt động ở cả hai đầu khi không mở console tương tác, argv và clipboard sạch. `--yes` ghi đúng một file tại cwd với redirection đã chọn. Kiểm ACL, reparse point, xung đột tên và lỗi đang giữ handle. Dùng Job Object với kill-on-close và gán child trước khi được thả chạy, kiểm trong môi trường có job cha. |
| Linux | `CROC_SECRET` điều khiển cả hai đầu với cấu hình sạch, không bật classic. Kiểm argv, stdout/stderr đã lược, quyền thư mục, process group mới và tín hiệu đến toàn nhóm. |
| macOS | Xác nhận lại hành vi nhận không tương tác, `CROC_SECRET` cả hai đầu và clipboard. Kiểm quyền, group, ứng xử khi app host đóng và sync metadata theo filesystem. |

Các lệnh dự kiến dùng argv dưới đây với đường dẫn tuyệt đối đã kiểm chứng. Các giá trị viết hoa là chỗ thế trực tiếp trong mảng, không phải chuỗi shell. Xác nhận help, cú pháp, biến môi trường và smoke hai đầu trước khi gọi chúng là lệnh đã chạy. Nếu pin không đọc mã môi trường cho TX hoặc RX trên một OS, khóa transport trên OS đó và ghi điều kiện chặn. Không lùi về `--code` hay mã vị trí trong argv.

```text
TX: [CROC, "--disable-clipboard", "--no-update-check", "--relay", RELAY, "send", STAGED_BATCH]
RX: [CROC, "--disable-clipboard", "--no-update-check", "--relay", RELAY, "--yes"]
Relay quản lý: [CROC, "relay"]
```

Nguồn kiểm cú pháp và cơ chế tiến trình gồm [README theo tag](https://github.com/schollz/croc/blob/v11.6.5/README.md), [README upstream](https://github.com/schollz/croc), [Python subprocess](https://docs.python.org/3/library/subprocess.html) và [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

## Thứ tự mở phiên

1. Khởi động relay đã khóa nếu dùng relay tự quản, rồi kiểm tra controller HTTPS nếu dùng luồng tích hợp. Mỗi đầu xác minh profile allowlist, binary, slot và thư mục làm việc riêng. Chốt đường thử và cấu hình relay trước ca chạy. Profile tự quản dùng cùng endpoint trên TX/RX và cổng TCP theo cấu hình relay. Upstream mô tả mặc định 9009–9013, cần kiểm lại bằng help và đường mạng thực tế của pin. Chỉ mở các cổng đã cấu hình cho các máy cần thử. Giữ riêng thông tin xác thực relay. Ghi địa chỉ dưới định danh profile được phép công bố và xác minh private LAN hoặc WAN theo cấu hình đo.
2. Luồng tích hợp chỉ cấp assignment cho đích đã ACCEPTED, nguồn còn quyền và có batch AVAILABLE. Lease chuẩn bị mặc định 30 giây. RX giữ slot, reserve dung lượng, lập staging rồi gửi `ready`. Controller chuyển sang lease chạy 180 giây và phát mã riêng cho assignment qua HTTPS cho RX trong response, cho TX ở lần poll kế tiếp. RX spawn ngay sau response, TX chỉ spawn sau khi poll có mã. Hai lần spawn có thể bị đảo thứ tự do lập lịch hệ điều hành và mạng. Đo khoảng đợi, kiểm cả thứ tự RX trước và TX trước trong cổng 0, và xác nhận pin đợi đầu còn lại trong deadline. Trong POC độc lập, harness mô phỏng cùng thứ tự phân quyền bằng mã ngẫu nhiên dùng một lần và hai khoảng đợi có kiểm soát.
3. Cùng assignment chỉ khởi động một child cho mỗi vai trò và giữ slot đến khi cây child đã dừng. Chốt deadline khi nhận lease dựa vào thời gian monotonic và phần lease còn lại, dùng hạn sớm hơn với timeout adapter. Retry `ready` không mở lease mới. Nếu mất HTTPS, chỉ phiên đã có mã tiếp tục trong hạn. Snapshot đầy đủ mất assignment, hết hạn, mất quyền, yêu cầu cancel/withdraw, hoặc lỗi child đều dẫn đến dừng. Mỗi lần retry controller cấp assignment và mã mới. Xem [giao thức](../../docs/control-protocol.md).
4. Với RX, chỉ sau khi cây child dừng và exit thành công mới bắt đầu kiểm một file thường hợp lệ, đúng kích thước, SHA-256 batch và từng piece. Flush và publish nguyên tử, commit `AVAILABLE` cùng ACK outbox rồi mới gửi ACK. Đối với final, kiểm SHA-256 toàn file và công bố bền vững trước receipt. TX chỉ giữ reference batch đến khi child kết thúc. Xem [thứ tự commit](../../docs/storage-and-recovery.md).

## Hủy và khôi phục

Đặt terminal intent cho assignment để chặn bước publish mới, ngừng nhận sự kiện tiến độ và hủy cả hai đầu qua controller khi có kết nối. Trên POSIX, khởi chạy session/group riêng, gửi terminate cho group, đợi khoảng grace có giới hạn rồi kill group nếu cần. Trên Windows, dùng Job Object gắn cây tiến trình và terminate job hoặc đóng handle cuối sau khi gửi tín hiệu mềm nếu nền tảng hỗ trợ. Chờ reap và drain pipe có deadline, xác nhận không còn child giữ file, rồi xóa đúng staging chưa commit, giải phóng reference và slot. Nếu chưa thể dọn, cô lập staging để startup xử lý và giữ nguyên trạng thái lỗi. Sau crash, supervisor xác nhận child cũ đã chết trước khi dọn, node reconcile từ disk trước công bố availability hoặc cấp lần giao mới. Giữ batch đã commit hợp lệ. Lỗi phân loại theo giao thức, gồm `TRANSPORT_TIMEOUT`, `NO_SPACE` và `CORRUPT`.

## Bằng chứng cổng 0

| Ca thử | Bằng chứng phải thu |
|---|---|
| Smoke và bí mật | Version, SHA-256, OS, kiến trúc, argv đã loại đường dẫn riêng tư, kết quả mã môi trường trên cả hai vai trò, stdout/stderr không đi vào log thô, không có mã trong clipboard và final đúng SHA-256 |
| 32/64/128 MiB | Fixture, số byte, hash hai đầu, setup, goodput, exit code, profile, route và kết quả ít nhất ba lần mỗi cỡ ở chế độ tuần tự và đồng thời |
| A→B đồng thời B→C | Hai mã và hai staging riêng với fixture độc lập ở B cho POC. Khoảng TX/RX giao nhau dương trên monotonic clock của B, C và B nhận đúng hash |
| RX/TX chờ đầu kia, cắt đường, hủy, crash | Deadline, lỗi chuẩn hóa, process tree trước/sau, slot được nhả, staging dở được dọn, batch commit hợp lệ còn nguyên, lần retry mới thành công |
| Đường truyền | Dấu hiệu endpoint socket và byte qua interface/relay theo khoảng truyền. Chỉ đánh dấu `direct` hoặc `relay` khi đủ chứng cứ, nếu thiếu ghi `unknown`. Cùng SSID hoặc IP riêng chưa đủ |

Ghi phiên theo [runbook thử nghiệm](../../docs/experiments.md), bảo toàn run lỗi và để trống phép đo thiếu. Pin release đã được xác nhận qua trang upstream. Binary chưa có trên PATH của môi trường kiểm kê. Các phép thử Croc thật và xác nhận từng OS hiện **chưa chạy**.
