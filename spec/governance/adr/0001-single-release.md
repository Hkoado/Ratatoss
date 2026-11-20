# Một bản phát hành chính thức của Ratatoss

**Trạng thái:** Chủ dự án đã chọn phát hành một bản chính thức. Ánh xạ dưới đây là đề xuất triển khai. Mọi thay đổi vào tài liệu gốc và đường chuẩn vẫn chờ phê duyệt riêng.

## Phạm vi bản chính thức

| Hạng mục | Yêu cầu đưa vào cùng bản phát hành |
| --- | --- |
| Transport | Croc ghim phiên bản và cấu hình. Adapter quản lý phiên, timeout, dừng cây tiến trình và xử lý staging dở. Kiểm chứng RX/TX đồng thời và chọn cỡ batch từ số đo. [Brief §8, giai đoạn 0](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#8-lộ-trình-triển-khai-và-nghiệm-thu) |
| Phân phối và phục hồi | Một ứng dụng cho mọi vai trò, UI/API loopback, ghi danh, ghép hai chiều và consent từng đích. Truyền theo batch, xác minh và lưu bền trước khi chuyển tiếp. Giữ batch hợp lệ qua gián đoạn hoặc restart Node. Ghép tệp, kiểm SHA-256 toàn tệp và ghi receipt từng đích. [Brief §3 F1, F2, F5 và F6](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#3-yêu-cầu-chức-năng-theo-giai-đoạn) · [Giao thức điều khiển](../../../docs/control-protocol.md) |
| Điều phối thích ứng | PLARS là lịch vận hành của bản chính thức. Đo goodput, xét cấu trúc mạng, nghẽn chung, tải và slot để chọn nguồn và batch theo ETA. Theo dõi lease và giữ cooldown khi đổi lịch. Nhân bản dự phòng mặc định tắt. Việc tự chuyển giữa Direct, Gateway và Swarm phụ thuộc kết quả đo như brief quy định. [Brief §3 F3, F4 và §4](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#4-thuật-toán-trọng-tâm-plars) · [PLARS cơ bản](../../../plan/ASTRA_PLAN.md#plars-cơ-bản) |
| Nghiệm thu | Kiểm chứng transport, demo A/B/C/D với PLARS, rồi chạy đối chứng trên cùng fixture, bản Croc, cấu hình mạng và ngân sách. Giữ lịch cố định, gồm chia chẵn/lẻ, trong bộ đối chứng. Báo cả ca lịch động chậm hơn. [Cổng 0–2 và cách lưu bằng chứng](../../../docs/experiments.md) |

## Mở rộng riêng

SafeExit và nhân bản cơ hội, khôi phục controller, tối ưu nâng cao như đa nguồn đồng thời cho một đích, phát hiện nghẽn tự động và điều chỉnh cỡ batch, cùng chữ ký manifest và bảo vệ payload xuyên hop. Mỗi hạng mục có ca thử và tiêu chí riêng theo [Brief §8, giai đoạn 3](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-3--mở-rộng-có-điều-kiện).

## Ánh xạ kế hoạch và backlog

- Gộp phạm vi phát hành của giai đoạn 1 và 2 trong [Brief §8](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#8-lộ-trình-triển-khai-và-nghiệm-thu) và [kế hoạch theo cổng](../../../plan/ASTRA_PLAN.md). Giữ các cổng làm mốc kiểm chứng nội bộ cho bản chính thức.
- Với [backlog](../../../plan/BACKLOG.md), giữ ranh giới tệp của R0.1–R2.2. R1.2 cung cấp controller và vòng đời phân công. R2.1 tích hợp PLARS vào luồng này sau khi có dữ liệu tuyến từ kiểm chứng R0 và đã nối Node ở R1.3. Chạy nghiệm thu R1.4 toàn tuyến với PLARS sau khi tích hợp R2.1. R2.2 giữ các lịch đối chứng. R3.1–R3.4 thuộc phạm vi mở rộng.
- Với [kiến trúc](../../../docs/architecture.md#điều-phối-mvp) và [runbook](../../../docs/experiments.md#cổng-1--demo-bốn-node), áp dụng các bất biến về quyền, ACK, lease và lưu bền cho lịch PLARS. Ca demo bản chính thức dùng PLARS để chứng minh các bất biến đó. Kịch bản lịch cố định phục vụ đối chứng.

**Bằng chứng phát hành:** Các cổng thử truyền thực tế và benchmark cho bản chính thức chưa chạy.
