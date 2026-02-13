# LTO-Backup-Manage-System
Enterprise-style LTO tape backup system for Windows (LTFS), with encryption, job tracking, and database recovery.

## 🎞️ LTO Backup & Manage System (Windows / LTFS)

A professional-grade LTO tape backup and management system for Windows, written in Python, designed for real-world archival workflows.

This project provides a job-based, database-driven backup system that uses LTFS to interact with LTO tapes, combining the reliability of tape storage with modern encryption, metadata tracking, and a rich interactive CLI.

### ⚠️ This is not a simple file copy tool.
It is designed as a true tape archive system with recovery, verification, and long-term maintainability in mind.

## ✨ Key Features

### 🧠 Database-driven architecture

SQLite metadata independent from tape data

Full recovery possible from tape alone

### 🎞️ LTFS-based tape access

No raw SCSI commands

Tape mounted as a filesystem (drive letter)

### 🔐 Optional tape-level encryption

Password-derived symmetric key (KDF)

Or RSA public/private key protection

Encrypted filenames & encrypted payloads

### 🌳 Full directory tree reconstruction

Original file paths preserved

Parent-child relationships stored in DB

100% path recovery on restore

### 🧾 Job-based operation model

Every action is a tracked Job

Backup / Restore / Verify / Browse / Recovery

### 🎨 Rich interactive CLI

Colored UI (Rich)

Confirmation steps

Progress bars

Logs & export

### 🛟 Disaster Recovery Mode

Rebuild database purely from tape contents

## 🧩 System Architecture
### 1️⃣ Dual-Track Design (Data vs Metadata)
Component	Purpose
SQLite3 Database	Logical structure, file tree, jobs, encryption info
LTO Tape (LTFS)	Actual compressed & encrypted data

The database does not contain the data itself.
It can be fully rebuilt from tape when needed.

### 2️⃣ Tape Model

Each tape is treated as a logical namespace + physical medium.

Tape ID: 000012L5

Generation auto-mapped:

Capacity

Block size

Recommended compression

Database tables:

tapes

tape_<TAPE_ID>

tape_<TAPE_ID>_info

### 3️⃣ Tree-Based Path Storage (Core Feature)

Every file and directory is a node

Stored with:

parent_id

job_id

(Optional) encrypted filename

Allows perfect reconstruction of original directory structure

### 4️⃣ Encryption Design

When encryption is enabled for a tape:

### 🔑 Symmetric Key

Used to encrypt tape data

256-bit key

### 🔐 Two Unlock Methods

Passphrase (KDF)

User remembers password

Salt stored in DB

RSA Key Pair

Random symmetric key generated

Encrypted with RSA public key

Private key required to unlock

Stored in database:

RSA public key (or KDF salt)

Encrypted symmetric key

SHA-256 hash of symmetric key (validation)

### 5️⃣ Job System

Every operation is a Job:

Add tape

Backup (append write)

Restore

Browse

Verify

Recovery

Each Job records:

Timestamp

Operation type

File count

Original size

Encryption state

Status (SUCCESS / FAILED / INTERRUPTED)

### 6️⃣ Verification & Recovery

verify.py

Automatically detects encrypted vs plain data

Uses AEAD tag (if encrypted) or SHA-256

recovery.py

Rebuilds entire database from tape

Restores file tree & job metadata

## 🖥️ Platform & Requirements

Windows 10 / 11

Python 3.10+

LTFS installed and mounted

LTO tape drive supported by LTFS

Python Dependencies (partial)
pip install rich pycryptodome tqdm pillow pyzbar reportlab customtkinter


Camera barcode scanning requires OpenCV and a working webcam.

## 🚀 Usage
```bash
python main.py
```

Main Menu:

➕ Add Tapes

💾 Backup (Write)

📥 Restore (Read)

📂 Browse Index

🔍 Verify Integrity

🛟 Disaster Recovery

📤 Export Logs

⚠️ Important Notes

This system assumes LTFS handles tape positioning

Tape removal during operations may corrupt the job

Always back up RSA private keys

Database ≠ Data — tape is the source of truth

## 📜 License

MIT License
Use at your own risk. Tape storage is unforgiving — test before production use.

## 🙌 Author

Designed & implemented by Kim Qian
Built for real LTO workflows, not demos.
