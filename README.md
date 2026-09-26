# TDTU Calendar Bot

Telegram bot hỗ trợ sinh viên TDTU kết nối tài khoản TDTU và Google Calendar, xem lịch học/lịch thi/deadline, đồng bộ dữ liệu và thêm lịch cá nhân bằng Smart Paste.

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
| `/schedule` | Xem lịch học |
| `/deadline` | Xem deadline eLearning |
| `/exam` | Xem lịch thi |
| `/add` | Thêm lịch thủ công |

Người dùng mới chọn **Bắt đầu kết nối**, nhập MSSV/mật khẩu TDTU trong Mini App, sau đó cấp quyền Google Calendar.

## Cấu hình Render

Vào Render → service → **Environment** và cấu hình:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_URL=https://tool-check-tkb-davidnguyen.onrender.com/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=...

SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<service_role_key>
ENCRYPTION_KEY=<fernet_key>

GOOGLE_OAUTH_CLIENT_JSON={...}
GEMINI_API_KEY=...
APP_TIMEZONE=Asia/Ho_Chi_Minh
```

`TELEGRAM_WEBHOOK_URL` phải đúng tuyệt đối với domain production. Sau khi lưu biến môi trường, chọn **Save and deploy**.

Health check:

```text
https://tool-check-tkb-davidnguyen.onrender.com/health
```

## Google OAuth

Trong Google Cloud Console, thêm Authorized redirect URI:

```text
https://tool-check-tkb-davidnguyen.onrender.com/api/setup/google/callback
```

URI phải khớp tuyệt đối, gồm scheme, domain và path.

## Supabase

Chạy toàn bộ nội dung [`schema.sql`](schema.sql) trong Supabase SQL Editor trước khi cho người dùng kết nối bot.

`SUPABASE_KEY` trên Render phải là service-role key vì bot cần truy cập bảng người dùng phía server. Không đưa key này vào frontend hoặc commit vào Git.

## Chạy local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Điền các biến trong `.env`, sau đó chạy webhook:

```bash
./start.sh
```

Chạy đồng bộ thủ công cho toàn bộ user:

```bash
python run_hour.py --morning
```

## GitHub Actions

- `Python tests`: chạy compile và toàn bộ test suite khi push hoặc mở pull request.
- `Morning Schedule Sync`: chạy `python run_hour.py --morning` theo lịch 05:00 giờ Việt Nam và khi bấm thủ công.
- `Keep Render Awake`: gọi `/health` định kỳ để hạn chế service free bị ngủ.

Workflow morning cần các GitHub Secrets:

```text
SUPABASE_URL
SUPABASE_KEY
ENCRYPTION_KEY
GOOGLE_OAUTH_CLIENT_JSON
TELEGRAM_BOT_TOKEN
```

## Kiểm tra

```bash
python -m pytest -q
python -m compileall -q .
```

Playwright cần có Chromium:

```bash
playwright install chromium
```

## Bảo mật

- Không commit `.env`, OAuth client secret, service-account JSON hoặc token.
- Mật khẩu TDTU và Google refresh token được mã hóa bằng `ENCRYPTION_KEY` trước khi lưu Supabase.
- Không dùng `GOOGLE_CALENDAR_ID=primary`; Google OAuth sẽ tạo/chọn Calendar riêng cho từng user.
- Khi secret bị lộ, rotate ngay trên Telegram, Google Cloud, Supabase hoặc Render tương ứng.
