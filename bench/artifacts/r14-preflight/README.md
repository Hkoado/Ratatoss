# Hồ sơ chuẩn bị lab A/B/C/D · Issue #60

Ngày kiểm fixture 2026-11-26 (UTC+07:00), trên Windows, theo hồ sơ tại `49a225c`. Đã xác minh sáu fixture tại workspace. Phiên 00:30 ngày 28/11/2026 dùng bốn vai trò trên ba máy theo bố trí đã chốt. B và C đã chạy hai chiều trên cùng Mac. [Phiếu chạy lab](https://github.com/Hkoado/Ratatoss/blob/e62dfe2/bench/artifacts/r14-preflight/lab-session.md) · [Số đo phiên 00:30](2026-11-28-0030-bc.json) [Issue #60](https://github.com/Hkoado/Ratatoss/issues/60) · [Runbook thử nghiệm](../../../docs/experiments.md)

## Kiểm kê đầu mút

Vai trò dưới đây theo kịch bản demo. Chốt định danh lab, hệ điều hành, quyền và lịch với người phụ trách từng máy trước phiên đo.

| Node | Vai trò dự kiến | Định danh lab / OS và build | Quyền / lịch (kèm múi giờ) | Trạng thái và lý do |
| --- | --- | --- | --- | --- |
| A | Gửi fixture 32 MiB sang B | Khoa · Windows 11 Pro 23H2, build 22631.6199, x64 | Khoa xác nhận sẵn sàng trong phiên 00:30 UTC+7 | Đã kiểm hash fixture và TCP tới relay WAN. Khoa ghi nhận sender thoát mã 0 lúc 00:36:47. Đầu B dùng để đo vẫn chưa nhận tệp cho lượt này. [Trạng thái sender](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224601607) · [Đối chiếu tại B/C](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224620294) · [Xác nhận A](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224477532) |
| B | Nhận từ A, gửi sang C, thu mốc RX/TX | Huy · Mac ARM64, macOS 27.0.1 (26A434), container Linux aarch64 | Huy vận hành phiên 00:30 UTC+7 | Đã gửi/nhận với C. Đã kiểm TCP từ B tới relay WAN cổng 9009 và 9010. [Kiểm tra tại B](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224498155) |
| C | Nhận từ B và gửi chiều ngược | Cùng Mac của Huy, container và thư mục nhận riêng | Huy vận hành phiên 00:30 UTC+7 | Hai chiều đã khớp fixture qua relay trên Docker bridge. |
| D | Đích cho ca bốn node | Bảo · Windows 11 Pro 25H2, build 26200.9974, x64 | Bảo đã kiểm OS/build. Giờ chạy ca bốn node và quyền cài ứng viên chờ xác nhận. | Bảo đã nhận `a-32mib.bin` bằng Croc v11.6.5 và kiểm đủ 33.554.432 byte, SHA-256 khớp manifest #3. Còn chờ cài và chạy thử ứng viên #9/#10 theo sơ đồ demo. [Kết quả tại D](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224595577) · [Xác nhận D](https://github.com/Hkoado/Ratatoss/issues/60#issuecomment-7224510940) |

Vị trí chạy controller xác định theo cấu hình demo #11. Xác nhận riêng quyền dùng relay và quyền xem số đếm mạng với người quản lý lab. Ghi vị trí truy cập fixture tại mỗi đầu mút khi cấp phát xong.

## Fixture đã đối chiếu

Đã đọc kích thước bằng `Get-Item` và tính SHA-256 bằng `Get-FileHash -Algorithm SHA256` trên từng file trong `fixture/` của workspace cục bộ. Sáu cặp kích thước và digest khớp [manifest #3](../../../spec/operations/croc-lab.md#fixture-tổng-hợp-tái-tạo-được). Thư mục này chứa file chưa theo dõi trong Git. Trên từng máy được cấp quyền, tạo lại bằng [script fixture](../../../scripts/make_croc_lab_fixtures.py) hoặc dùng bản sao đã cấp phát, rồi kiểm lại kích thước và hash trên máy đó.

| File | Byte | SHA-256 |
| --- | ---: | --- |
| `fixture/a-32mib.bin` | 33554432 | `25716462de562377f7c3b37dc26507d5cce2d66338af3cc3b415b956b4c2ec8a` |
| `fixture/a-64mib.bin` | 67108864 | `545a0e718c1a1584c397c853018a16581a31cd66377209041f0984778a4a6a67` |
| `fixture/a-128mib.bin` | 134217728 | `cdf2287f633d6558a33bcdbbfd6428708c8f869b3fc4ffb3cca88366703a353c` |
| `fixture/b-to-c-32mib.bin` | 33554432 | `7488ef0ec60bc1027479ca06cdce256d9465d14368e99fd005b3c6797fe62679` |
| `fixture/b-to-c-64mib.bin` | 67108864 | `69befdfa85c9f9d3283797ebe5869630fd52bd685afa52f651246357930d6c84` |
| `fixture/b-to-c-128mib.bin` | 134217728 | `f9205ac9406aed59a117658ac37648e3c85a49a9b2a37a2a349a55101750b5f8` |

Trên macOS arm64, lượt kiểm ở commit `98edb71` đã tạo lại sáu fixture rồi mở lại từng file để đo số byte và SHA-256. Hồ sơ R2.2 lưu số đo theo tên tương đối dưới `fixture/`. Vị trí cấp phát trên từng máy lab sẽ được ghi khi bàn giao. [Số đo sáu fixture](../r22-preflight/fixture-hashes.json) · [Trạng thái đầu vào #12](../r22-preflight/readiness.json)

## Phiên đo B↔C

[Hồ sơ #40](../r02-preflight/README.md) dùng các tiến trình A/B/C trên một máy Windows qua IPv4 loopback. Dùng hồ sơ đó để tra pin và cách kiểm fixture. Phiên #60 dùng B/C trên Docker bridge cùng Mac theo bố trí của chủ dự án.

1. Ghi máy vật lý và môi trường Croc riêng của B và C. Ghi topology đã lược bí mật, vai trò relay, interface và quy tắc tuyến áp dụng. Trên A, B, C và máy relay được sử dụng, lưu OS/build, kết quả `croc --version` và SHA-256 của đúng executable mà lệnh chạy sẽ gọi. Trước khi chạy, lưu lệnh đã lược bí mật và khóa cấu hình theo từng phiên, gồm giới hạn upload (`--throttleUpload`), chế độ nhiều luồng (`--no-multi` nếu dùng), nén và cờ chọn đường. Áp dụng cả cho TX trên A vì nó tạo tải RX tại B. Ghi commit, thời điểm kèm múi giờ, cỡ fixture, số lượt, slot RX/TX và tải nền.
2. Chạy riêng B→C và C→B với cùng cỡ fixture, dùng thư mục nhận riêng. Sau đó chạy A→B đồng thời B→C bằng hai fixture độc lập cùng cỡ. So kích thước và SHA-256 ở hai đầu mỗi lần thử, ghi lỗi hoặc timeout và kết quả dọn phiên.
3. Trước khi chạy, kiểm tra bộ quan sát trên đường thử thực tế. Dùng một bộ thu tại B, gắn timestamp monotonic tại lúc quan sát cả hai hướng và ghép socket dữ liệu theo phiên Croc. Với capture TCP thụ động, tái lắp byte stream theo sequence TCP, loại byte truyền lại và giữ mốc quan sát của từng đoạn chứa payload. Dùng quy tắc nhận diện vị trí payload trong khung đã xác minh cho đúng phiên bản và cấu hình Croc. [Observer R0.2](../../../scripts/croc_r02_tap.py) là tham chiếu cho Croc v11.6.5 với fixture không nén trên relay loopback. Xác minh riêng quy tắc trên đường LAN và chế độ direct hoặc relay thực tế trước khi dùng số đo. Ghi phương pháp, vị trí quan sát và độ phân giải. Hiện vật chỉ giữ mốc, số byte và metadata đã lược bí mật.
4. Lấy `rx_first` và `rx_last` khi bộ thu thấy byte payload đầu và cuối của A→B tại B, và `tx_first` và `tx_last` từ B→C tại B. Loại bắt tay, header, nonce, thẻ xác thực, ping và byte điều khiển. Chỉ dùng mốc khi cả hai stream quan sát được đầy đủ, số byte payload đối chiếu được với fixture theo cấu hình đã khóa, và đích xác minh SHA-256. Tính `overlap = max(0, min(rx_last, tx_last) - max(rx_first, tx_first))` trên cùng đồng hồ ở B. Nếu thiếu mốc tin cậy, để trống overlap và ghi lý do. Thời gian sống của tiến trình không dùng để suy ra overlap payload.
5. Phân loại từng luồng payload bằng peer trên socket dữ liệu, interface và phần tăng bộ đếm relay gắn được với phiên đó. Ghi `direct` khi quan sát socket dữ liệu giữa hai đầu mút qua interface dự kiến, `relay` khi xác nhận socket dữ liệu đi qua relay, hoặc `unknown` khi không đủ bằng chứng. Bộ đếm relay tổng của ca đồng thời chỉ cung cấp bối cảnh. Lưu riêng bằng chứng socket đã lược bí mật cho A→B và B→C, cùng mốc, cấu hình và log chọn lọc. [Quy tắc thu thập bằng chứng](../../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)

| Ca | Luồng payload | Trạng thái | Loại đường | Bằng chứng socket / interface / relay | Byte nhận / SHA-256 | Mốc đầu/cuối tại B | Lý do |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B→C riêng | B→C (TX tại B) | Đã chạy | relay | Docker bridge cùng Mac | 32 MiB, SHA-256 khớp | [Mốc tại B](2026-11-28-0030-bc.json) | |
| C→B riêng | C→B (RX tại B) | Đã chạy | relay | Docker bridge cùng Mac | 32 MiB, SHA-256 khớp | [Mốc tại B](2026-11-28-0030-bc.json) | |
| Đồng thời | A→B (RX tại B) | `blocked` | | | | | Đã kiểm TCP tới relay WAN từ A và B, chờ ghép phiên Croc |
| Đồng thời | B→C (TX tại B) | `blocked` | | | | | Đã kiểm TCP tới relay WAN từ A và B, chờ ghép phiên Croc |

| Ca | Overlap tại B | Lý do khi thiếu số đo |
| --- | --- | --- |
| A→B đồng thời B→C | | Chưa chạy trên lab |

## Chạy thử bộ đo trên Docker

Ba container A/B/C và một relay chạy trên cùng một máy Mac arm64. Mạng Docker chỉ dùng nội bộ và không publish port ra máy chủ. Đã chạy B→C, C→B và A→B đồng thời B→C. Cả bốn lượt nhận đều khớp 32 MiB và SHA-256 với fixture. Bộ quan sát tại B ghi đầu/cuối payload theo cùng đồng hồ monotonic và đếm đủ byte từng hướng. Kết quả này xác nhận quy trình thu số đo qua relay trong môi trường thử cục bộ. Ca Windows A→Mac B đồng thời B→C cần số đo riêng trên hai máy. [Kết quả Docker](docker-rehearsal.json) · [Mã chạy thử](../../../scripts/croc_r14_rehearsal.py)

Để chạy lại trên Docker Linux ARM64, dùng bản Croc Linux ARM64 v11.6.5 và bộ fixture đã tạo bằng script của repo. SHA-256 của tệp nén là `095526c841d989ef231ce87634e9d4e1410d390d1fa7e825be9d17170286d5ef`. Script xác minh SHA-256 executable và hai fixture 32 MiB trước khi chạy. [Bản Croc v11.6.5](https://github.com/schollz/croc/releases/tag/v11.6.5)

```sh
python -B -m scripts.croc_r14_rehearsal \
  --croc /path/to/linux-arm64/croc \
  --fixtures /path/to/fixture \
  --output /path/to/new-evidence.json
```

Trước khi chạy lab, điền bảng kiểm kê ở trên cùng đầu mối cấp quyền, giờ chạy và cách truy cập từng máy. Ghi cấu hình tích hợp dự kiến cho #9, gồm vị trí controller, bản Node, đường relay và slot RX/TX. Trên tuyến thực tế, thử bộ đo với fixture đã kiểm rồi ghi loại đường và hiện vật theo từng luồng. Dùng kết quả để hoàn thiện `test-nodes` và `integration-config` cho #9, `measured-lan-bc` cho #11, và `locked-croc-network-slots` cho #12. Ca `same-installer-abcd` tiếp tục dùng ứng viên tích hợp và lịch của #11. [Quy tắc hiện vật](../../../spec/operations/issue-readiness.md#hiện-vật-dùng-cho-phép-kiểm)

## Bàn giao

| Bên nhận | Có thể dùng ngay | Còn thiếu |
| --- | --- | --- |
| [#9 · Smoke tích hợp](https://github.com/Hkoado/Ratatoss/issues/9) | Fixture xác minh và kiểm kê theo vai trò | OS/build, quyền và lịch cài/chạy trên từng máy, vị trí fixture trên các máy thử |
| [#11 · Demo bốn Node](https://github.com/Hkoado/Ratatoss/issues/11) | Kịch bản đo B↔C và fixture độc lập để chạy đồng thời | Hồ sơ đầu mút đã xác nhận, hiện vật B↔C, và ứng viên tích hợp từ #9/#10 để chạy `r14 same-installer-abcd` |
| [#12 · Đối chứng](https://github.com/Hkoado/Ratatoss/issues/12) | Digest fixture và danh sách cấu hình cần ghi | Topology, relay, pin Croc, slot RX/TX và bằng chứng đo thực tế để #12 khóa cấu hình. Ngân sách transport lấy từ [#6](https://github.com/Hkoado/Ratatoss/issues/6). [Checklist #43](../../../spec/operations/r22-run-checklist.md) |
