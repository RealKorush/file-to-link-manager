# 📂 Multi-S3 Cloud File Manager Telegram Bot

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg?style=for-the-badge&logo=python&logoColor=white" alt="Python Version">
  <img src="https://img.shields.io/badge/Telegram--Bot-v20.x-cyan.svg?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram Bot">
  <img src="https://img.shields.io/badge/Amazon--S3-Compatible-orange.svg?style=for-the-badge&logo=amazons3&logoColor=white" alt="S3 Compatible">
  <img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License">
</p>

A production-ready Telegram Bot built with Python to manage multiple S3-Compatible object storages (such as Liara, AWS S3, DigitalOcean Spaces) through a highly intuitive, state-managed inline keyboard interface.

---

## 🌍 Language / زبان‌ها
- [English](#-english-documentation)
- [فارسی](#-مستندات-فارسی)

---

## 🇬🇧 English Documentation

### ✨ Features
- 🔐 **Super Admin Restricted:** Secured with dedicated Admin ID filtering to block unauthorized usage.
- 🧠 **Robust State Management:** Powered by Python-telegram-bot's `ConversationHandler` to guarantee stability and prevent bot crashes from unexpected messages or clicks.
- 📊 **Real-time Bucket Analytics:** Instantly calculates total file counts, used space, and free capacity for each bucket based on a configurable total storage limit.
- 🔗 **Presigned URL Generation:** Generates temporary, secure, and time-restricted download links on demand.
- ✏️ **In-place Renaming:** Safely rename remote files on the fly without downloading and re-uploading overhead.
- 🗑️ **Safe Object Deletion:** Implements a two-step confirmation prompt to prevent accidental data loss.
- 🔌 **Environment Variables:** Zero hardcoded credentials. Configuration is entirely based on dynamic environment variables (`.env`).

### 🛠️ Quick Start & Installation

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/RealKorush/file-to-link-manager.git](https://github.com/RealKorush/file-to-link-manager.git)
   cd file-to-link-manager

2. **Install requirements:**
   ```bash
   pip install -r requirements.txt

3. **Configure Environment Variables:**
   ```bash
   cp .env.example .env
4. **Run the Bot:**
   ```bash
   python main.py
   
   Environment Variables Configuration
Variable,Description,Example
BOT_TOKEN,Your Telegram Bot Token from BotFather,7676098241:AAGtvc...
SUPER_ADMIN_USER_ID,Your numeric Telegram User ID,594976861
SERVER_CAPACITY_GB,Storage limit allocated per bucket,2.5
SERVER1_ACCESS_KEY,Access Key of your first S3 Bucket,it9dlgvf7rriu0s1
SERVER1_SECRET_KEY,Secret Key of your first S3 Bucket,04a97537-01a9-458e...
SERVER1_BUCKET,Name of your first S3 bucket,my-bucket-1
SERVER1_ENDPOINT,Endpoint URL of your S3 provider,https://storage.c2.liara.space




