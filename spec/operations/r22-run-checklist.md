# Checklist chạy đối chứng R2.2

> Issue: #43 · Ticket: R2.2 · Tuyến: benchmark  
> Chủ benchmark: #12 · Runbook: [Cổng 2 — So sánh](../../docs/experiments.md#cổng-2--so-sánh)


Checklist này ghi việc tick trước và sau mỗi lượt benchmark. Tất cả ô chưa có bằng chứng phải để trống; không điền kết quả giả định.

## Thông tin lượt chạy

- Ngày giờ bắt đầu:
- Ngày giờ kết thúc:
- Người vận hành:
- Commit:
- `run_id`: 
- `repeat`:
- `seed`:
- `evidence_ref`:
- Trạng thái: `pass` / `fail` / `timeout` / `blocked` / `not_run`

## Trước khi chạy

### Fixture và môi trường

- [ ] Đã kiểm tra fixture có SHA-256 cố định.
- [ ] Đã ghi `fixture_sha256`.
- [ ] Đã ghi `file_bytes`.
- [ ] Đã ghi `batch_mib`.
- [ ] Đã ghi phiên bản Croc và SHA-256 executable.
- [ ] Đã ghi OS của các node.
- [ ] Đã ghi relay và cấu hình relay.
- [ ] Đã ghi cấu hình mạng.
- [ ] Đã ghi `rx_slots` và `tx_slots`.
- [ ] Đã ghi CPU/disk, link rate, latency, loss và quan hệ bottleneck.
- [ ] Đã xác nhận quyền và cấu hình của node.
- [ ] Đã áp dụng cùng quy trình làm ấm/làm lạnh cache.

### Cấu hình đối chứng

- [ ] Direct
- [ ] Gateway nguyên file
- [ ] Fixed Split
- [ ] Gateway pipeline
- [ ] PLARS
- [ ] Đã tạo lịch cố định đối chứng với cùng topology, batch size, cây tuyến cho phép, nút nghẽn và mức RX/TX như PLARS.
- [ ] Đã ghi tên/lộ trình của lịch cố định:


### Warmup và thứ tự

- [ ] Đã chạy đúng một lượt warmup.
- [ ] Warmup không được ghi vào CSV lượt đo.
- [ ] Đã tạo job và state mới cho lượt chạy.
- [ ] Đã xáo trộn thứ tự policy.
- [ ] Đã lưu seed vào run.
- [ ] Đã chạy ít nhất năm lượt đo cho tổ hợp hiện tại.

## Trong khi chạy

- [ ] Đã ghi trigger lỗi và thời điểm trigger thực tế.
- [ ] Đã ghi khoảng offline nếu có.
- [ ] Đã ghi thời điểm recovery thực tế.
- [ ] Đã ghi thời điểm consent và phát lệnh chạy.
- [ ] Đã ghi thời điểm xác minh của từng đích.
- [ ] Đã theo dõi mọi timeout, hash sai và run thiếu số đo.
- [ ] Đã giữ lượt chạy trong bằng chứng thay vì bỏ khỏi CSV.
- [ ] Đã ghi receipt xác minh SHA-256 toàn file của từng đích và đích cuối.

### Hồ sơ lab bắt buộc khi áp dụng

- [ ] WAN B/C chung với LAN nhanh.
- [ ] B/C lệch tốc.
- [ ] C rớt mạng.
- [ ] D có đường A trực tiếp tốt.
- [ ] Đã chạy hồ sơ LAN/AP bận nếu thuộc ma trận benchmark.
- [ ] Đã chạy hồ sơ băng thông bão hòa để kiểm tra `optional_replication_bytes = 0` theo cấu hình mặc định.

## Sau mỗi lượt chạy

- [ ] Hai file `bench/runs.csv` và `bench/transfers.csv` là mẫu header-only.
- [ ] Không ghi dữ liệu benchmark trực tiếp vào hai mẫu.
- [ ] Đã sao chép mẫu vào `bench/artifacts/<run-id>/runs.csv`.
- [ ] Đã sao chép mẫu vào `bench/artifacts/<run-id>/transfers.csv`.
- [ ] Đã lưu dòng run trong `bench/artifacts/<run-id>/runs.csv`.
- [ ] Đã lưu từng lần thử trong `bench/artifacts/<run-id>/transfers.csv`.
- [ ] Đã nối `run_id` giữa hai file bằng chứng.
- [ ] Đã lưu log đã lược bí mật.
- [ ] Đã lưu cấu hình đã dùng.
- [ ] Đã lưu số liệu giao diện/relay.
- [ ] Đã lưu trạng thái hash theo từng đích.
- [ ] Đã lưu script hoặc mã run.

### Số đo cấp run — runs.csv

- `status`:
- `makespan_ms`:
- `source_payload_bytes`:
- `source_wire_bytes`:
- `wan_wire_bytes`:
- `wan_measurement_scope`:
- `retry_payload_bytes`:
- `recovery_ms`:
- `setup_p50_ms`:
- `setup_p95_ms`:
- `peer_utilization_ref`:
- `optional_replication_bytes`:
- `evidence_ref`:
- `notes`:

Để trống số đo thiếu. Ghi lý do trong `notes` thay vì suy ra giá trị.

### Số đo cấp lần thử — transfers.csv

- `run_id`:
- `job_id`:
- `assignment_id`:
- `batch_id`:
- `source_peer`:
- `target_peer`:
- `start_monotonic_ms`:
- `first_byte_monotonic_ms`:
- `last_byte_monotonic_ms`:
- `end_monotonic_ms`:
- `setup_ms`:
- `goodput_bps`:
- `verified_sha256`:
- `status`:
- `is_retry`:
- `is_replication`:
- `notes`:

Để trống số đo thiếu. Ghi lý do trong `notes` thay vì suy ra giá trị.

## Kiểm tra cuối lượt

- [ ] Mọi run đều được giữ, kể cả timeout/hash sai/thất bại/thiếu số đo.
- [ ] Run đạt báo rõ số lần đạt/tổng.
- [ ] Median và min–max chỉ được báo cho run đạt.
- [ ] Makespan chỉ được điền khi đủ đích xác minh toàn file.
- [ ] `makespan_ms` được đo từ lúc phát lệnh chạy sau consent đến lúc controller nhận receipt xác minh SHA-256 toàn file của đích cuối.
- [ ] Thời điểm bắt đầu và kết thúc makespan dùng cùng đồng hồ monotonic.
- [ ] Không bịa kết quả hoặc đóng trạng thái là `pass` nếu thiếu bằng chứng.
- [ ] Bằng chứng có thể truy lại qua `evidence_ref`.

## Trường dữ liệu ngắn theo CSV

```text
run_id:
gate:
scenario:
baseline:
repeat:
seed:
commit:
os:
croc_version:
croc_sha256:
relay_config:
network_profile:
fixture_sha256:
file_bytes:
batch_mib:
rx_slots:
tx_slots:
status:
makespan_ms:
source_payload_bytes:
source_wire_bytes:
wan_wire_bytes:
wan_measurement_scope:
retry_payload_bytes:
recovery_ms:
setup_p50_ms:
setup_p95_ms:
peer_utilization_ref:
evidence_ref:
notes:
```

## Tài liệu nguồn

- [Runbook Cổng 2 — So sánh](../../docs/experiments.md#cổng-2--so-sánh)
- [Thu thập và lưu bằng chứng](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)
- [Mẫu benchmark](../../bench/README.md)
- [Mẫu runs.csv](../../bench/runs.csv)
- [Mẫu transfers.csv](../../bench/transfers.csv)
- [MAPDOCS](../../MAPDOCS.md) 
