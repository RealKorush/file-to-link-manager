import os
from dotenv import load_dotenv

# لود کردن متغیرهای محیطی از فایل .env در صورت وجود
load_dotenv()

# توکن ربات و آیدی ادمین ارشد
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SUPER_ADMIN_USER_ID = int(os.getenv("SUPER_ADMIN_USER_ID", 0))
SERVER_CAPACITY_GB = float(os.getenv("SERVER_CAPACITY_GB", 2.5))

# ساختار سرورهای S3 (می‌توانید سرورهای خود را اینجا تعریف کنید یا از متغیرهای محیطی داینامیک استفاده کنید)
SERVERS = {
    "server1": {
        "access_key": os.getenv("SERVER1_ACCESS_KEY", "YOUR_ACCESS_KEY"),
        "secret_key": os.getenv("SERVER1_SECRET_KEY", "YOUR_SECRET_KEY"),
        "bucket": os.getenv("SERVER1_BUCKET", "YOUR_BUCKET_NAME"),
        "endpoint_url": os.getenv("SERVER1_ENDPOINT", "https://storage.c2.liara.space"),
        "region_name": os.getenv("SERVER1_REGION", "")
    },
    "server2": {
        "access_key": os.getenv("SERVER2_ACCESS_KEY", "YOUR_ACCESS_KEY"),
        "secret_key": os.getenv("SERVER2_SECRET_KEY", "YOUR_SECRET_KEY"),
        "bucket": os.getenv("SERVER2_BUCKET", "YOUR_BUCKET_NAME"),
        "endpoint_url": os.getenv("SERVER2_ENDPOINT", "https://storage.iran.liara.space"),
        "region_name": os.getenv("SERVER2_REGION", "")
    }
    # می‌توانید سرورهای ۳، ۴ و ۵ را هم به همین شکل اضافه کنید...
}
