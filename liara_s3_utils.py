import logging
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError

logger = logging.getLogger(__name__)

def get_s3_client(access_key, secret_key, endpoint_url, region_name=None):
    """ایجاد یک کلاینت S3 برای اتصال به لیارا یا هر سرویس S3 compatible"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            config=Config(signature_version='s3v4'),
            region_name=region_name if region_name else None
        )
        return s3_client
    except (NoCredentialsError, PartialCredentialsError) as e:
        logger.error(f"خطا در اطلاعات ورود به S3: {e}")
    except ClientError as e:
        logger.error(f"خطای کلاینت S3: {e}")
    except Exception as e:
        logger.error(f"خطای ناشناخته در اتصال به S3: {e}")
    return None

def list_files(s3_client, bucket_name):
    """لیست کردن فایل‌های داخل یک باکت"""
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        files = []
        if 'Contents' in response:
            for item in response['Contents']:
                files.append({'name': item['Key'], 'size': item['Size']})
        return files
    except ClientError as e:
        logger.error(f"خطا در لیست کردن فایل‌ها از باکت {bucket_name}: {e}")
        return []

def delete_file(s3_client, bucket_name, file_key):
    """حذف یک فایل از باکت"""
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_key)
        logger.info(f"فایل {file_key} از باکت {bucket_name} حذف شد.")
        return True
    except ClientError as e:
        logger.error(f"خطا در حذف فایل {file_key} از باکت {bucket_name}: {e}")
        return False

def rename_file(s3_client, bucket_name, old_file_key, new_file_key):
    """تغییر نام یک فایل (کپی و حذف)"""
    try:
        copy_source = {'Bucket': bucket_name, 'Key': old_file_key}
        s3_client.copy_object(CopySource=copy_source, Bucket=bucket_name, Key=new_file_key)
        s3_client.delete_object(Bucket=bucket_name, Key=old_file_key)
        logger.info(f"فایل {old_file_key} با موفقیت به {new_file_key} تغییر نام یافت.")
        return True
    except ClientError as e:
        logger.error(f"خطا در تغییر نام فایل {old_file_key} به {new_file_key}: {e}")
        return False

def get_download_link(s3_client, bucket_name, file_key, expiration=3600):
    """ایجاد لینک دانلود موقت برای یک فایل"""
    try:
        response = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': file_key},
            ExpiresIn=expiration
        )
        return response
    except ClientError as e:
        logger.error(f"خطا در ایجاد لینک دانلود برای {file_key}: {e}")
        return None

def get_bucket_usage(s3_client, bucket_name, server_capacity_gb):
    """محاسبه فضای استفاده شده و خالی باکت"""
    files = list_files(s3_client, bucket_name)
    total_size_bytes = sum(file['size'] for file in files)
    total_size_gb = total_size_bytes / (1024**3)
    free_space_gb = server_capacity_gb - total_size_gb

    return {
        "used_gb": round(total_size_gb, 2),
        "free_gb": round(free_space_gb, 2),
        "total_gb": server_capacity_gb,
        "file_count": len(files)
    }
