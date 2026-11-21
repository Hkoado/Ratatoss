# Bàn giao nền phát triển Ratatoss

Yêu cầu trực tiếp của chủ dự án, ngoài backlog, chưa có số GitHub Issue. Tuyến chính `integration`, tuyến phụ `store`, `control` và `project-docs`. Nền phát triển cung cấp CLI, HTTP loopback đọc dữ liệu tĩnh, manifest SHA-256 và bootstrap SQLite theo từng vai trò. Lộ trình sản phẩm nằm ở [Brief v1.3 §8–9](../../docs/source/Ratatoss_Project_Brief_v1.3.md#8-lộ-trình-triển-khai-và-nghiệm-thu), với luồng ghi danh, ghép và consent theo [giao thức điều khiển](../../docs/control-protocol.md) và [UX](../../docs/ux.md).

## Điểm vào và ranh giới tệp

Chạy các lệnh phát triển từ [README](../../README.md#chạy-trên-powershell). Các phiên có thể dùng thư mục dữ liệu tạm riêng để tránh ghi vào hồ sơ phát triển thông thường. [Cấu hình đang dùng](tech-stack.md#cấu-hình-đang-dùng)

| Tệp hiện có | Trách nhiệm hiện tại | Điểm phối hợp khi giao issue |
|---|---|---|
| [`__main__.py`](../../ratatoss/__main__.py), [`settings.py`](../../ratatoss/settings.py), [`app.py`](../../ratatoss/app.py) | Điểm vào CLI chung, cấu hình local, khởi động DB Node, phục vụ UI/health có kiểm tra loopback | R1.3 phụ trách điểm vào người dùng. R1.2 phối hợp khi bổ sung điểm vào controller. |
| [`database.py`](../../ratatoss/database.py), [`spec/db/`](../db/), [`setup.py`](../../setup.py), [`MANIFEST.in`](../../MANIFEST.in) | Bootstrap hai DB tách vai trò, nhãn phiên bản, DDL chuẩn cho source và wheel | R1.1 sở hữu truy cập dữ liệu Node, R1.2 sở hữu truy cập DB controller. Đổi bootstrap, schema chia sẻ hoặc cơ chế đóng gói cần review cả bên dùng. |
| [`manifest.py`](../../ratatoss/manifest.py) | Tạo và xác minh manifest, hash tệp và batch | R1.1 phụ trách lưu trữ và tái sử dụng hàm manifest. R1.2 xác thực manifest tại ranh giới API. |
| [`transport.py`](../../ratatoss/transport.py) | Hợp đồng Python cho adapter | R0.1 hiện thực transport, R0.2 chuẩn hóa cách đo, R1.3 gọi qua worker và giữ ngân sách phiên. |
| [`spec/api/`](../api/), [`ratatoss/static/`](../../ratatoss/static/), [UI Kit](../ui-integration.md) | Hợp đồng controller và hiện vật UI | R1.2 triển khai giao thức, R1.3 nối Node/UI và dùng hợp đồng để quyết định quyền, trạng thái. |
| [`tests/`](../../tests/), [`bench/`](../../bench/), [runbook](../../docs/experiments.md) | Kiểm tra mã hiện tại và mẫu kết quả | Mỗi issue giữ ca kiểm đúng phạm vi. R0.2, R1.4 và R2.2 thống nhất cách ghi hiện vật. Tài liệu chạy thử bổ sung nằm dưới `spec/`. |

Tên module mới do từng issue chốt trong bước Plan. Nếu hai issue cùng cần sửa một tệp dùng chung, ghi phụ thuộc PR và thống nhất thứ tự trước khi sửa. [Quy tắc làm việc nhóm §1–4](../../CONTRIBUTING.md)

## Bản nháp để chủ dự án giao issue

Mỗi hàng cung cấp trường mục tiêu, phạm vi, phụ thuộc và điều kiện nghiệm thu cho [mẫu GitHub Issue](../../.github/ISSUE_TEMPLATE/ratatoss-task.md). Khi giao, chủ dự án thêm assignee và số issue phụ thuộc thực tế. Nhóm bốn người có thể tham khảo vai trò Agent & Transport, Storage & Recovery, Scheduler, Controller & Evaluation tại [Brief §11](../../docs/source/Ratatoss_Project_Brief_v1.3.md#11-phân-công-triển-khai-tham-khảo-nhóm-4-người).

| Ticket và tuyến | Mục tiêu, ranh giới tệp và đầu vào | Điều kiện nghiệm thu và bằng chứng cần lưu |
|---|---|---|
| R0.1 · `transport` | Hoàn thiện adapter và smoke runner. Phạm vi lớp transport, cấu hình pin/relay, runner và test của adapter. Đầu vào là binary Croc v11.6.5 có digest, relay thử nghiệm xác định và fixture SHA-256. [Backlog R0.1](../../plan/BACKLOG.md) · [Runbook adapter](croc-adapter-runbook.md) | Qua runner, kiểm pin, gửi và nhận thật với hash trùng, tái hiện timeout, ghi mã thoát, xác nhận toàn cây tiến trình đã dừng, tệp dở được cách ly và lần thử lại có ID riêng. Bằng chứng gồm binary/version/digest, cấu hình đã lược bí mật và kết quả theo lần thử. |
| R0.2 · `transport` | Đo thiết lập và goodput theo cỡ, chồng lấp RX/TX và chọn cỡ batch đầu. Phạm vi runner, `bench/` và hướng dẫn bổ sung trong `spec/`. Cần R0.1, ba đầu mút A/B/C, fixtures 32/64/128 MiB đã hash, cấu hình relay/mạng đã khóa. [Backlog R0.2](../../plan/BACKLOG.md) · [Runbook cổng 0](../../docs/experiments.md#cổng-0--transport) | Lưu tối thiểu ba lần cho mỗi cỡ và mỗi chế độ tuần tự/đồng thời. Ghi hash, setup, goodput, overlap trên cùng đồng hồ B, loại đường nếu quan sát được, timeout tái hiện và lập luận chọn batch. |
| R1.1 · `store` | Xây kho piece/batch, snapshot, ghép file, kiểm tra và reconcile từ đĩa. Phạm vi manifest, kho và DB Node, test lỗi đĩa. Cần R0.2 và manifest v1. [Backlog R1.1](../../plan/BACKLOG.md) · [SQLite Node](../db/README.md#node) · [Lưu trữ và phục hồi](../../docs/storage-and-recovery.md) | Chứng minh hash hỏng bị từ chối, batch được ghi bền trước khi commit availability và chỉ quảng bá sau commit, restart giữ batch hợp lệ và ghép file cuối có SHA-256 đúng. Lưu fixture, mốc ghi/publish và trạng thái sau crash/restart. |
| R1.2 · `control` | Xây controller v1, auth, ghi danh, ghép hai chiều, offer/consent, state SQLite và lịch cố định ban đầu. Phạm vi controller, DB controller, lease/auth và test API. Cần R0.2, danh tính peer và các schema. [Backlog R1.2](../../plan/BACKLOG.md) · [Giao thức](../../docs/control-protocol.md) · [OpenAPI và mẫu](../api/README.md) | Qua API, chứng minh đúng quyền từng đích và thiếu consent thì chưa cấp việc, chỉ một lease sống mỗi khóa, ACK lặp/muộn đúng hiệu ứng, rớt heartbeat, hết lease và reconcile. Lưu trạng thái DB/API theo các mốc đã lược bí mật. |
| R1.3 · `node-ui` | Nối worker RX/TX, API/UI loopback và đóng gói cùng một ứng dụng cho mọi vai trò. Cần R1.1, R1.2 và adapter R0.1. Đọc hướng dẫn tích hợp trước khi dùng UI Kit. [Backlog R1.3](../../plan/BACKLOG.md) · [Tích hợp UI](../ui-integration.md) · [Bộ cài Windows](windows-installer.md) | Dùng cùng bản cài trên máy thử tạo và nhận job. Ghi danh, ghép hai chiều, chọn đích đã ghép, xác nhận trước RX, đổi tab vẫn có tiến độ và ngân sách phiên có hiệu lực. Lưu thao tác UI, cấu hình gói và log agent đã lược bí mật. |
| R1.4 · `integration` | Chuẩn bị kịch bản, hiện vật và CSV cho demo A/B/C/D. Cần R1.3 và đường LAN B↔C đo được. Theo ánh xạ đề xuất ADR0001, nghiệm thu bản chính thức thêm R2.1. [Backlog R1.4](../../plan/BACKLOG.md) · [Runbook cổng 1](../../docs/experiments.md#cổng-1--demo-bốn-node) · [ADR0001](../governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog) | Ghi overlap B vừa nhận vừa chuyển tiếp batch khác đã lưu bền, C offline và reconcile, giữ batch hợp lệ, hash toàn file B/C/D, B tạo job mới để A nhận. Kèm ca restart, batch hỏng và giới hạn slot, cùng log/video đủ mốc và đã lược bí mật. |
| R2.1 · `scheduler` | Tích hợp PLARS theo ETA, goodput, slot và ngân sách nghẽn chung. Phạm vi scheduler, cấu hình tải/topology và telemetry. Backlog yêu cầu R1.4, nhóm nghẽn, mẫu goodput. Theo ánh xạ đề xuất, dùng kiểm chứng R0 và luồng đã nối ở R1.3 để tích hợp trước demo chính thức. [Backlog R2.1](../../plan/BACKLOG.md) · [Brief §4](../../docs/source/Ratatoss_Project_Brief_v1.3.md#4-thuật-toán-trọng-tâm-plars) · [Kế hoạch PLARS](../../plan/ASTRA_PLAN.md#plars-cơ-bản) | Chứng minh phân công động khi còn slot, giữ ngân sách chung, D chọn A khi tốt hơn và cooldown giải thích được. Lưu cấu hình, ảnh đầu vào từng lần quyết định, lý do chọn và telemetry. |
| R2.2 · `benchmark` | Xây runner cho Direct, Gateway nguyên file, Fixed Split, Gateway pipeline và PLARS. Cần R2.1, fixture và hồ sơ mạng; phạm vi runner, `bench/` và báo cáo. [Backlog R2.2](../../plan/BACKLOG.md) · [Brief §9](../../docs/source/Ratatoss_Project_Brief_v1.3.md#9-kiểm-thử-và-benchmark) · [Runbook cổng 2](../../docs/experiments.md#cổng-2--so-sánh) | So cùng fixture, pin Croc, topology/slot và ngân sách. Dùng thêm lịch tĩnh cùng topology; lặp trên WAN chung, peer lệch tốc và rớt mạng. Lưu từng run kể cả thua, lỗi hoặc thiếu số đo. Makespan dừng khi đích cuối đã xác minh SHA-256 toàn file. |

Mở rộng sau R2.2 theo [backlog R3.1–R3.4](../../plan/BACKLOG.md) và [Brief §8 giai đoạn 3](../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-3--mở-rộng-có-điều-kiện). R3.1 cần mục tiêu chịu lỗi và số đo chi phí SafeExit. R3.2 cần mô hình persistence và chứng cứ restart controller/reconcile đúng. R3.3 cần giả thuyết có số đo và đối chứng riêng với PLARS. R3.4 cần khóa tin cậy, yêu cầu quyền đọc và kiểm chữ ký/quyền giải mã xuyên hop.

## Chuẩn bị song song và thứ tự nghiệm thu

1. **Chuẩn bị.** Chủ dự án có thể giao R0.1 ngay khi đủ binary, relay và fixture. Trong lúc đó, thành viên phụ trách Store và Control có thể đọc schema, xác định ca lỗi và chuẩn bị Plan cho R1.1/R1.2. Nhóm Node/UI đọc UI Kit và hợp đồng quyền, nhóm Scheduler và Evaluation chuẩn bị profile và mẫu bằng chứng. Công việc triển khai theo đầu vào của từng ticket.
2. **Kiểm chứng transport.** Chạy R0.1 rồi R0.2. Chọn cỡ batch theo số đo trước khi khóa bài demo và đối chứng. R1.1 và R1.2 có thể thực hiện song song khi R0.2 hoàn tất. R1.3 nối ba phần adapter, Store và Control.
3. **Tích hợp và demo.** Backlog gốc đặt R1.4 trước R2.1. ADR0001 đề xuất tích hợp R2.1 vào luồng sau R1.3 rồi mới nghiệm thu R1.4 toàn tuyến với PLARS cho bản chính thức. Đề xuất cụ thể là chạy smoke phát triển lịch cố định sau R1.3 để kiểm chứng luồng, phục vụ chuẩn bị PLARS và làm căn cứ xử lý thứ tự giao việc. Smoke có kết quả riêng. Chủ dự án cần xác nhận ánh xạ trước khi đặt phụ thuộc issue và chốt lịch nghiệm thu. [Backlog](../../plan/BACKLOG.md) · [ADR0001](../governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog)
4. **Đối chứng và mở rộng.** Sau PLARS và demo chính thức, chạy R2.2 trên cấu hình đã khóa. Chỉ giao từng mục R3.* khi đầu vào và mục tiêu riêng đã được chọn.

## Quy trình và trạng thái

- Khi nhận issue, đọc [MAPDOCS](../../MAPDOCS.md), chỉ mục và quản trị đặc tả. Dùng Astra 6.2 để lập Plan, Sol 6.2 để thực thi sau khi có đầu vào và Astra 6.2 để rà lại phạm vi, hành vi và hiện vật. Luồng PR và quyền merge thuộc [quy trình nhóm](../../CONTRIBUTING.md#3-mở-pr-và-review). [Prompt Plan/Act](../../plan/PROMPTS.md)
- Khi mở issue, xác nhận người phụ trách và số issue phụ thuộc. Thêm đầu mút A/B/C/D và cấu hình thử đã lược bí mật nếu ticket yêu cầu. Chủ dự án chốt relay và nơi lưu hiện vật, xác nhận ánh xạ R1.4/R2.1, nghiệm thu từng cổng và duyệt thay đổi hợp đồng dùng chung theo [quản trị](../governance/README.md).
- Cổng 0 **chưa chạy**. Môi trường chuẩn bị hiện thiếu Croc trên PATH và cấu hình relay thử nghiệm. Cổng 1–2 **chưa chạy**. Còn thiếu bản cài demo, phiên truyền nhiều Node, overlap, kết quả hash các đích và số đo so sánh. Cổng 3 **chưa chạy**. CSV dùng mẫu trống đến khi có kết quả thật. [Lưu bằng chứng](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng) · [Benchmark](../../bench/README.md)
- Các lệnh kiểm nền phát triển nằm trong [README](../../README.md#kiểm-tra-trước-khi-mở-pr). Các ca CLI/SQLite/HTTP dùng fixture cục bộ. Nghiệm thu truyền tải cần hiện vật thực trên cấu hình đã khóa.

## Bằng chứng kiểm tra nền

Phiên chuẩn bị chạy trên Windows với Python 3.14.2 và SQLite 3.50.4. Các DB và tệp thử dùng thư mục tạm.

| Lệnh hoặc thao tác | Kết quả quan sát |
|---|---|
| `python -m unittest discover -s tests -v` | 15 ca đạt, gồm CLI manifest/verify, HTTP loopback, cài đặt cấu hình, bootstrap đồng thời, rollback, mở WAL khi có writer và từ chối DB không tương thích. |
| `python -m pip wheel . --no-build-isolation --no-deps` | Wheel chứa hai DDL đúng byte so với nguồn. Sau cài wheel và cài editable trong hai venv riêng, chạy `init node` và `init controller` thành công từ ngoài checkout trong cả hai môi trường. |
| `python spec/db/validate.py` | Kiểm tra DDL Node và controller đạt trên SQLite 3.50.4. |
| `python spec/ui-kit/scripts/build_preview.py --check` | 101 biến được tham chiếu đều đã khai báo, hash nguồn khớp và preview đồng bộ với JSON. |
| `python spec/governance/verify_originals.py` | Xác minh 9 tệp gốc trong `docs/` và `plan/`. |
