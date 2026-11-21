# ADR 0002 · Tích hợp PLARS trước demo bản chính thức

**Trạng thái** Đã chốt cho bản chính thức theo ủy quyền của chủ dự án trong đợt chuẩn bị. [Issue #4](https://github.com/Hkoado/Ratatoss/issues/4)

## Bối cảnh

Backlog gốc đặt R1.4 trước R2.1 để kiểm chứng luồng bằng lịch cố định trước khi phát triển lịch động. ADR 0001 ghi định hướng một bản phát hành có PLARS và đề xuất tích hợp lịch động trước demo nghiệm thu. Nếu dùng một lần demo cho cả hai mục đích, hai ticket sẽ chờ nhau. [Backlog](../../../plan/BACKLOG.md) · [Brief v1.3 §8](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#8-lộ-trình-triển-khai-và-nghiệm-thu) · [ADR 0001](0001-single-release.md#ánh-xạ-kế-hoạch-và-backlog)

## Quyết định

1. [R1.3 · #9](https://github.com/Hkoado/Ratatoss/issues/9) tích hợp Node, controller, kho và adapter. Giữ một ca thử luồng với lịch cố định để kiểm quyền, ACK, lease và lưu bền. Lưu kết quả ca thử phát triển riêng.
2. [R2.1 · #10](https://github.com/Hkoado/Ratatoss/issues/10) tích hợp PLARS sau khi đầu ra R1.3 đã merge và có đủ số liệu transport, goodput cùng hồ sơ nhóm nghẽn.
3. [R1.4 · #11](https://github.com/Hkoado/Ratatoss/issues/11) nghiệm thu toàn tuyến với PLARS sau khi R2.1 đã merge. Dùng A/B/C/D và cấu hình LAN B↔C đã đo. Giữ đủ ca pipeline, mất mạng, hash cuối, tiếp tục truyền và đổi vai trò trong runbook.
4. [R2.2 · #12](https://github.com/Hkoado/Ratatoss/issues/12) chạy đối chứng sau khi đã có PLARS và hiện vật R1.4. Giữ lịch cố định trong bộ đối chứng. [Runbook cổng 1–2](../../../docs/experiments.md)

## Phạm vi áp dụng

Ánh xạ này chỉ quyết định thứ tự phụ thuộc và cách phân biệt ca thử phát triển với nghiệm thu chính thức. Quyền, ACK, lease, lưu bền và tiêu chí nghiệm thu tiếp tục theo nguồn. Đầu vào thực, PR đã duyệt và merge cùng kết quả kiểm là điều kiện để mở từng issue; ca thử cục bộ không thay cho bằng chứng demo. Giữ nguyên các tệp gốc, trạng thái cổng và đường chuẩn. [Quản trị](../README.md) · [Quy tắc nhóm](../../../CONTRIBUTING.md)
