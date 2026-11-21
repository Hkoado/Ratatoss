# Ngăn xếp và cấu hình Ratatoss

## Starter và đích MVP

| Thành phần | Khai báo hoặc trạng thái starter | Runtime kiểm kê trên Windows 11 x64 | Đích MVP |
|---|---|---|---|
| Python | `>=3.11` | CPython 3.14.2 | Khóa interpreter và bộ phụ thuộc theo từng gói phát hành, kiểm tra bản tối thiểu và các nền tảng được hỗ trợ |
| Build | `setuptools>=68`, `setuptools.build_meta` | setuptools 80.9.0 | Build wheel và cài thử trên máy sạch |
| UI/API | FastAPI `>=0.111,<1`, Uvicorn `>=0.29,<1`, HTML/CSS tĩnh | FastAPI 0.111.0, Uvicorn 0.29.0, Starlette 0.37.2, Pydantic 2.12.5, AnyIO 4.13.0, h11 0.16.0 | UI loopback trên mỗi node. Agent chạy độc lập với vòng đời tab. Controller HTTPS với JSON UTF-8 tại `/v1` |
| Lưu trữ | Manifest/hash SHA-256 qua CLI. Bootstrap SQLite cho Node và controller | SQLite 3.50.4 qua `sqlite3` | SQLite >=3.38.0, có bảng STRICT và hàm JSON. Hai DB riêng cho node/controller trên ổ đĩa cục bộ. WAL, foreign keys mỗi connection, synchronous FULL, busy timeout và một scheduler MVP |
| Truyền | `TransportAdapter` chỉ là Python Protocol | `shutil.which("croc")` không thấy binary trên PATH | Croc upstream v11.6.5 theo [runbook](croc-adapter-runbook.md) |

Phiên bản dự án trong [pyproject.toml](../../pyproject.toml) là 0.1.0. Các phiên bản đo được là ảnh chụp môi trường, còn dải phụ thuộc là điều kiện cài đặt. Để tái lập, chạy `python -VV` và `python -c "import sqlite3; print(sqlite3.sqlite_version)"`, rồi ghi phiên bản package từ `python -m pip show fastapi uvicorn setuptools starlette pydantic anyio h11` trong đúng interpreter của thử nghiệm. Đã thử tạo bảng STRICT và gọi json_valid trên SQLite 3.50.4. Khi kiểm tra bản đóng gói, phải xác nhận cả hai tính năng. SQLite hỗ trợ riêng bảng STRICT từ 3.37.0. Bộ schema yêu cầu SQLite 3.38.0 trở lên và các hàm JSON phải sẵn có, theo [hướng dẫn DB](../db/README.md). Xem [STRICT](https://sqlite.org/stricttables.html), [hàm JSON](https://sqlite.org/json1.html), [pragma SQLite](https://www.sqlite.org/pragma.html) và [đặc tả lưu trữ](../../docs/storage-and-recovery.md).

## Cấu hình đang dùng

| Biến | Tùy chọn CLI và mặc định |
|---|---|
| `RATATOSS_NODE_PORT` | `serve --port` ưu tiên hơn biến môi trường. Miền 1–65535, mặc định 8765. Lệnh mặc định và `serve` bind `127.0.0.1` và tắt proxy headers. |
| `RATATOSS_NODE_DATA_DIR` | `serve --data-dir` hoặc `init node --data-dir` ưu tiên hơn biến. Giá trị tuyệt đối; biến trống dùng mặc định theo tài khoản. Mặc định là `%LOCALAPPDATA%\Ratatoss` (hoặc `~/AppData/Local/Ratatoss`), `~/Library/Application Support/Ratatoss` trên macOS, và `$XDG_DATA_HOME/ratatoss` hoặc `~/.local/share/ratatoss` ở hệ khác. |
| `RATATOSS_CONTROLLER_DB` | `init controller --db` ưu tiên hơn biến. Cần chỉ định đường dẫn DB tuyệt đối trên ổ cục bộ. |

`serve` và `init node` mở hoặc tạo `node.sqlite3` trong thư mục dữ liệu Node. `init controller` mở hoặc tạo DB ở đường dẫn cung cấp. Mở lại giữ dữ liệu hiện có. Runtime từ chối đường dẫn UNC. Người vận hành cần xác nhận ổ ánh xạ hoặc mount thực sự nằm trên filesystem cục bộ. SQLite quản lý WAL, foreign keys, synchronous FULL và busy timeout 5000 ms. Bootstrap lưu `application_id` theo vai trò và `user_version=1` cùng giao dịch với DDL chuẩn tương ứng. CLI từ chối DB sai vai trò, sai phiên bản hoặc có schema chưa nhận diện. DB tự tạo bằng chạy DDL trực tiếp chưa có dấu nhận diện, dành cho kiểm tra DDL độc lập. Runtime có thể khởi tạo lại một DB trống sau lỗi bootstrap. [DDL](../db/README.md) · [Lưu trữ và phục hồi §SQLite và thứ tự commit](../../docs/storage-and-recovery.md#sqlite-và-thứ-tự-commit)

Điểm mở phát triển từ mã nguồn đọc DDL trong `spec/db/`. Wheel chứa bản sao byte của chính hai tệp đó. Hai lệnh `init` chuẩn bị schema cho công việc Store và Control. [Mã bootstrap](../../ratatoss/database.py) · [Build](../../setup.py)

## Hợp đồng cấu hình MVP đề xuất

Tiến trình đọc biến trực tiếp từ môi trường. [.env.example](../../.env.example) liệt kê biến đang dùng và các biến đề xuất cho MVP. Giữ token, mã ghi danh, mã ghép, mật khẩu relay và mã Croc trong kho bí mật hoặc tệp hạn chế quyền đọc.

| Biến đề xuất | Kiểu và giá trị khởi điểm | Cách áp dụng |
|---|---|---|
| `RATATOSS_NODE_PORT` | Số nguyên 1–65535, 8765 | UI vẫn bind loopback. Khi có loader, CLI ưu tiên hơn biến môi trường |
| `RATATOSS_NODE_DATA_DIR` | Đường dẫn tuyệt đối, trống để dùng thư mục ứng dụng riêng của tài khoản | DB node, đối tượng và staging. RX staging cùng filesystem với kho batch. Kiểm tra quyền trước khi mở worker |
| `RATATOSS_CONTROLLER_URL` | URL gốc HTTPS, trống khi chưa cấu hình | Agent nối `/v1`; xác minh tên máy và chuỗi CA, cấm thông tin xác thực trong URL |
| `RATATOSS_CONTROLLER_DB` | Đường dẫn DB tuyệt đối, trống khi chưa cấu hình | Chỉ dùng khi chạy controller, DB riêng trên filesystem cục bộ |
| `RATATOSS_CROC_EXE` | Binary tuyệt đối, trống khi transport chưa cấu hình | Chỉ bật sau khi kiểm tra pin, digest và quyền sở hữu |
| `RATATOSS_CROC_VERSION` | Chuỗi pin `11.6.5` | So sánh với phiên bản executable báo trên mỗi máy |
| `RATATOSS_RELAY_PROFILE` | ID cấu hình allowlist, trống khi chưa cấu hình | Khớp profile controller cấp. Kho bí mật và endpoint được cấu hình cục bộ theo profile đã duyệt |
| `RATATOSS_PIECE_BYTES`, `RATATOSS_BATCH_BYTES` | `4194304`, `67108864` | Số nguyên dương, batch chia hết cho piece. 32/64/128 MiB là ma trận đo cổng 0 |
| `RATATOSS_ENROLLMENT_TTL_S`, `RATATOSS_PAIR_TTL_S`, `RATATOSS_OFFER_TTL_S` | `600`, `600`, `86400` | Controller tính từ lúc phát mã ghi danh, mở phiên ghép và commit offer tương ứng |
| `RATATOSS_HEARTBEAT_S`, `RATATOSS_OFFLINE_AFTER_S`, `RATATOSS_ASSIGNMENT_POLL_S` | `5`, `20`, `1` | Poll khi có slot hoặc đang chạy. Đổi boot hoặc trở lại sau offline yêu cầu reconcile |
| `RATATOSS_PREPARE_LEASE_S`, `RATATOSS_RUN_LEASE_S` | `30`, `180` | Hạn chạy bắt đầu sau ready hợp lệ. Ready lặp giữ nguyên hạn |
| `RATATOSS_CROC_TIMEOUT_S` | Số giây dương, khởi điểm đề xuất `180` | Deadline monotonic sớm hơn giữa giới hạn adapter và phần lease còn lại |
| `RATATOSS_RX_SLOTS`, `RATATOSS_TX_SLOTS` | Số nguyên không âm, khởi điểm demo `1`, `1` | Hai ngân sách riêng. Số 0 vô hiệu hóa hướng tương ứng |

Khi triển khai loader, kiểm tra kiểu, miền giá trị, quan hệ giữa các timeout và điều kiện đường dẫn lúc khởi động. Chỉ bật role đã có đủ cấu hình hợp lệ. Giới hạn upload, kích thước manifest, dung lượng staging và ngân sách disk/CPU/đường truyền dùng profile của bản đóng gói và phải được chốt trước ca đo. Mặc định tắt nhân bản dự phòng và SafeExit. Các giá trị 30/180 giây và timeout adapter cần hiệu chỉnh bằng số đo, theo [giao thức](../../docs/control-protocol.md) và [kế hoạch](../../plan/ASTRA_PLAN.md).
