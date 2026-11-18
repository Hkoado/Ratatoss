# RATATOSS

> **Adaptive, Pipelined & Fault-Tolerant P2P File Distribution**  
> **Tagline:** *Transfer As Swift As Possible — Swift Across Every Branch.*  
> **Tài liệu định hướng sản phẩm và yêu cầu kỹ thuật dành cho nhóm triển khai**  
> **Phiên bản:** 1.3 · **Ngày:** 18/11/2026 · **Trạng thái:** Đề xuất thiết kế, chưa có kết quả benchmark.

> **Điều chỉnh thiết kế v1.1:** Không đặt mục tiêu nhân bản mỗi piece thành hai bản sao. **Phân phối cho người thực sự đang thiếu dữ liệu và giảm makespan là ưu tiên số 1**. Nhân bản *dự phòng* chỉ là tính năng cơ hội khi còn băng thông/tài nguyên dư và không gây chậm đáng kể, hoặc khi người dùng chủ động chọn chính sách chịu lỗi riêng.

## 1. Tầm nhìn và bài toán

**Ratatoss** (lấy cảm hứng từ **Ratatoskr**, chú sóc chạy dọc cây thế giới Yggdrasil trong thần thoại Bắc Âu) là một hệ thống **phân phối một file đến nhiều người nhận** trên mạng hỗn hợp LAN/WAN. Ratatoss dùng **Croc** làm *transport* cho từng phiên truyền và bổ sung lớp điều phối để mọi máy có thể **vừa nhận, vừa chuyển tiếp các phần dữ liệu đã xác minh** mà không chờ tải xong toàn bộ file.

**Mục tiêu ưu tiên số 1:** Giảm thời gian để **người nhận cuối cùng** có đủ file (*makespan*), thay vì chỉ tối đa hóa tốc độ của một kết nối.

**Mục tiêu đi kèm:**

- Giảm áp lực upload và lượng dữ liệu nguồn A phải phát trực tiếp; tận dụng tài nguyên nhàn rỗi của các peer.
- Khai thác LAN tốc độ cao và giảm những lượt truyền trùng qua WAN **khi thực sự có lợi**.
- Tự thích nghi khi goodput, tải thiết bị, kết nối hoặc nhóm peer thay đổi.
- Giữ tiến độ nhận file khi peer mất kết nối; không tải lại các phần đã lưu và xác minh. **Không bắt buộc mỗi piece có hai bản sao**; khi cần thì lấy lại phần thiếu từ A hoặc nguồn còn giữ piece.
- Bảo đảm toàn vẹn dữ liệu và, ở mức mở rộng, xác thực nguồn phát hành. *SafeExit* chỉ là chế độ tùy chọn, không được làm suy giảm ưu tiên tối ưu thời gian phân phối mặc định.

> **Nguyên tắc kiến trúc:** Không máy nào phải chờ nhận đủ file mới được hỗ trợ máy khác. Không máy nào bắt buộc phải chuyển tiếp nếu việc chuyển tiếp làm giảm hiệu năng tổng thể hoặc vượt hạn mức tài nguyên của máy đó.

## 2. Kịch bản chuẩn để tất cả thành viên hiểu thống nhất

- **A:** Máy nguồn tại Hà Nội, có file 20 GB.
- **B và C:** Hai máy tại chi nhánh Đà Nẵng, cùng LAN; có thể trao đổi nội bộ nhanh nếu kết nối LAN thực đo tốt.
- **D:** Người nhận ở một mạng khác (ví dụ làm việc từ xa).

**Đây là hoạt động ĐỒNG THỜI, không phải quy trình A→B/C xong rồi B/C→D:**

```text
                            WAN
                       ┌────────────┐
                       │ A: file 20G│
                       └──────┬─────┘
                              │ cấp các batch KHÁC NHAU
                     ┌────────┴────────┐
                     ▼                 ▼
                 ┌───────┐   LAN   ┌───────┐
                 │   B   │◄───────►│   C   │
                 │ RX+TX │         │ RX+TX │
                 └───┬───┘         └───┬───┘
                     └───────┬─────────┘
                             ▼  WAN (nếu có lợi)
                         ┌───────┐
                         │   D   │
                         │ RX+TX │
                         └───────┘
              A ───────────► D (tùy điều kiện mạng)
```

Diễn biến minh họa:

1. A bắt đầu gửi một nhóm batch cho B và một nhóm batch khác cho C, **đồng thời**. Tỷ lệ có thể là 60/40, 50/50 hoặc phương án khác, tùy tốc độ/tải đo được; **không phân chia cố định**.
2. **Ngay khi B nhận xong và xác minh batch #1**, B có thể bắt đầu gửi #1 cho C hoặc D, **trong lúc vẫn đang nhận #3, #5… từ A**. C làm tương tự với #2, #4…
3. Nếu B còn dư **download** trong lúc C đang bận, Scheduler có thể giao B nhận thêm batch chưa được phân công hoặc đang chờ. B **không phải đợi C gửi xong phần được giao**; cũng không cần chờ B hoàn thành 12 GB ban đầu.
4. B và C có thể **vừa tải từ A, vừa trao đổi hai chiều qua LAN, vừa upload cho D** (tới giới hạn tài nguyên và số phiên an toàn).
5. Nếu B→D chậm hơn A→D hoặc C→D, D chọn nguồn/nhóm nguồn khác. Có thể chia các batch khác nhau cho nhiều nguồn nếu giúp giảm thời gian hoàn thành; không mặc định D luôn tải qua B/C.
6. Nếu C ngắt mạng, B vẫn giữ toàn bộ batch đã xác minh; Scheduler **chỉ phân công lại phần còn thiếu**, lấy từ A hoặc peer đang có bản sao, không bắt đầu lại từ 0.

**Điểm quan trọng:** B/C cùng LAN thường cũng **chia sẻ cùng đường WAN của chi nhánh**. Hai luồng A→B, A→C không tự tạo thêm băng thông từ A hoặc WAN của chi nhánh. Chia mảnh có giá trị khi cải thiện truyền tiếp, giảm tải, khả năng chịu lỗi hoặc tận dụng đường truyền độc lập; có lúc **Gateway đơn** lại tốt hơn.

## 3. Yêu cầu chức năng theo giai đoạn

Mục 8 xác định phạm vi nghiệm thu từng giai đoạn. MVP ưu tiên F1, F2, F5 và F6 ở mức cơ bản. F3 và F4 được triển khai ở giai đoạn điều phối thích ứng.

### F1. Phân phối file theo piece/batch có khả năng xác minh

- Cắt file logic thành **piece kích thước cố định** (gợi ý ban đầu: **4 MiB**) để đánh địa chỉ, băm và theo dõi.
- Gom nhiều piece thành **batch truyền qua Croc** (gợi ý ban đầu: **32–128 MiB**, phải benchmark rồi hiệu chỉnh).
- Mỗi piece/batch có định danh, offset, kích thước, hash; có manifest toàn file và SHA-256 toàn file.
- Piece/batch phải được **lưu bền vững và kiểm tra hash thành công** trước khi công bố là *AVAILABLE* cho peer khác.
- Không mở một phiên Croc cho mỗi piece quá nhỏ; giới hạn số phiên đồng thời để tránh overhead.

### F2. Pipelined Full-Duplex Transfer — vừa nhận vừa truyền

- B/C có thể chạy **nhiều luồng RX/TX đồng thời** trong giới hạn thiết bị: RX từ A, TX cho peer khác, RX/TX nội bộ LAN.
- Batch vừa xác minh được phát thông báo khả dụng và có thể được Scheduler giao chuyển tiếp **ngay**, không đợi hoàn thành file hoặc phần nhiệm vụ được giao trước đó.
- Triển khai MVP ở mức **batch pipeline**: nhận xong một batch → xác minh → chia sẻ, trong khi batch tiếp theo vẫn đang nhận. **Không hứa streaming từng byte** qua Croc CLI.
- Có **backpressure**: nếu disk, CPU, Wi-Fi, WAN hoặc hàng đợi quá tải, giảm/hoãn các lượt chuyển tiếp.

### F3. Topology-Aware Delivery — chọn đường theo cấu trúc mạng

- Phân biệt các nhóm peer có kết nối LAN khả dụng, liên kết WAN và các peer remote.
- Đo **goodput thực tế** (không chỉ đo ping hoặc dùng tốc độ card mạng). Kiểm tra LAN trực tiếp; không suy ra LAN chỉ từ tên Wi-Fi hoặc IP riêng.
- Ở giai đoạn điều phối thích ứng, đánh giá ba chiến lược: **Direct** (A→từng người), **Gateway** (A→một cache/peer rồi chia sẻ), **Collaborative Swarm** (A đưa các phần khác nhau tới nhiều peer, các peer trao đổi và hỗ trợ người khác).
- Khi bổ sung tự chọn chiến lược, so sánh **ETA dự kiến của toàn bộ nhóm** và chi phí, tránh ép chia mảnh nếu tất cả đi qua một WAN nghẽn hoặc Wi-Fi AP bị tranh chấp.

### F4. Load-Aware Scheduling & Dynamic Assignment

- Mỗi Agent báo cáo định kỳ: goodput RX/TX gần đây, số phiên đang mở, hàng đợi, tải thiết bị, giới hạn upload/download cho phép, trạng thái lưu trữ, các batch đã có.
- Nếu B rảnh tài nguyên **ngay cả khi đang nhận dữ liệu**, Scheduler có thể giao thêm batch còn thiếu hoặc thêm tác vụ chuyển tiếp có ích.
- Không gán việc trùng không cần thiết: mỗi nhiệm vụ có `assignment_id`, thời hạn (`lease`) và trạng thái; tác vụ dự phòng (nếu chủ động bật) phải được đánh dấu riêng và không tranh chấp với tác vụ giao dữ liệu cho người nhận còn thiếu.
- Ưu tiên chuyển batch **đã có ở gần người nhận qua LAN** thay vì yêu cầu A truyền trùng qua WAN, nếu lợi ích đo được tốt hơn.
- Cơ chế *hysteresis/cooldown* tránh thay đổi phân công liên tục gây dao động (*thrashing*).

### F5. Availability-Aware Fault Recovery — phục hồi không nhân bản bắt buộc

- Lưu **piece-availability bitmap** theo từng peer; theo dõi `AVAILABLE` / `IN_FLIGHT` / `MISSING` / `CORRUPT`, nguồn hiện có và trạng thái xác minh.
- **Mặc định không yêu cầu hai bản sao cho mỗi piece.** Nút nào còn thiếu piece thì việc truyền piece đến nút đó là **phân phối hữu ích**, không coi là nhân bản dự phòng dư thừa.
- Khi B đã có một batch và C/D còn thiếu, B được phép chuyển tiếp ngay nếu có lợi về makespan và trong hạn mức tài nguyên. Không đợi B tải xong hoặc ép một lần nhân bản khác trước khi gửi cho người cần.
- **Nhân bản dự phòng chủ động** (gửi thêm piece tới một nút lưu trữ/cache không cần piece đó để hoàn thành nhiệm vụ nhận file, chỉ nhằm tăng số bản lưu) **mặc định tắt**. Chỉ cân nhắc khi có băng thông, CPU, disk và số phiên rảnh, không làm tăng đáng kể thời gian hoàn thành dự kiến; hoặc khi bật chế độ chịu lỗi riêng. Nếu dư tài nguyên không có nghĩa là bắt buộc nhân bản.
- Nếu C offline và dữ liệu chỉ còn ở A, Scheduler lấy lại đúng phần cần từ A; nếu B/D đã có thì chọn nguồn phù hợp. **Không truyền lại những piece đã xác minh tại người nhận.**
- Khi máy quay lại, Agent đối chiếu trạng thái thật từ disk và manifest để tiếp tục; không tin tuyệt đối vào phần trăm tiến độ trước khi ngắt.
- File hoàn tất khi **tất cả piece hợp lệ có mặt và hash toàn file khớp**.

### F6. Verified Delivery & Audit

- Ghi nhận người nhận nào đã xác minh thành công file, phiên bản/hash, thời gian và nguồn các batch (để debug và đánh giá).
- Không đánh đồng "đã chuyển hết byte" với "người nhận đã lưu và xác minh xong".
- Mở rộng tùy chọn: chữ ký số Ed25519 cho manifest gốc; người nhận xác thực nguồn phát hành độc lập với các peer trung gian.

## 4. Thuật toán trọng tâm: PLARS

**PLARS — Pipelined, Load-Aware & Replication-Aware Scheduler**.

### Mục tiêu

Với các người nhận đích `R`, thời điểm `T_r` mà người nhận `r` hoàn tất và xác minh file:

```text
Minimize T_all = max(T_r),  r ∈ R
```

Theo các ràng buộc:

- Upload/download/CPU/disk không vượt **ngân sách tài nguyên** được cấu hình cho từng peer.
- Từng tuyến LAN/WAN có thông lượng thực tế; phải xét **nút nghẽn chung** (A uplink, WAN chi nhánh, Wi-Fi AP, relay).
- Chỉ truyền những piece mà người gửi đã xác minh; tránh giao trùng không cần thiết.
- **Không có ngưỡng số bản sao tối thiểu ở chế độ mặc định.** Nếu người dùng chủ động bật SafeExit/chịu lỗi có điều kiện, áp dụng ngưỡng tương ứng và công khai chi phí hiệu năng.

**Mục tiêu phụ/tie-break:** giảm byte upload từ A, giảm lưu lượng WAN, cân bằng phần trăm tài nguyên sử dụng; **không bắt mọi peer upload bằng số GB nhau**. Nhân bản dự phòng không nằm trong mục tiêu mặc định; chỉ kích hoạt có điều kiện khi dư năng lực mà không ảnh hưởng đáng kể đến makespan.

### Vòng lập lịch đề xuất

```text
Mỗi khi có sự kiện (batch hoàn tất, peer online/offline, thay đổi tốc độ),
hoặc theo chu kỳ ngắn:
    1. Thu thập bitmap các batch đã xác minh, goodput và tải hiện tại.
    2. Xác định những người nhận còn thiếu và ước lượng T_all nếu giữ lịch hiện tại.
    3. Tạo tập tác vụ khả thi: (source_peer, target_peer, batch),
       chỉ từ source đã có batch, đường truyền được phép, tài nguyên còn đủ.
    4. Xếp hạng tác vụ theo lợi ích dự kiến đối với T_all,
       có xét tranh chấp băng thông, chi phí WAN và upload của A.
       Chỉ đưa tác vụ nhân bản DỰ PHÒNG vào khi còn năng lực dư và phù hợp chính sách.
    5. Giao một số tác vụ tốt nhất; giới hạn phiên và giữ lease để tránh trùng.
    6. Khi ACK sau xác minh: cập nhật bitmap, lập tức cho phép chuyển tiếp.
    7. Khi timeout/offline: thu hồi tác vụ, tính lại và chuyển việc sang peer khác.
    8. Chỉ đổi kế hoạch khi lợi ích vượt ngưỡng để tránh dao động.
```

**Heuristic MVP:** `ETA = kích thước batch / goodput dự kiến + overhead thiết lập + thời gian chờ`; kết hợp ngân sách băng thông và **nhu cầu thực tế của người nhận** (piece nào còn thiếu). Không ưu tiên tạo bản sao chỉ vì piece đang hiếm. Đây chỉ là ước lượng ban đầu, không thay thế benchmark; phải cập nhật theo EWMA và tránh cộng tốc độ của các luồng cùng chung bottleneck.

### Quy tắc ra quyết định quan trọng

1. **Cùng LAN ≠ luôn chia 50/50:** Nếu B là gateway tốt và LAN nhanh, chọn Gateway; nếu B/C có thể giúp các đích khác nhanh hơn, chọn Collaborative Swarm.
2. **Pipeline luôn sẵn sàng, truyền tiếp có điều kiện:** Sau khi B xác minh batch, có thể gửi ngay cho C/D **đang thiếu batch đó** nếu còn ngân sách tài nguyên và giúp cải thiện ETA; không cần nhân bản dự phòng trước.
3. **Phân công động không cần đợi task gốc hoàn tất:** Khi B còn dư download, B có thể nhận thêm batch dù đang RX từ A và TX sang C/D.
4. **D có thể nhận đa nguồn:** Chỉ chia các batch khác nhau giữa A/B/C khi tổng hiệu quả cao hơn một nguồn; không yêu cầu D nhận qua B/C nếu A→D nhanh hơn.
5. **Phân biệt phân phối với nhân bản dự phòng:** B→C khi C còn thiếu là truyền hữu ích; gửi thêm một bản cho peer đã có dữ liệu chỉ để lưu dự phòng là overhead. **Mặc định không nhân bản dự phòng**, kể cả khi truyền qua LAN rất nhanh. Chỉ cân nhắc sử dụng tài nguyên thật sự nhàn rỗi; ngừng nếu làm chậm đường truyền chính.

**Quy tắc triển khai lịch động ban đầu:** Khai báo nhóm LAN/WAN và uplink dùng chung bằng cấu hình. Đo goodput theo cặp và theo loại đường truyền. Với liên kết chưa có mẫu, dùng giá trị cấu hình bảo thủ hoặc đo thử, rồi cập nhật bằng EWMA. Chỉ xét tác vụ còn slot RX/TX và còn ngân sách trên liên kết dùng chung. Ưu tiên người nhận có ETA hoàn thành cao nhất, sau đó chọn nguồn có ETA giao batch thấp nhất. Khi ETA gần nhau, ưu tiên ít byte WAN hơn, rồi ít byte từ A hơn. Giữ phiên đang chạy trừ khi lỗi hoặc hết hạn do mất tiến độ. Giao thêm batch chưa chạy khi peer còn slot; chỉ đưa cơ chế giành lại việc đang chờ vào sau nếu đo được lợi ích.

## 5. SafeExit — chế độ tùy chọn, không ép nhân bản mặc định

Trong **chế độ truyền nhanh mặc định**, A không được báo "có thể rời mạng an toàn khi một peer bất ngờ hỏng" nếu chưa có đủ dữ liệu ngoài A. **Không nhân bản toàn bộ piece hai lần chỉ để đạt SafeExit.**

Nếu người dùng **chủ động bật SafeExit**:

- **Chỉ rời mạng, không cam kết chịu lỗi peer:** Mỗi piece cần có ít nhất một bản đã lưu, xác minh và ACK ở một peer ngoài A. Nếu peer đó cũng rời mạng sau đó, tiến trình có thể đình trệ.
- **Rời mạng và chịu được một peer hỏng:** Mỗi piece cần tối thiểu hai bản sao trên **hai peer độc lập ngoài A**; đây là yêu cầu của chế độ chịu lỗi mạnh, **không phải chính sách chung**. Nếu bảo vệ trước sự cố cả chi nhánh thì các bản sao phải nằm ở các *fault domain* khác nhau.
- Khi băng thông còn dư, Scheduler có thể tạo các bản sao còn thiếu cho mục tiêu SafeExit; nếu không đủ băng thông, báo **chưa đạt điều kiện**, không tự hy sinh makespan một cách âm thầm.
- SafeExit không bảo đảm mọi người hoàn tất ngay khi A tắt; thời gian tiếp tục còn phụ thuộc peer giữ dữ liệu, mạng và tài nguyên.

**SafeExit nằm ngoài MVP; lựa chọn không bật SafeExit không ảnh hưởng các yêu cầu truyền liên tục, phân công động và phục hồi khi A còn online.**

## 6. Kiến trúc và đóng gói Ratatoss Node

Mỗi máy cài cùng một ứng dụng **Ratatoss Node**. Bản đóng gói có thể khác theo hệ điều hành, nhưng cùng chức năng, giao thức và giao diện. Mỗi node có thể tạo job gửi, nhận job hoặc vừa nhận vừa chuyển tiếp. Vai trò do từng job và từng lần truyền quyết định. Máy đã nhận đủ vẫn có thể chuyển tiếp các batch đã xác minh cho đến khi job kết thúc hoặc người dùng dừng node.

### 6.1. Một ứng dụng, giao diện web chạy tại máy

- Bấm chạy ứng dụng để khởi động agent và tự mở `http://127.0.0.1:<port>`. Agent phục vụ cả giao diện và API local trên cùng địa chỉ loopback. Agent quản lý file, trạng thái và tiến trình croc. Đóng tab vẫn truyền nếu agent đang chạy. Thoát agent sẽ dừng các phiên của máy đó và giữ dữ liệu đã xác minh.
- MVP dùng FastAPI phục vụ HTML/CSS/JS tĩnh. Mỗi máy dùng cùng các màn hình **Gửi**, **Nhận** và **Tiến độ**. Chuẩn bị một gói chạy trên hệ điều hành dùng khi demo, có kèm croc đã ghim phiên bản hoặc kiểm tra rõ phiên bản phụ thuộc khi khởi động.
- **Gửi:** Chọn file, tạo job và sao chép lời mời. Người gửi xem các máy đã tham gia và máy nào đã xác minh xong. Với bộ chọn file trong trình duyệt, nội dung được đưa vào vùng lưu trữ của agent qua loopback. Ghi theo luồng, kiểm tra dung lượng trước, rồi dọn dữ liệu tạm theo vòng đời job.
- **Nhận:** Dán lời mời, xem tên, dung lượng và vị trí lưu rồi xác nhận. Tiến độ hiển thị các trạng thái đang nhận, đang chuyển tiếp, mất kết nối và đã xác minh. Agent tự gửi tiếp batch khi được giao và còn trong hạn mức.
- Lời mời Ratatoss chứa địa chỉ controller và thông tin tham gia giới hạn theo job. Có thời hạn và tránh ghi bí mật vào log. Mã croc được agent dùng riêng cho từng lần truyền.

### 6.2. Kênh điều khiển và đường truyền dữ liệu

- **Demo LAN:** Chạy một controller trên bất kỳ node nào bằng cấu hình riêng. Chỉ cổng điều khiển cần được các máy khác truy cập trong mạng thử nghiệm. Trang web trên từng máy luôn bind loopback. Node chạy controller vẫn có thể gửi hoặc nhận như mọi node khác.
- **Qua Internet:** Dùng controller chung có địa chỉ HTTPS mà các node đều truy cập được. Các agent kết nối ra controller để tham gia job, nhận lịch và báo trạng thái. Phiên croc truyền các batch giữa các agent, trực tiếp hoặc qua relay tùy kết nối. Controller xử lý metadata và lịch truyền. Croc relay phục vụ đường dữ liệu riêng.
- Một job có một controller điều phối. Khả năng gửi và nhận giống nhau giữa các node độc lập với vai trò vận hành controller. Nếu controller ngừng hoạt động, node giữ batch đã xác minh và báo gián đoạn điều phối.

### 6.3. Thành phần và trạng thái

```text
[Ratatoss Node trên mọi máy: Web UI local + Agent Python]
    ├─ Croc transport adapter (gọi CLI; điều phối nhiều phiên độc lập)
    ├─ Local piece store + manifest + hash validation
    ├─ RX/TX workers, giới hạn phiên + tốc độ + queue
    ├─ Peer discovery / kiểm tra kết nối / đo goodput
    └─ Heartbeat + ACK + resume/reconcile state
                  │ Control API / WebSocket
                  ▼
[Controller: FastAPI]
    ├─ Job registry / recipients / network groups
    ├─ Piece/batch availability registry
    ├─ PLARS Scheduler + phân công động + lease/timeouts
    ├─ Recovery policy + optional spare-capacity replication / SafeExit
    └─ SQLite + logs / metrics / dashboard
```

**Quy ước phục hồi:** Mỗi lần thử có `assignment_id` riêng và lease. Chỉ có một lần giao còn hiệu lực cho mỗi `(job, peer nhận, batch)`. ACK lặp không tạo tác dụng phụ. ACK đến muộn có thể cập nhật batch đã xác minh của đúng peer, nhưng chỉ lần giao trùng ID mới được ACK đó chuyển trạng thái. Agent đối chiếu file trên đĩa với manifest khi khởi động lại, giữ phần hợp lệ và bỏ qua tác vụ trùng nếu batch đích đã có. Controller hết lease hoặc mất heartbeat thì giao lại phần thiếu từ nguồn còn giữ batch.

**State machine một batch tại người nhận:**
`MISSING → ASSIGNED → TRANSFERRING → RECEIVED → VERIFIED → AVAILABLE`.
Khi lỗi: `TRANSFERRING → RETRY_PENDING`; hash sai: `RECEIVED → CORRUPT → RETRY_PENDING`. Chỉ `VERIFIED/AVAILABLE` mới được làm nguồn chuyển tiếp.

**API tối thiểu (định hướng):**

- `POST /jobs`: đăng ký file, manifest, danh sách người nhận.
- `POST /peers/register`, `POST /peers/heartbeat`: tham gia mạng và báo trạng thái/tải.
- `GET /peers/{id}/assignments`: nhận việc theo lịch.
- `POST /assignments/{id}/ack`: ACK sau khi ghi và xác minh batch.
- `POST /assignments/{id}/fail`: báo lỗi để điều phối lại.
- `GET /jobs/{id}/status`: tiến độ, makespan dự kiến và kết quả xác minh.

**Cảnh báo thực thi:** Croc cung cấp truyền file bảo mật giữa **từng cặp đầu cuối**, nhưng không có sẵn API piece-level swarm cho cả nhóm. Pipeline bản MVP là **nhiều phiên Croc trên các batch đã hoàn tất**, không phải forward byte-stream giữa chừng. Cần thử overhead tạo phiên, tính ổn định khi nhiều tiến trình Croc đồng thời và khả năng đi đường LAN thực tế. Nếu chi phí Croc quá cao, có thể giữ lớp `TransportAdapter` để thay bằng một transport phù hợp hơn trong bản nghiên cứu mở rộng.

## 7. Mô hình bảo mật và giới hạn

- UI local chỉ bind loopback. Các thao tác thay đổi trạng thái kiểm tra Host, Origin và mã phiên local để trang web khác không thể tự gọi thao tác gửi hoặc nhận.
- Kênh điều khiển dùng HTTPS và thông tin xác thực riêng cho từng agent, giới hạn quyền theo job. Controller kiểm tra agent có quyền đọc hoặc cập nhật đúng lần giao việc. Agent nhận manifest qua kênh đã xác thực và kiểm tra manifest gắn với đúng job. Chỉ cấp mã phiên croc cho hai đầu của lần giao tương ứng và che mã trong log.
- Giả định MVP: controller, nguồn phát và các peer được mời đều đáng tin. Controller tập trung là điểm dừng điều phối nếu mất kết nối. Khôi phục tự động sau sự cố controller thuộc phần mở rộng.

- Croc mã hóa dữ liệu **theo từng phiên giữa sender và receiver**. Khi B giải mã rồi phát tiếp cho D, B có khả năng xem plaintext; **đây không phải mã hóa đầu-cuối xuyên qua mọi hop từ A đến D**.
- Nếu dữ liệu nhạy cảm và peer trung gian **không được phép đọc**, phải **mã hóa payload trước khi chia piece**; chỉ người nhận có quyền mới được giải mã. Đây là tính năng mở rộng, không tự chế giao thức mật mã.
- Chữ ký manifest của A cho phép người nhận kiểm tra nguồn gốc và toàn vẹn; hash một mình **không chứng minh nội dung đúng sự thật**.
- Peer ID giả danh không đồng nghĩa ẩn IP: kết nối trực tiếp vẫn làm lộ địa chỉ endpoint. Che IP cần relay/biện pháp định tuyến phù hợp, có thể làm tăng độ trễ.
- Không đưa blockchain vào MVP; audit log và chữ ký số đủ cho yêu cầu ban đầu.

## 8. Lộ trình triển khai và nghiệm thu

### Giai đoạn 0 — Kiểm chứng croc

- Ghim phiên bản croc và cấu hình relay. Làm adapter tự động gửi, nhận và thu kết quả phiên.
- Thử B vừa nhận từ A vừa gửi cho C. Ghi thời gian thiết lập, goodput và đường dữ liệu trực tiếp hoặc qua relay nếu quan sát được. Ghi “không xác định” nếu thiếu bằng chứng.
- Thử 32, 64 và 128 MiB. Kiểm tra timeout, dừng tiến trình con và xử lý file tạm.

**Nghiệm thu:** Hai phiên chồng lấp ở B, dữ liệu nhận đúng, có số đo để chọn kích thước batch đầu tiên và có ca timeout tái hiện được.

### Giai đoạn 1 — MVP phân phối và phục hồi

- Cài cùng gói Ratatoss Node trên A/B/C/D. Tạo lượt truyền A → B/C/D bằng web local. B và C có liên kết LAN kiểm chứng được. Dùng cấu hình nhóm mạng và lịch truyền cố định có pipeline.
- Dùng manifest, định danh batch, SHA-256 theo piece/batch và toàn file. Chỉ công bố batch sau khi lưu và xác minh. Giới hạn phiên RX/TX, timeout, retry, heartbeat và lease.
- Khi peer rớt mạng, các peer còn online tiếp tục. Lấy batch thiếu từ A hoặc peer còn giữ dữ liệu đã xác minh. Peer quay lại đối chiếu trạng thái đĩa trước khi tiếp tục. Nhân bản dự phòng mặc định tắt.

**Nghiệm thu:** Log cho thấy B gửi một batch đã xác minh trong lúc vẫn nhận batch khác từ A. Ngắt một peer giữa chừng rồi cho kết nối lại. Cả ba người nhận xác minh đúng SHA-256 cuối cùng và không tải lại batch nguyên vẹn đã xác minh tại chính máy mình. Tạo lượt truyền mới từ B và cho A tham gia nhận bằng đúng ứng dụng đã cài. Đóng tab trong lúc truyền rồi mở lại để kiểm tra agent và tiến độ vẫn hoạt động.

### Giai đoạn 2 — Điều phối thích ứng và benchmark

- Bổ sung đo goodput, ngân sách liên kết dùng chung, chọn nguồn theo ETA và phân công động khi còn slot. Kiểm tra trường hợp D nên nhận trực tiếp từ A.
- So sánh Direct, Gateway nguyên file, Gateway pipeline lịch cố định, Fixed Split và Ratatoss lịch động. Chạy lặp trên cùng file, cấu hình croc và giới hạn mạng. Ghi rõ phát hiện khi lịch động chậm hơn.
- Sau khi có số đo, cân nhắc tự chọn giữa Direct, Gateway và Swarm. Dùng ngưỡng cải thiện và cooldown khi đổi kế hoạch.

**Nghiệm thu:** Tái hiện được ít nhất ca WAN chung, peer lệch tốc độ và peer rớt mạng. Báo makespan, byte nguồn upload, byte WAN nếu đo được, thời gian thiết lập và byte truyền lại. Có đối chứng dùng cùng topology và mức đồng thời để đánh giá riêng tác động của lịch động.

### Giai đoạn 3 — Mở rộng có điều kiện

| Hạng mục | Điều kiện nghiệm thu |
|---|---|
| SafeExit tùy chọn và nhân bản cơ hội | Kiểm thử từng mức chịu lỗi. Chỉ báo nguồn có thể rời khi đủ bản sao đã xác minh, đúng phạm vi lỗi đã công bố. Đo chi phí makespan và băng thông riêng so với chế độ mặc định. |
| Khôi phục controller | Khởi động lại controller và đối chiếu trạng thái với các agent. Job tiếp tục mà không báo hoàn tất sai hoặc giao lại batch đích đã xác minh. |
| Tối ưu nâng cao | Đo lợi ích khi D nhận đồng thời từ nhiều nguồn, phát hiện nghẽn tự động hoặc điều chỉnh kích thước batch. So sánh từng thay đổi với lịch động cơ bản. |
| Bảo mật nâng cao | Xác minh chữ ký manifest và bảo vệ payload xuyên các hop khi peer trung gian không được phép đọc. |

## 9. Kiểm thử và benchmark

### Baselines

1. **Direct:** A gửi file riêng từng người nhận.
2. **Gateway:** A gửi nguyên file cho B, B phân phối lại cho C/D.
3. **Fixed Split:** A chia tĩnh 50/50 cho B và C, rồi trao đổi.
4. **Gateway pipeline:** Giữ cùng gateway như baseline 2, chuyển tiếp ngay theo batch đã xác minh, dùng lịch cố định.
5. **Ratatoss PLARS:** Pipeline, chia theo tải, phân công động, recovery.
6. **Nếu còn thời gian:** libtorrent/BitTorrent hoặc Dragonfly (thiết lập cùng môi trường, cùng số peer, tài nguyên và giới hạn).

### Chỉ số

| Metric | Ý nghĩa |
|---|---|
| **Makespan** | Thời điểm người nhận cuối cùng **xác minh đủ file** |
| **Source upload bytes** | Báo riêng payload do A gửi và byte trên mạng nếu đo được. Ghi rõ phương pháp đo và phạm vi interface/relay. |
| **WAN bytes** | Dữ liệu truyền qua từng WAN/relay (không chỉ byte từ A) |
| **Peer utilization** | Băng thông upload/download B/C/D đã sử dụng so với ngân sách |
| **Recovery overhead** | Byte bị truyền lại khi peer mất mạng |
| **Recovery time** | Thời gian từ sự cố đến khi hệ thống tiếp tục có tiến độ |
| **Optional replication overhead** | Byte truyền dư chỉ để lưu dự phòng; kỳ vọng gần 0 khi tắt cơ chế tùy chọn |
| **Transfer setup overhead** | Thời gian và tài nguyên mở các phiên Croc theo batch |

### Tình huống kiểm thử

Giai đoạn 1 nghiệm thu pipeline và phục hồi. Giai đoạn 2 bổ sung các ca đánh giá lịch động, WAN và relay. Case 8 chỉ thực hiện khi triển khai SafeExit.

- **Case 1 — WAN chung nghẽn:** B/C cùng uplink WAN, LAN nhanh. Ratatoss không được giả định hai đường A→B và A→C là độc lập.
- **Case 2 — B/C lệch hiệu năng:** B Ethernet tốt, C Wi-Fi yếu; kiểm tra điều phối tỷ lệ linh hoạt.
- **Case 3 — B tải và chuyển tiếp đồng thời:** A→B vẫn đang chạy trong lúc B→C và B→D bắt đầu; log thời gian chứng minh pipeline có thật.
- **Case 4 — Phân công động:** B còn dư tải, C chậm; B nhận thêm batch khi chưa hoàn thành toàn bộ nhiệm vụ ban đầu.
- **Case 5 — C rớt mạng:** B và D tiếp tục từ các batch đã xác minh; không bắt đầu lại từ 0.
- **Case 6 — LAN nghẽn/Wi-Fi AP bận:** Scheduler không tạo bản sao dự phòng; vẫn ưu tiên truyền cho những người thực sự còn thiếu, hoặc chọn Gateway/Direct nếu tốt hơn.
- **Case 7 — D có đường trực tiếp tốt:** Không ép B/C chuyển tiếp cho D nếu khiến makespan xấu đi.
- **Case 8 — Nguồn A offline (nâng cao, tùy chọn):** Chỉ tuyên bố SafeExit thành công theo đúng cấp độ chịu lỗi được chọn; bật chính sách không được ngầm định trong chế độ truyền thường.
- **Case 9 — Băng thông hạn chế:** Khi mọi đường truyền đang bận, không phát sinh lượt nhân bản dự phòng. Đo makespan và overhead để xác minh chính sách.

**Điều kiện nghiệm thu quan trọng nhất:** Video/log thể hiện **chồng lấp các phiên A→B, A→C, B↔C và (nếu có lợi) B/C→D**. Nếu B chờ nhận xong tất cả trước khi gửi, tính năng pipeline **chưa đạt yêu cầu**.

## 10. Rủi ro và chiến lược giảm thiểu

| Rủi ro | Biện pháp |
|---|---|
| Nhiều phiên Croc tạo overhead lớn | Batch đủ lớn, giới hạn đồng thời, benchmark 32/64/128 MiB |
| Cùng WAN/AP gây tranh chấp | Đo goodput thực tế và nhận biết bottleneck chung; tắt swarm khi không có lợi |
| Scheduler giao trùng hoặc ACK thất lạc | Assignment lease, idempotent ACK, bitmap sau xác minh, reconcile khi reconnect |
| Tốc độ biến động dẫn tới đảo lịch liên tục | EWMA, cooldown, hysteresis, tối thiểu hóa việc hủy transfer đang chạy |
| Mất phần dữ liệu duy nhất khi A offline | Chế độ thường không bảo đảm SafeExit; chế độ tùy chọn chỉ báo đạt sau ACK số bản sao tương ứng chính sách |
| Nhiều nguồn khiến D tốn chi phí ghép | Manifest/offset cố định, kiểm tra hash, hạn mức RX/TX và queue |
| Kỳ vọng vượt đối thủ không thực tế | Chỉ kết luận theo benchmark có cấu hình và điều kiện rõ ràng |

## 11. Phân công triển khai tham khảo (nhóm 4 người)

- **A — Agent & Transport:** Wrapper Croc, RX/TX worker, giới hạn phiên, đo goodput.
- **B — Storage & Recovery:** Manifest, hash, bitmap, ACK, ghép file, khôi phục trạng thái.
- **C — Scheduler:** Topology, load-aware, phân công động, phục hồi và nhân bản dự phòng có điều kiện, thuật toán PLARS.
- **D — Controller & Evaluation:** FastAPI, trạng thái job, dashboard/log, test LAN/WAN, benchmark và báo cáo.

**Mốc triển khai:** Kiểm chứng croc → MVP pipeline và phục hồi → điều phối thích ứng và benchmark → mở rộng theo điều kiện nghiệm thu ở Mục 8.

## 12. Điểm khác biệt và tuyên bố nghiên cứu trung thực

Cơ chế chia file, seeding các piece khác nhau, truyền tiếp khi đang tải, rarest-first và scheduling dựa trên tải **đều có tiền lệ** ở BitTorrent/libtorrent, Dragonfly và các hệ thống đồng bộ dữ liệu. Ratatoss **không tuyên bố phát minh P2P/swarming**.

**Giá trị của dự án:** thiết kế và kiểm chứng **chính sách điều phối kết hợp** topology LAN/WAN + tải tài nguyên + pipeline + phân công động + recovery (nhân bản dự phòng tùy chọn), hướng tới **phân phối file theo yêu cầu** cho một nhóm người nhận, trên nền transport Croc đơn giản.

**Câu hỏi nghiên cứu:**

> Trong mạng LAN/WAN không đồng nhất, một Scheduler kết hợp truyền pipeline, khai thác peer nhàn rỗi và phục hồi khi peer rớt mạng (không ép nhân bản dự phòng) có thể giảm **makespan** và tải máy nguồn, đồng thời giảm chi phí khôi phục sau sự cố, so với Direct, Gateway và Fixed Split trong những điều kiện nào?

**Thành công phải được chứng minh bằng số liệu**, không chỉ bằng việc hệ thống chạy được. Nếu một baseline tốt hơn trong một kịch bản, Ratatoss cần **nhận biết và lựa chọn chiến lược phù hợp** thay vì cố áp dụng một chế độ cho mọi mạng.

## 13. Tài liệu tham khảo kỹ thuật

- Croc — https://github.com/schollz/croc
- libtorrent Features — https://libtorrent.org/features.html
- Dragonfly Scheduler — https://d7y.io/docs/next/operations/architecture/components/scheduler/
- Syncthing — https://docs.syncthing.net/

---

**Một câu chốt để giới thiệu dự án:**

> **Ratatoss** là hệ thống phân phối file P2P nhiều người nhận, cho phép các peer **vừa tải vừa chuyển tiếp các phần đã xác minh**, liên tục nhận thêm việc khi còn băng thông, tự chọn đường truyền dựa trên cấu trúc mạng và tải thực tế, và phục hồi khi một peer mất kết nối — nhằm giúp **tất cả người nhận hoàn thành sớm nhất có thể** mà không đặt toàn bộ gánh nặng lên máy gửi ban đầu.
