# MAPDOCS · Chọn tài liệu theo issue

Đọc [quy tắc làm việc nhóm](CONTRIBUTING.md) và trang này trước khi mở mã hoặc lập kế hoạch cho issue.

## Chọn tuyến

1. Lấy mã **Ticket** từ issue, ví dụ `R1.1`. Đọc đúng dòng trong [backlog](plan/BACKLOG.md) để kiểm tra đầu vào, ranh giới tệp và điều kiện nghiệm thu. Chọn dòng tương ứng trong bảng dưới.
2. Nếu issue ngoài backlog, dùng trường **Tuyến**. Nếu thiếu cả hai trường, suy ra một tuyến từ mục tiêu và tệp sẽ sửa. Nếu có nhiều tuyến khả dĩ, bắt đầu với tuyến của thay đổi chính. Mở đúng mục của tuyến phụ khi có phụ thuộc hoặc hợp đồng dùng chung bị tác động.
3. Trước khi sửa, ghi ngắn `issue #N · ticket/tuyến · mục đã đọc · tệp dự kiến sửa` trong kế hoạch hoặc bàn giao. Khi thiếu hợp đồng ở tuyến đã chọn, tìm theo tên endpoint, bảng hoặc trạng thái trong tệp được dẫn trước khi mở thêm tài liệu.

Khi triển khai, đọc phần yêu cầu liên quan trong brief, phần kế hoạch áp dụng và ca kiểm chứng tương ứng trong runbook. Bảng đã trỏ tới các phần này. Với thay đổi chỉ sửa tài liệu, đọc các nguồn mà thay đổi dựa vào. Khi viết hoặc thực thi đặc tả, đọc thêm [chỉ mục đặc tả](spec/README.md) và [quy tắc quản trị](spec/governance/README.md).

## Tuyến theo ticket

| Tuyến | Ticket | Đọc trước trong tuyến |
| --- | --- | --- |
| `transport` | R0.1, R0.2 | [Brief §8 giai đoạn 0](docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-0--kiểm-chứng-croc), [dòng cổng 0 trong kế hoạch](plan/ASTRA_PLAN.md), [runbook cổng 0](docs/experiments.md#cổng-0--transport), [Croc adapter](spec/operations/croc-adapter-runbook.md). Với R0.2, đọc thêm [mẫu số liệu](bench/README.md). |
| `store` | R1.1 | [Brief §3 F1, F5, F6](docs/source/Ratatoss_Project_Brief_v1.3.md#3-yêu-cầu-chức-năng-theo-giai-đoạn), [lưu trữ và phục hồi](docs/storage-and-recovery.md), [SQLite Node](spec/db/README.md#node), [đoạn reconcile trong lịch ban đầu](plan/ASTRA_PLAN.md#lịch-cố-định-ban-đầu), [ca restart và batch hỏng ở cổng 1](docs/experiments.md#cổng-1--demo-bốn-node). |
| `control` | R1.2 | [Brief §6.2–6.3](docs/source/Ratatoss_Project_Brief_v1.3.md#62-kênh-điều-khiển-và-đường-truyền-dữ-liệu), [giao thức điều khiển](docs/control-protocol.md), [hợp đồng API theo route](spec/api/README.md#tệp-mẫu-theo-route), [SQLite controller](spec/db/README.md#controller), [ánh xạ R1.2](spec/governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog), [ca consent, lease và ACK ở cổng 1](docs/experiments.md#cổng-1--demo-bốn-node). |
| `node-ui` | R1.3 | [Brief §6.1](docs/source/Ratatoss_Project_Brief_v1.3.md#61-một-ứng-dụng-giao-diện-web-chạy-tại-máy), [biên mạng và quyền](docs/architecture.md#biên-mạng-và-quyền), [UX theo màn hình](docs/ux.md), [Job và consent](docs/control-protocol.md#job-và-consent), [ánh xạ R1.3](spec/governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog), [ca thao tác qua UI ở cổng 1](docs/experiments.md#cổng-1--demo-bốn-node). Với UI, mở [hướng dẫn tích hợp](spec/ui-integration.md) trước UI Kit. Với đóng gói, mở [bộ cài Windows](spec/operations/windows-installer.md). |
| `integration` | R1.4 | [Brief §8 giai đoạn 1](docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-1--mvp-phân-phối-và-phục-hồi), [ánh xạ demo PLARS](spec/governance/adr/0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog), [runbook A/B/C/D](docs/experiments.md#cổng-1--demo-bốn-node), [bằng chứng cần lưu](docs/experiments.md#thu-thập-và-lưu-bằng-chứng). |
| `scheduler` | R2.1 | [Brief §4](docs/source/Ratatoss_Project_Brief_v1.3.md#4-thuật-toán-trọng-tâm-plars), [kế hoạch PLARS](plan/ASTRA_PLAN.md#plars-cơ-bản), [phân công và báo cáo](docs/control-protocol.md#phân-công-và-báo-cáo), [ca WAN chung và peer lệch tốc ở cổng 2](docs/experiments.md#cổng-2--so-sánh). |
| `benchmark` | R2.2 | [Brief §9](docs/source/Ratatoss_Project_Brief_v1.3.md#9-kiểm-thử-và-benchmark), [dòng cổng 2 trong kế hoạch](plan/ASTRA_PLAN.md), [đối chứng](docs/experiments.md#cổng-2--so-sánh), [cách lưu bằng chứng](docs/experiments.md#thu-thập-và-lưu-bằng-chứng), [mẫu CSV](bench/README.md). |
| `extensions` | R3.1, R3.2, R3.3, R3.4 | [Brief §8 giai đoạn 3](docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-3--mở-rộng-có-điều-kiện), [kế hoạch mở rộng](plan/ASTRA_PLAN.md#mở-rộng-có-điều-kiện), [cách lưu bằng chứng](docs/experiments.md#thu-thập-và-lưu-bằng-chứng). Mở thêm [SafeExit](docs/source/Ratatoss_Project_Brief_v1.3.md#5-safeexit--chế-độ-tùy-chọn-không-ép-nhân-bản-mặc-định) cho R3.1, [phục hồi](docs/storage-and-recovery.md#khởi-động-lại-và-mất-kết-nối) cho R3.2, [PLARS](plan/ASTRA_PLAN.md#plars-cơ-bản) cho R3.3 hoặc [mô hình đe dọa](spec/operations/threat-model.md) cho R3.4. |
| `project-docs` | Issue tài liệu ngoài backlog | [Quy tắc nhóm](CONTRIBUTING.md), [quản trị đặc tả](spec/governance/README.md) và các mục nguồn được trích trong trang cần sửa. |

## Thẩm quyền và ranh giới sửa

| Nhóm tài liệu | Dùng để quyết định | Quyền sửa trong issue |
| --- | --- | --- |
| `docs/`, `plan/` | Brief quy định yêu cầu sản phẩm. Giao thức điều khiển và UX cập nhật luồng mời ở §6.1. Kế hoạch, backlog và runbook quy định cách triển khai và bằng chứng. | Chỉ đọc trong công việc thường lệ. Chủ dự án duyệt rõ từng thay đổi nguồn hoặc đường chuẩn qua ADR. |
| `spec/api/`, `spec/db/`, `spec/operations/`, `spec/ui-*` | Hợp đồng triển khai, schema, chế độ vận hành và UX. Mở đúng endpoint, bảng, ca vận hành hoặc màn hình liên quan. | Sửa phần nằm trong phạm vi issue. Khi đổi hợp đồng dùng chung, ghi rõ bên bị ảnh hưởng để người phụ trách cùng review. |
| `spec/governance/` | Quy tắc nguồn và ADR. [Phạm vi phát hành](spec/governance/adr/0001-single-release.md) ghi định hướng một bản chính thức có PLARS. | Có thể đề xuất ADR trong issue phù hợp. Chủ dự án duyệt quyết định và mọi thay đổi vào cơ chế bảo vệ. |
| `MAPDOCS.md`, `CONTRIBUTING.md`, `README.md`, sơ đồ | Điều hướng và quy trình nhóm. | Sửa theo issue tài liệu. Dẫn lại nguồn khi mô tả yêu cầu hoặc hành vi. |

Chạy `python spec/governance/verify_originals.py` trước khi bàn giao.
