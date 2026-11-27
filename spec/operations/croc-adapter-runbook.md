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

## WAN trực tiếp qua IPv6

Issue #60 · R1.4 · Tuyến `integration`. Kịch bản này dùng profile thử Tailcat đã chạy trên Windows A và macOS B để truyền tệp qua WAN. Mục tiêu là giảm thời gian từ lúc bắt đầu sau consent đến khi người nhận cuối cùng xác minh SHA-256 toàn tệp. Khi đường trực tiếp khả dụng, ưu tiên thử tuyến đó và dùng thời gian thiết lập, goodput đã đo, retry và thời gian xác minh để đánh giá thời gian hoàn tất. [Brief §1](../../docs/source/Ratatoss_Project_Brief_v1.3.md#1-tầm-nhìn-và-bài-toán) · [Quy tắc đo makespan](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)

1. Xác nhận hai đầu có IPv6 toàn cục, tuyến mặc định IPv6 và gửi được UDP ra Internet. Có thể dùng `UDP=true` và `IPv6=true` từ `netcheck` để kiểm tra đầu vào, rồi xác minh đường thực tế ở bước 3. Dùng đúng Croc v11.6.5 và đối chiếu SHA-256 của executable theo OS/kiến trúc. Kiểm kích thước và SHA-256 của fixture tổng hợp `a-32mib.bin` trước khi gửi. Chuẩn bị thư mục phiên trống và cấu hình worker riêng. [Manifest fixture](croc-lab.md#fixture-tổng-hợp-tái-tạo-được) · [Pin và lệnh đã chạy](../../bench/artifacts/r14-preflight/tailcat/2026-11-28-0211-concurrent.json)
2. Chốt cùng kênh ghép phiên ở hai đầu. Đích xác nhận nhận trước khi mở RX với `--yes`. Cấp mã dùng một lần qua `CROC_SECRET` trong môi trường từng child. Đưa output `--debug` qua bộ phân loại trước khi lưu, chỉ giữ sự kiện đã phân loại và số đếm đã lược thông tin mạng. Dùng argv dưới đây để tái hiện profile #60.

   ```text
   TX: [CROC, "--disable-clipboard", "--no-update-check", "--no-compress", "--debug",
        "--relay", "1.getcroc.com:9009", "send", "--no-local", "--transport", "derp",
        "a-32mib.bin"]
   RX: [CROC, "--debug", "--disable-clipboard", "--no-update-check", "--no-compress",
        "--relay", "1.getcroc.com:9009", "--yes"]
   ```

3. Dùng số byte vào theo giao thức và họ địa chỉ tại socket của B để xác định đường payload A→B. Ghi riêng lưu lượng phản hồi B→A. Lưu sự kiện Tailcat `path=…` đã phân loại kèm mốc monotonic ở từng đầu khi có thể. Một sự kiện `path=` chỉ mô tả tuyến quan sát tại đầu báo. Dòng tóm tắt cho biết trạng thái cuối phiên. Khi thiếu bằng chứng cho một chiều, ghi `unknown`.
4. Croc dùng TCP 9009 để ghép phiên trong ca này. `--transport derp` chọn Tailcat và tắt fallback sang relay dữ liệu Croc. Tailcat có thể giữ luồng trên DERP nếu đường UDP trực tiếp chưa khả dụng. Với ca tái hiện, có thể giữ lượt để đo và ghi `derp` nếu dữ liệu thực sự qua DERP. Với ca vận hành ưu tiên tốc độ, dùng ngân sách chờ đã khóa cho profile. Khi hết ngân sách mà payload vẫn qua DERP, so thời gian còn lại của phiên với thời gian thiết lập lại, truyền và xác minh qua profile relay được duyệt. Chỉ chuyển tuyến khi dự kiến hoàn tất sớm hơn. [Tài liệu Croc v11.6.5](https://github.com/schollz/croc/blob/v11.6.5/README.md#data-transport-selection) · [Các lượt DERP và relay đã đo](../../bench/artifacts/r14-preflight/tailcat/README.md#các-lượt-ab)
5. Kiểm kích thước và SHA-256 toàn tệp ở đích. Lưu goodput payload, đường đi, mốc thiết lập và mốc xác minh theo các tín hiệu quan sát được. Trong ca tích hợp có nhiều đích, lấy ACK xác minh của đích cuối để tính makespan theo đồng hồ monotonic của controller. [Runbook thử nghiệm](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng)

Để đưa profile vào allowlist tích hợp, duyệt kênh ghép phiên và relay được phép, khóa phiên bản, cấu hình đường truyền và ngân sách slot, rồi kiểm từ hai đầu theo quy trình tích hợp. Trong profile thử #60, kênh ghép Croc và DERP đều dùng dịch vụ công cộng. [Trạng thái đầu vào R2.2](../../bench/artifacts/r22-preflight/readiness.json)

Trong lượt #60 lúc 02:11 ngày 28/11/2026 (UTC+7), A→B chuyển đủ 32 MiB, khớp SHA-256 và đạt **5,47 MiB/s**. Payload đến B trực tiếp qua UDP/IPv6. Chiều phản hồi B→A đi qua DERP khoảng 4,15 giây đầu rồi chuyển sang UDP/IPv6. Đây là kết quả trên mạng thử đã ghi trong hồ sơ. [Profile Tailcat và bộ chạy](../../bench/artifacts/r14-preflight/tailcat/README.md) · [Số đo lượt 02:11](../../bench/artifacts/r14-preflight/tailcat/2026-11-28-0211-concurrent.json)

### Dùng profile ở adapter Windows

Issue #78 · R0.1 · Tuyến `transport`. Với tuyến WAN đã xác minh, cấu hình `RelayProfile(…, transport="derp")` ở adapter để TX yêu cầu Tailcat kể cả khi batch chỉ có 32 MiB. RX dùng cùng điểm ghép phiên và Croc tự nhận lựa chọn từ TX. Điểm ghép có thể là IPv4 hoặc tên DNS đã duyệt kèm cổng. Chỉ dùng `password=None` khi profile đã duyệt dùng mật khẩu công khai mặc định của bản ghim. Dùng `no_compress=True` khi tái hiện ca #60. [Adapter Croc](../../ratatoss/transport.py)

Profile cũ mặc định dùng `transport="relay"`. Tùy chọn `transport="auto"` để Croc tự chọn trong phiên. Ở Croc v11.6.5 trên WAN, `auto` thử Tailcat từ **128 MiB trong một phiên Croc**. Chọn profile trước khi mở assignment, với ngân sách setup, truyền, xác minh và margin của tuyến đã đo. Nếu phải đổi profile, đồng bộ cả hai đầu bằng assignment mới. [Ngưỡng trong mã nguồn Croc](https://github.com/schollz/croc/blob/v11.6.5/src/croc/tailcat_negotiation.go#L209-L240) · [Giao thức phân công](../../docs/control-protocol.md#phân-công-và-báo-cáo)

Với Tailcat, adapter đọc output Croc trong bộ nhớ và chỉ giữ `tailcat_summary` gồm đường cuối tại đầu báo, số luồng và bộ đếm byte Tailcat. Dựa vào socket từng chiều ở bước 3 để xác nhận đường payload. SHA-256 và điều kiện publish áp dụng cho mọi profile. [Adapter Croc](../../ratatoss/transport.py)

Chạy smoke với binary Windows và fixture 32 MiB đã ghim. Cờ `--tailcat` mặc định mở RX trước và kiểm SHA-256 cùng số luồng, byte Tailcat ở hai đầu. Dùng `--start-first tx` để thử thứ tự ngược và lưu riêng lỗi thiết lập nếu có. Cả hai đầu và kênh ghép mô phỏng nằm trên cùng máy Windows. [Fixture và pin](croc-lab.md) · [Smoke CLI](../../scripts/croc_smoke.py)

```powershell
python -m scripts.croc_smoke --croc $croc --fixture $fixture --work-parent $lab --report $report --tailcat
```

## Preflight ngân sách lease chạy

Issue #25 · tuyến `transport` và điểm bàn giao `control`. Căn cứ [Brief §6.3 và §8 giai đoạn 0](../../docs/source/Ratatoss_Project_Brief_v1.3.md#63-thành-phần-và-trạng-thái), [kế hoạch cổng 0 và lịch cố định](../../plan/ASTRA_PLAN.md), [giao thức phân công và báo cáo](../../docs/control-protocol.md#phân-công-và-báo-cáo) và [runbook thử nghiệm cổng 0–1](../../docs/experiments.md#cổng-0--transport). Phạm vi gồm mục này, [preflight](../../ratatoss/lease_profile.py) và [kiểm thử CLI](../../tests/test_croc_lease.py).

**Đề xuất cho profile thử nghiệm.** Trước khi chạy, khóa batch tính theo byte, ngưỡng goodput payload tính theo bit/giây và ba khoản thời gian nguyên theo mili giây. `setup-ms` bao gồm thời gian sau `ready` đến khi payload bắt đầu, kể cả poll TX. `verify-commit-ms` bao gồm thời gian kết thúc Croc, kiểm batch/piece và công bố bền vững tại RX. `margin-ms` dành cho biến động của các khoản trên. Lấy ngưỡng và các khoản dự trù từ số đo phù hợp hoặc cấu hình đã khóa, ghi nguồn và điều kiện áp dụng. Dùng ngân sách thời gian nhỏ nhất còn lại ở hai đầu khi các đầu có giá trị khác nhau.

- `transfer_ms = ceil(batch_bytes * 8 * 1000 / min_goodput_bps)`
- `required_ms = transfer_ms + setup_ms + verify_commit_ms + margin_ms`
- `available_ms = min(remaining_lease_ms, adapter_timeout_ms)`

Profile khả thi khi `required_ms <= available_ms`. Kiểm tra ngoại tuyến dùng ngân sách chạy cấu hình từ lúc `ready`. CLI gọi cùng API `evaluate_lease_budget` trong `ratatoss.lease_profile` và in kết quả của `LeaseBudget.fits`. Lease chuẩn bị 30 giây là giai đoạn riêng. Các hạn chạy được tính bằng monotonic clock theo giao thức. Mã thoát `0` nghĩa là khả thi theo đầu vào, `1` nghĩa là thiếu ngân sách và `2` nghĩa là đối số không hợp lệ.

Ví dụ tổng hợp với ngưỡng 2.000.000 bit/s và 10.000 ms overhead. Chạy từ gốc repo hoặc trong môi trường đã cài gói Ratatoss.

```powershell
python -m ratatoss.lease_profile --batch-bytes 67108864 --min-goodput-bps 2000000 --remaining-lease-ms 180000 --adapter-timeout-ms 300000 --setup-ms 5000 --verify-commit-ms 2000 --margin-ms 3000
python -m ratatoss.lease_profile --batch-bytes 33554432 --min-goodput-bps 2000000 --remaining-lease-ms 180000 --adapter-timeout-ms 300000 --setup-ms 5000 --verify-commit-ms 2000 --margin-ms 3000
```

Ví dụ 64 MiB cần ít nhất 268.436 ms cho payload, 278.436 ms cả overhead, nên trả mã `1`. Ví dụ 32 MiB cần 144.218 ms cả overhead, nên trả mã `0`. Đây là phép tính trên đầu vào tổng hợp. Nếu profile thiếu thời gian, khóa lại cỡ batch, route có ngưỡng goodput phù hợp hoặc cấu hình lease và timeout dành cho ca thử rồi kiểm lại trước khi cấp việc.

| Ca cần chạy với Croc ghim và profile đã khóa | Điều kiện và bằng chứng |
|---|---|
| Đường chậm còn tiến triển | Chạy trên đường giới hạn goodput với profile khả thi. Ghi các mốc monotonic lấy mẫu byte để thấy payload tiếp tục tăng, thời điểm kết thúc child, kết quả SHA-256 batch/piece và mốc commit RX trong hạn sớm hơn. Khi là ca tích hợp cuối file, lưu thêm kết quả SHA-256 toàn file tại đích. |
| Phiên treo | Dùng cùng profile khả thi và làm dừng luồng payload trong lab trong khi kênh điều khiển còn hoạt động. Ghi mốc tác động, byte đứng yên, deadline hiệu lực, `TRANSPORT_TIMEOUT`, kết quả dừng cây child, slot được nhả và staging dở được dọn hoặc cô lập. Ghi batch đã commit vẫn đúng hash và không có batch dở được publish. Khi chạy lại sau khi khôi phục, đối chiếu ID lần thử mới, hash và commit. |

Lưu phiên bản và digest binary, profile và đường truyền theo bằng chứng, ngân sách preflight, mốc monotonic theo từng node, byte, hash fixture và kết quả kiểm hash. Dùng cùng đồng hồ trên một node để tính khoảng thời gian. Lược token, mã phiên và dữ liệu người dùng khỏi hiện vật. Ghi bằng chứng theo [quy tắc lưu run](../../docs/experiments.md#thu-thập-và-lưu-bằng-chứng).

Chỉ retry cùng profile khi preflight vẫn khả thi, batch vẫn thiếu sau đối chiếu và điều kiện gây lỗi tạm thời đã hết. Nếu đường thực tế xuống dưới ngưỡng hoặc ngân sách vẫn thiếu, đánh giá lại profile trước lần thử tiếp theo. Chỉ retry phần còn thiếu với assignment và mã mới sau khi lần cũ kết thúc. Giữ bản hợp lệ đã lưu bền. [Lịch cố định và retry](../../plan/ASTRA_PLAN.md#lịch-cố-định-ban-đầu) · [Phân công và báo cáo](../../docs/control-protocol.md#phân-công-và-báo-cáo).

Bàn giao cho các điểm tích hợp sau.

- [#5](https://github.com/Hkoado/Ratatoss/issues/5) gọi API tại Node ngay trước spawn. Truyền lease còn lại và thời gian còn lại của hạn adapter theo monotonic clock, làm tròn xuống theo ms và chặn ở 0. Truyền vào `remaining_setup_ms` chỉ phần setup chưa diễn ra, bao gồm cả thời gian còn chờ đầu kia nếu áp dụng. Nếu ngân sách thiếu, báo lỗi và dọn phần staging chưa commit theo luồng hiện hành. Nếu khả thi, tiếp tục dùng hạn sớm hơn đã chốt.
- [#6](https://github.com/Hkoado/Ratatoss/issues/6) dùng CLI để kiểm tra từng profile thử và ghi kết quả cùng số đo của hai ca. Khóa phiên bản, tuyến và điều kiện đo.
- [#8](https://github.com/Hkoado/Ratatoss/issues/8) gọi API trước chuyển sang RUNNING và phát mã. Truyền ngân sách chạy dự kiến ở hai đầu, cùng toàn bộ phần setup sau `ready`. Khi thiếu ngân sách, không chuyển sang RUNNING và đánh giá lại profile trước khi thử lại.
- [#9](https://github.com/Hkoado/Ratatoss/issues/9) kiểm chứng luồng tích hợp gồm profile đủ và thiếu ngân sách, thời gian đã trôi qua từ `ready`, kết quả thử lại và commit hợp lệ. Lặp `ready` hoặc poll dùng hạn của lần giao hiện có.

Cả hai điểm kiểm tính lại ngân sách cho phần việc còn lại. Phần setup đã tiêu tốn thời gian nằm trong phần deadline đã trôi qua. Việc gọi API giữ nguyên mọi deadline. Hai điểm kiểm chạy thật và hai ca Croc tích hợp **chưa chạy** vì controller và adapter chưa sẵn sàng.


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

Ghi phiên theo [runbook thử nghiệm](../../docs/experiments.md), bảo toàn run lỗi và để trống phép đo thiếu. Pin và smoke chuẩn bị Windows đã được kiểm trong [hồ sơ lab Croc](croc-lab.md). Hồ sơ ghi argv thực nghiệm riêng. Cần kiểm tiếp hợp đồng adapter cho từng OS và hoàn tất các ca nghiệm thu của R0.1–R0.2.
