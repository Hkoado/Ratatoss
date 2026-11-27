# Bằng chứng nghiệm thu R1.1 · Issue #7

Chạy trên Windows với Python 3.11.9 và SQLite 3.46.0.

```powershell
python -B -m unittest discover -s tests -p test_store.py -v
```

Fixture tổng hợp trong `tests/test_store.py` dùng payload ASCII `abcdefghij`, piece 3 byte và batch 6 byte. Batch 0 chứa `abcdef`, batch 1 chứa `ghij`. SHA-256 của file sau khi ghép là `72399361da6a7754fec986dca5b7cbaf1c810a28ded4abaf56b2106d06cb78b0`. Test cũng dùng vector API `sample.txt` để đối chiếu digest manifest và SHA-256 payload riêng.

Các test dừng tiến trình con tại điểm kiểm tra và mở lại cùng kho Node. Trạng thái trong bảng được kiểm bằng file trên đĩa, truy vấn SQLite và payload outbox.

| Điểm dừng hoặc lỗi được tạo | Quan sát trước khi mở lại hoặc thử lại | Quan sát sau phục hồi |
| --- | --- | --- |
| Trước publish batch | Staging đã xác minh. Batch `MISSING`, chưa có ACK. | Dọn staging, hủy attempt cũ, snapshot rỗng. |
| Sau publish batch, trước commit SQLite | File batch hợp lệ đã có trên đĩa. Batch `MISSING`, chưa có ACK. | Snapshot nhận lại batch 0. Nhận batch 1 rồi ghép qua kho, SHA-256 toàn file khớp fixture. |
| Sau commit batch | Batch `AVAILABLE`, attempt `FINISHED` và ACK cùng tồn tại. | Giữ batch và ACK. Snapshot của boot mới đứng trước ACK. |
| SQLite từ chối ghi ACK | File batch đã publish. Giao dịch rollback, batch vẫn `MISSING` và TX bị chặn. | Thử lại cùng assignment commit batch và ACK cùng lúc. |
| Sau publish file đích rỗng, trước commit delivery | File đích đã có, delivery `PUBLISHING`. | Delivery `PUBLISHED`, outbox có một receipt. |
| Trước publish file đích, sau đó đường dẫn bị chiếm bởi file có cùng nội dung | Delivery `PUBLISHING` và file ghép tạm còn trong staging. | Delivery `PATH_CONFLICT`, giữ file người dùng và các batch, không tạo receipt. |

17 ca kiểm tra kho đã đạt. Các điểm dừng kiểm tra việc tiến trình thoát đột ngột. Ca mất điện và truyền Croc thật chưa chạy trong lượt nghiệm thu này.
