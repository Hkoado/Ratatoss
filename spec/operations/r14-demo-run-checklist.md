# Kịch bản demo A/B/C/D

Checklist chuẩn bị cho [#74](https://github.com/Hkoado/Ratatoss/issues/74). Trạng thái ca nghiệm thu [#11](https://github.com/Hkoado/Ratatoss/issues/11) trong checklist này là **chưa chạy**. Dùng [brief v1.3 §8](../../docs/source/Ratatoss_Project_Brief_v1.3.md#8-lộ-trình-triển-khai-và-nghiệm-thu), [runbook cổng 1](../../docs/experiments.md#cổng-1--demo-bốn-node) và [ADR 0002](../governance/adr/0002-plars-integration-order.md) để đối chiếu. Ca phát triển của #9 dùng lịch cố định. Ca nghiệm thu #11 dùng ứng viên tích hợp PLARS từ #10.

## Trước phiên chạy

Điền bảng bằng cấu hình đã xác nhận với người vận hành. Để trống thông tin chưa có và ghi lý do `blocked` hoặc `not_run` trong phiếu ca. Mỗi Node mở cùng phiên bản ứng dụng qua điểm vào đã bàn giao cho hệ điều hành tương ứng.

| Đầu vào cần khóa | Giá trị tại lab | Cách kiểm và lưu |
| --- | --- | --- |
| Mã phiên, thời gian và múi giờ, người vận hành A/B/C/D | | Ghi vai trò, OS/build, quyền chạy và vị trí controller trong hồ sơ phiên. |
| Commit ứng viên #9/#10, phiên bản ứng dụng, bộ cài và SHA-256 từng nền tảng | | Đối chiếu manifest phát hành và kiểm phiên bản trên A/B/C/D. Lưu chứng cứ cho `same-installer-abcd`. |
| Croc trên từng Node, profile, relay và trust store của controller | | Khóa phiên bản, SHA-256 executable, profile đường dữ liệu, thiết lập relay và HTTPS, rồi lưu cấu hình đã lược bí mật. |
| Tuyến A/B/C/D, phép đo LAN B↔C và nhóm nghẽn | | Xác nhận B và C theo topology demo. Đối chiếu phép đo trên đường LAN của chính ca, gồm cả hai chiều và bằng chứng đường truyền cho `measured-lan-bc`. Hồ sơ #60 ghi B và C cùng Mac trong các lượt đã lưu. |
| Fixture nhiều batch và fixture lượt B→A | | Ghi byte, SHA-256 toàn tệp nguồn, cỡ batch đã chọn ở cổng 0 và manifest của từng job. |
| Giới hạn RX/TX, ngân sách đường chung và cấu hình PLARS | | Ghi cấu hình có hiệu lực, thời hạn lease, điều kiện kích hoạt lỗi và cách quan sát payload tại B. |

Nguồn đầu vào và hồ sơ chuẩn bị nằm ở [hồ sơ #60](../../bench/artifacts/r14-preflight/README.md) và [cấu hình Issue readiness](../../.github/issue-readiness.json). Kiểm quyền thử cắt mạng riêng C và gây lỗi trên bản sao fixture trước khi bắt đầu. Ghi mốc tương quan theo job, đích, batch và lần giao bằng định danh đã lược thông tin người dùng. Mỗi phép tính thời lượng dùng các mốc từ cùng đồng hồ monotonic.

## Ca nghiệm thu chính

| Bước | Thao tác và nơi quan sát | Mốc, hiện vật và điều kiện đối chiếu |
| --- | --- | --- |
| 1. Ghi danh và ghép | Mở ứng viên trên A/B/C/D. Ghi danh từng Node với controller. A ghép với B/C/D và xác nhận ghép ở cả hai đầu. | Lưu phiên bản trên bốn Node, trạng thái ghép và ảnh UI đã lược bí mật. B/C/D xuất hiện theo danh sách đã ghép tại A. |
| 2. Gửi và nhận offer | A tạo job qua UI local cho B/C/D. Tạm giữ một đích ở trạng thái chờ để đối chiếu. Từng đích kiểm tra offer, chọn vị trí lưu và xác nhận. B bật quyền chuyển tiếp cho ca pipeline. | Tại controller ghi mốc tạo job, offer, quyết định, cấp assignment và phát lệnh chạy sau consent. Đối chiếu mọi assignment của từng đích với mốc consent tương ứng. |
| 3. Đo pipeline | Ở B, bắt RX batch `j` từ A và TX batch `k` sang C, với `j` khác `k`. Theo dõi A→C, tuyến D và quyết định PLARS tại controller. | Dùng log commit và ACK của `k` xác nhận batch đã lưu bền và kiểm hash trước TX. Ghi byte đầu và byte cuối của RX `j` và TX `k` trên đồng hồ B. Tính `min(RX cuối, TX cuối) − max(RX đầu, TX đầu)` cho cả đối chiếu theo RX và theo TX bằng cách ghép các khoảng payload cùng cặp batch. `pipeline-overlap` cần ít nhất một giao nhau dương đã quan sát và hash batch hợp lệ. Thiếu mốc payload thì để trống số overlap, ghi giới hạn quan sát. |
| 4. Ngắt và khôi phục C | Khi C đã có ít nhất một batch lưu bền và vẫn còn dữ liệu cần nhận, lưu inventory rồi ngắt mạng riêng C. Quan sát B/D tiếp tục. Nối lại C và chờ reconcile. | Ghi trigger, heartbeat, lease, retry, tuyến được chọn lại, ACK hữu ích đầu tiên của job, và ACK hữu ích đầu tiên của C sau reconnect. Đối chiếu batch xác minh trước ngắt, batch còn nguyên sau reconcile và danh sách RX sau reconnect. `recovery` đạt khi mọi batch còn nguyên được giữ và lượt giao lại chỉ chứa batch còn thiếu, hỏng hoặc dở. |
| 5. Xác minh B/C/D | Chờ từng Node ghép, kiểm SHA-256 toàn tệp, công bố tệp và gửi receipt. | Lưu hash nguồn A và hash cuối từng đích cùng mốc xác minh local và receipt controller. `verified-bcd` cần cả ba digest trùng A. Tính makespan từ lệnh chạy sau consent đến receipt xác minh cuối cùng trên đồng hồ controller. |
| 6. Đổi vai | Tạo job mới qua UI của B. A kiểm offer, xác nhận nhận và đối chiếu SHA-256 tệp cuối. | Lưu hai đầu của lượt B→A, consent ở A, digest nguồn tại B, digest đích tại A và receipt. Dùng cho `reverse-job`. |

## Các ca phục hồi và giới hạn

Chạy ca lỗi riêng khi thao tác có thể làm nhiễu mốc của ca chính. Giữ log từng lần thử theo cùng quy tắc thu bằng chứng.

| Ca | Thao tác và Node quan sát | Hiện vật và điều kiện đối chiếu |
| --- | --- | --- |
| Đóng và mở lại tab | Đóng tab trên đích đang nhận, giữ Node chạy rồi mở lại. | Lưu cùng job ID, mốc trước/sau tại Node và tiến độ. Job tiếp tục trong khoảng tab đóng. |
| Khởi động lại từ đĩa | Tại C, ghi inventory sau commit, khởi động lại Node giữa job rồi chờ reconcile. | Đối chiếu batch hợp lệ trên đĩa và registry. Reconcile hoàn tất trước khi C nhận assignment mới, và batch còn nguyên tiếp tục được dùng. |
| Batch hỏng | Dùng ca kiểm soát riêng, sửa một batch thử trên đĩa C trước khi reconcile, giữ nguyên một batch cạnh nó. | Lưu hash/check trước và sau, tập batch loại bỏ và lần nhận lại. Batch hỏng thành missing, batch hợp lệ được giữ, tệp cuối vẫn phải khớp SHA-256. |
| Timeout và cleanup | Dùng ca có assignment nhưng phiên thử thiếu đầu còn lại hoặc bị ngắt có kiểm soát. Quan sát hai Node và controller. | Ghi deadline, lease, mã kết quả, dọn cây tiến trình, cách ly tệp dở và lần retry có ID mới nếu có. Registry chỉ cập nhật availability sau kiểm hash và lưu bền. |
| ACK lặp và ACK muộn | Dùng điểm vào thử của controller đã bàn giao để phát lại ACK hợp lệ và thử ACK của lần giao đã hết lease. | Lưu thứ tự theo lần giao và snapshot registry. ACK lặp giữ kết quả trước. ACK muộn được đối chiếu với quyền của đích, availability và trạng thái của lease mới theo [giao thức điều khiển](../../docs/control-protocol.md#thử-lại-và-lỗi-api). |
| Bão hòa slot và backpressure | Tạo đủ batch chờ trên một Node để chạm giới hạn RX/TX, giữ nguyên ngân sách đường chung. | Lưu snapshot theo tick, số phiên RX/TX, số việc chờ và lý do. Đối chiếu trần theo hướng, giới hạn ngân sách và việc cấp tiếp khi slot được giải phóng. |

## Bàn giao hiện vật cho #11

- Lưu theo mã run dưới `bench/artifacts/r14/`. Điền [mẫu CSV benchmark](../../bench/README.md) bằng lượt thật. Mỗi run giữ một dòng `runs.csv`, mỗi lần giao giữ một dòng `transfers.csv`. Để trống số đo thiếu, ghi lý do và dùng trạng thái `pass`, `fail`, `timeout`, `blocked` hoặc `not_run` theo [runbook thu bằng chứng](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng).
- Lưu cấu hình, mốc monotonic, hash, log theo vai trò và video/ảnh đã lược bí mật cùng mã run. Kiểm từng tệp trước khi đưa lên GitHub. Chỉ lưu dữ liệu fixture, định danh lab cần thiết và trường telemetry được phép công bố. Giữ token, mã Croc, mật khẩu relay, mã ghi danh và dữ liệu người dùng ngoài hiện vật.
- Chuẩn bị `bench/artifacts/r14-preflight/readiness.json` cho `same-installer-abcd` và `measured-lan-bc`. Báo cáo kết quả `bench/artifacts/r14/readiness.json` theo bốn khóa `pipeline-overlap`, `recovery`, `verified-bcd` và `reverse-job`. Mục `pass` trỏ đến tệp hiện vật tương đối và SHA-256 của tệp theo [hợp đồng Issue readiness](issue-readiness.md#hiện-vật-dùng-cho-phép-kiểm).
