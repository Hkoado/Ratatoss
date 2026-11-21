# Smoke Croc R0.1 · Issue #5

Nguồn cho ca thử gồm [Brief §8 giai đoạn 0](../../../docs/source/Ratatoss_Project_Brief_v1.3.md#giai-đoạn-0--kiểm-chứng-croc), [backlog R0.1](../../../plan/BACKLOG.md), [runbook cổng 0](../../../docs/experiments.md#cổng-0--transport), [hợp đồng adapter](../../../spec/operations/croc-adapter-runbook.md) và [hồ sơ lab #3](../../../spec/operations/croc-lab.md).

Hai lượt trên commit `ffd9550dfe92d6bd374a8ace50fe649be41dd732` dùng Croc v11.6.5 Windows x64, fixture tổng hợp 32 MiB và ba tiến trình cùng máy. Relay chỉ nghe TCP loopback tại cổng 19009 và 19010. Ngân sách lease trong JSON là cấu hình khóa của smoke. Đường dữ liệu được ghi `unknown` vì chưa thu bộ đếm byte theo interface hoặc relay. [Lượt 1](report.json) · [Lượt 2](../r01-ffd9550-2/report.json)

| Ca | Kết quả ở cả hai lượt |
| --- | --- |
| RX trước TX, TX trước RX | TX/RX trả mã 0. Kích thước và SHA-256 file nhận khớp fixture. |
| RX vắng TX | Hết hạn sau 4,5 giây. Job Object có tiến trình trước khi dừng và còn 0 sau khi dừng. |
| RX có dữ liệu dở | TX bị giới hạn tải lên bằng `--throttleUpload 512k`. Hai đầu hết hạn sau 6 giây. RX đã ghi phần đầu khớp fixture, hash toàn phần dở khác SHA-256 mong đợi. File dở nằm trong staging cách ly và đường dẫn bàn giao chưa tồn tại. |
| Thử lại | Dùng cùng fixture và đường dẫn bàn giao, với ID và mã phiên mới. TX/RX trả mã 0, SHA-256 khớp. Hai file đã xác minh ở các ca trước vẫn khớp hash. |

Báo cáo JSON ghi argv đã lược đường dẫn riêng tư, thời gian UTC và monotonic, mã thoát và số tiến trình trong Job Object. Lần smoke trên commit `edb6a0e` được lưu để đối chiếu. Ở lần đó, bộ kiểm tra RX đã từ chối thư mục probe tạm của Croc. Adapter ở commit kiểm chứng cho phép đúng mẫu probe khi child đang chạy và yêu cầu thư mục biến mất trước khi bàn giao file. [Báo cáo lần lỗi](../r01-edb6a0e/report.json) · [Mã probe ở tag v11.6.5](https://github.com/schollz/croc/blob/v11.6.5/src/receivefs/publication.go#L15-L29)

## Chạy lại

Từ checkout Ratatoss, dùng Windows x64, binary đã kiểm SHA-256 và fixture `a-32mib.bin` theo hồ sơ lab. Chọn đường dẫn tuyệt đối đến thư mục lab có ACL chỉ cho tài khoản lab và quản trị truy cập, trên filesystem hỗ trợ hardlink. Dành riêng hai cổng loopback của profile cho runner.

```powershell
$lab = 'D:\Ratatoss-lab'
$report = Join-Path $lab ("smoke-" + [guid]::NewGuid() + ".json")
python -m scripts.croc_smoke --croc "$lab\pin\croc.exe" --fixture "$lab\fixtures\a-32mib.bin" --work-parent $lab --report $report
python -m unittest discover -s tests
python spec/governance/verify_originals.py
```

Smoke mô phỏng cấp quyền phiên tại hai đầu. Runner cấp mã một lần và mật khẩu relay trong môi trường riêng của child. Các phép đo cổng 0 qua nhiều máy, overlap A→B/B→C và so sánh 32/64/128 MiB thuộc R0.2 và ở trạng thái **chưa chạy**.

## Kiểm lại sau review

Commit `2d6f72c` chạy lại đủ năm ca trên cùng binary, relay và fixture. Profile smoke dự trù 750 ms chờ đầu kia và 200 ms bắt tay. Đầu vào preflight của vai trò mở sau chỉ còn 200 ms bắt tay. Hai khoản này là cấu hình của ca thử. Bộ test hồi quy kiểm thêm phiên còn đủ lease khi setup đã giảm và ca nhận lệnh hủy lúc file đang được kiểm SHA-256. [Báo cáo chạy lại](../r01-2d6f72c/report.json)
