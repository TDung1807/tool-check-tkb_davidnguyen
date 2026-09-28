# TDTU Calendar Bot

Telegram bot hỗ trợ sinh viên TDTU kết nối tài khoản TDTU portal và Google Calendar, xem lịch học/lịch thi/deadline, đồng bộ dữ liệu và thêm lịch cá nhân bằng Smart Paste.

## Kiến trúc hiện tại

```text
Telegram → Render Web Service (FastAPI / webhook_app.py)
                         ├── Supabase: users, sync_snapshots, sync_logs
                         ├── Google OAuth: Calendar riêng cho từng user
                         └── TDTU/eLearning crawler

GitHub Actions → run_hour.py --morning → đồng bộ lịch cho toàn bộ user
```

Google Calendar là nơi lưu trữ lịch. Telegram là giao diện thao tác.

## Tính năng Telegram

| Lệnh | Chức năng |
| --- | --- |
| `/start` | Mở menu và hướng dẫn kết nối |
| `/status` | Xem trạng thái kết nối |
| `/today` | Xem lịch hôm nay |
| `/schedule` | Cào và xem lịch tuần này |
| `/deadline` | Xem deadline eLearning |
| `/exam` | Xem lịch thi |
| `/add` | Thêm lịch thủ công |

Khi chọn **Lịch tuần này** hoặc dùng `/schedule` không kèm ngày, bot sẽ cào toàn bộ
tuần hiện tại từ cổng TDTU, gửi bản xem trước theo từng ngày và hỏi trước khi
đồng bộ tuần đó vào Google Calendar. Luồng tự động lúc 05:00 vẫn tiếp tục kiểm
tra thay đổi và đồng bộ như cũ.

Menu **Cài đặt** gồm:

- **Trạng thái kết nối**: kiểm tra kết nối TDTU, Google Calendar và Smart Paste.
- **Đăng xuất tất cả**: xóa thông tin kết nối TDTU/Google khỏi bot và vô hiệu hóa tài khoản.

Mỗi môn học được hiển thị với ca và giờ theo bảng phân tiết chính thức của TDTU.
Trong luồng tự động 05:00, bot nhận diện thay đổi về môn, giờ, phòng và trạng thái;
sau khi đồng bộ sẽ gửi thông báo chi tiết cho user.

Người dùng mới chọn **Bắt đầu kết nối**, nhập MSSV/mật khẩu TDTU portal trong Mini App, sau đó cấp quyền Google Calendar.



## Bảo mật
- Mật khẩu TDTU portal và Google refresh token được mã hóa thành `ENCRYPTION_KEY` bằng Fernet trước khi lưu Supabase kể cả admin cũng không thể đọc được ở dạng plain text.
- Cam kết không dùng `GOOGLE_CALENDAR_ID=primary`; Google OAuth sẽ tạo/chọn Calendar riêng cho từng user.

## Lưu ý 
**Bot không có giá trị và quyền thay thế hoàn toàn lịch học chính thức trên portal và app TDT student**
**Mọi hành động đăng nhập và cung cấp thông tin đều do người dùng quyết định**

## Bản fork được chỉnh sửa lại từ bản chính với mục đích chính là dễ dùng hơn cho non-tech users.

## Mọi thắc mắc về bản fork này liên hệ về gmail : nguyenntienndungg18@gmail.com
