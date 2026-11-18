# Bộ cài Ratatoss cho Windows

**Trạng thái: đặc tả triển khai.** Starter hiện phục vụ web local qua lệnh `python -m ratatoss`. Bộ cài, launcher, menu CLI và kiểm thử máy sạch thuộc hạng mục này. Nguồn yêu cầu: [brief v1.3, mục 6](../../docs/source/Ratatoss_Project_Brief_v1.3.md), [kiến trúc Node](../../docs/architecture.md), [UX](../../docs/ux.md) và [quy tắc quản trị](../governance/README.md).

## Trải nghiệm người dùng

Phạm vi phát hành đầu tiên là Windows 11 x64, cài theo tài khoản đang dùng bằng `Ratatoss-Setup-<version>-win-x64.exe`. Bộ cài chứa runtime Python, giao diện web, Node và binary croc đã ghim. Người dùng cài như ứng dụng thông thường, rồi bấm **Mở Ratatoss** ở màn hình cuối hoặc biểu tượng **Ratatoss** trong Start Menu. Có thể chọn tạo biểu tượng ngoài Desktop. Người dùng dùng trình duyệt mặc định, không cần cài Python, croc hay Docker riêng.

| Điểm vào | Kết quả |
| --- | --- |
| **Ratatoss** | Bật Node local nếu cần. Khi Node sẵn sàng, mở web bằng trình duyệt mặc định. Hiện thông báo lỗi dễ hiểu nếu không mở được. |
| **Ratatoss Terminal** | Mở cửa sổ có menu **1. Mở giao diện web**, **2. Kiểm tra trạng thái**, **3. Đóng menu**. Dùng Node của cùng tài khoản. Mục 1 mở web trên chính Node đó. |
| Bấm lại biểu tượng Ratatoss | Mở lại web của Node đang chạy. Hiện trạng thái các lượt truyền hiện tại. |
| Đóng tab hoặc cửa sổ Terminal | Node tiếp tục chạy và giữ phiên truyền. |
| **Thoát Ratatoss** | Yêu cầu Node dừng có kiểm soát. Nếu còn phiên đang chạy, hiển thị số phiên và xin xác nhận. Khi mở lại, đối chiếu dữ liệu đã lưu trước khi nhận việc mới. |

Ở lần mở đầu tiên, web hiển thị tên thiết bị và trạng thái kết nối. Bản demo phân phối có thể nạp trước URL HTTPS của controller và cấu hình tin cậy dành cho Ratatoss. Nếu chưa kết nối, trình hướng dẫn hỏi đúng phần còn thiếu, giải thích mã ghi danh lấy từ quản trị viên, rồi dẫn người dùng tới màn hình ghép thiết bị. Cài đặt và mở web local phải hoạt động khi mất Internet. Trạng thái kết nối tới controller hiển thị riêng. Hồ sơ phát hành chứa cấu hình công khai, còn token và mã ghi danh được cấp riêng cho từng thiết bị. Xem [giao thức điều khiển](../../docs/control-protocol.md).

## Thành phần và thư mục

| Thành phần | Yêu cầu |
| --- | --- |
| Đóng gói Python | **PyInstaller dạng thư mục (`onedir`)**, build trên Windows x64. Đưa asset HTML/CSS/JS vào layout, kiểm đường dẫn resource cả khi chạy từ Start Menu với thư mục làm việc khác. |
| Bộ cài | **Inno Setup**, chế độ theo tài khoản với `PrivilegesRequired=lowest`. Dùng một `AppId` ổn định xuyên bản nâng cấp. Cài vào `%LOCALAPPDATA%\Programs\Ratatoss` và tạo các shortcut Start Menu. |
| Node | Một tiến trình nền trên mỗi tài khoản Windows. Bản cài có launcher cửa sổ và launcher Terminal. Cả hai dùng chung lệnh nội bộ mở hoặc kết nối vào Node. |
| croc | Đóng gói asset upstream Windows x64 phiên bản **v11.6.5** làm ứng viên MVP. Gọi bằng đường dẫn tuyệt đối trong thư mục chương trình qua adapter. Đưa thông báo giấy phép đi kèm và khóa digest asset sau khi kiểm chứng. |
| Dữ liệu | `%LOCALAPPDATA%\Ratatoss\` giữ cấu hình, DB, batch, tệp chờ gửi và log. File nhận nằm tại thư mục người dùng chọn. Bảo vệ thư mục trạng thái bằng ACL theo tài khoản. |

PyInstaller đóng gói interpreter và phụ thuộc theo nền tảng build. Inno Setup hỗ trợ chế độ cài không yêu cầu nâng quyền với `lowest`. Ghim phiên bản chính xác của Python, PyInstaller, Inno Setup và phụ thuộc trong hồ sơ phát hành sau khi build thành công. Mỗi bản cao hơn có manifest gồm phiên bản ứng dụng/giao thức, kiến trúc, phiên bản công cụ build, SHA-256 của croc asset và installer, cùng các giấy phép cần phân phối. Nếu có chứng thư ký mã, ký bộ cài và ghi trạng thái chữ ký. Tài liệu build nằm trong repo để người dùng cuối chỉ cần chạy installer. [Tài liệu PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html), [Inno Setup](https://jrsoftware.org/ishelp/topic_setup_privilegesrequired.htm), [croc v11.6.5](https://github.com/schollz/croc/releases/tag/v11.6.5), [runbook adapter](croc-adapter-runbook.md).

## Hợp đồng launcher

1. Launcher liên hệ tiến trình đã chạy qua IPC Windows giới hạn SID tài khoản hiện tại. Dùng mutex theo người dùng để chỉ một Node có quyền giữ khóa dữ liệu. Hai lần bấm đồng thời phải nhận cùng một Node. Không tin PID, URL hoặc cổng từ một tệp trạng thái chưa được kiểm.
2. Khi chưa có Node, khởi chạy executable nền từ thư mục cài. Node bind cổng trên `127.0.0.1`, ưu tiên cổng cấu hình. Nếu cổng đó bận, để hệ điều hành cấp cổng và công bố cổng thực tế qua IPC của Node. Cấu hình Host/Origin theo cổng thực tế, không tắt kiểm tra để né lỗi cổng.
3. Chỉ báo sẵn sàng sau khi dữ liệu local mở được, kiểm tra giao diện đã phục vụ và socket đã bind thành công. Launcher đợi có thời hạn, lấy URL loopback đã xác minh qua IPC rồi mở trình duyệt mặc định. URL mở web không chứa token, mã ghép hay mã croc. Nếu hết thời gian hoặc trình duyệt không mở được, hiển thị thông báo có nút thử lại hoặc sao chép URL local đã xác minh.
4. Cả hai launcher tách khỏi vòng đời của Node. Đóng menu CLI hay tab web không phát tín hiệu dừng Node. Hành động thoát chủ động mới dừng nhận lượt mới, xử lý checkpoint, kết thúc các phiên croc theo runbook và trả khóa dữ liệu. Khi khởi động lại, Node reconcile theo [đặc tả lưu trữ](../../docs/storage-and-recovery.md).
5. Lỗi hiển thị tiếng Việt với cách tự xử lý. Ví dụ **Không mở được trình duyệt. Sao chép địa chỉ để mở thủ công**. Chi tiết kỹ thuật nằm trong log đã lọc bí mật. Cổng UI chỉ bind loopback. Bản desktop thường không cần quy tắc tường lửa inbound.

## Nâng cấp và gỡ cài

- Khi đang truyền, installer yêu cầu đóng Ratatoss có kiểm soát hoặc hoãn nâng cấp. Thay binary sau khi Node và croc child đã dừng. Giữ danh tính, cấu hình, file đã nhận và batch đã xác minh trong thư mục dữ liệu riêng.
- Nếu có thay đổi schema, sao lưu SQLite bằng cơ chế snapshot nhất quán trước khi migrate. Ghi version schema và thực hiện migration có giao dịch. Khi migration lỗi, dừng khởi động và dùng quy trình restore đã kiểm thử trước khi cho bản cũ đọc DB. Khi nâng cấp nhiều máy, chỉ cho node nhận việc nếu phiên bản giao thức nằm trong dải controller hỗ trợ.
- Gỡ bỏ shortcut và binary. Mặc định giữ dữ liệu local để cài lại và tiếp tục. Xóa dữ liệu ứng dụng là thao tác riêng, cần xác nhận. File nhận do người dùng chọn nằm ngoài phạm vi dọn của installer.

## Bàn giao cho coding agent

Triển khai theo thứ tự **launcher và web local → bản `onedir` → installer → máy sạch → nghiệm thu phiên truyền**. Mã launcher dùng entry point hiện có, build recipe và script installer đặt dưới `packaging/windows/`. Nghiệm thu GUI có thể chạy với starter. Chỉ bật và nghiệm thu truyền thật sau khi adapter, controller và các luồng liên quan đã đạt các cổng trong [kế hoạch](../../plan/ASTRA_PLAN.md).

| Ca thử | Điều kiện đạt |
| --- | --- |
| Cài trên máy sạch | Windows 11 x64, tài khoản thường, không cài Python/croc/Docker. Double-click setup, cài xong bấm mở. UI local và asset tải đủ. |
| Cổng bận và bấm hai lần | Chiếm cổng mặc định bằng tiến trình thử nghiệm, mở cả hai shortcut. Một Node dùng cổng loopback khác. Cả hai shortcut đưa tới cùng Node và không mở trang ở tiến trình đang giữ cổng cũ. |
| Mở CLI rồi chuyển Web | Chọn **Mở giao diện web** từ menu bằng phím số. Trong lúc có lượt truyền, web hiển thị cùng job ID. Đóng CLI và tab rồi mở lại, phiên vẫn tiếp tục. |
| Chạy không có Internet | Cài từ file setup local và mở được UI. Màn hình hiển thị trạng thái chưa kết nối controller với nút thử lại. |
| Lỗi khởi động | Tái hiện lỗi mở thư mục dữ liệu và thiếu quyền. Thông báo hiển thị bằng tiếng Việt, có hướng dẫn phù hợp. Agent giữ dữ liệu cũ và log không lộ bí mật. |
| Nâng cấp hoặc gỡ rồi cài lại | Danh tính thiết bị, dữ liệu nhận và file đã xác minh còn nguyên. Sau khi reconnect, đối chiếu trạng thái trước khi giao việc và kiểm SHA-256 cuối. |

Mỗi ca thử ghi phiên bản, SHA-256 installer, môi trường, bước chạy và kết quả quan sát. Cung cấp thêm hướng dẫn một trang cho người dùng gồm **Cài → Mở → Ghép thiết bị → Gửi hoặc Nhận** khi có bản cài thật. Các kết quả nghiệm thu của hạng mục đóng gói hiện chờ triển khai.
