import sqlite3
from datetime import datetime

class Database:
    def __init__(self, path="lto.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_core()

    def _init_core(self):
        # Modified: Added 'description' column
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tapes (
            tape_id TEXT PRIMARY KEY,
            generation TEXT,
            encrypted INTEGER,
            created_at TEXT,
            used_capacity INTEGER DEFAULT 0,
            description TEXT
        )
        """)
        
        # Modified: Removed 'offset', rely on filename derived from job_id
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tape_id TEXT,
            action TEXT,
            started_at TEXT,
            finished_at TEXT,
            status TEXT,
            iv_hex TEXT,
            tag_hex TEXT,
            size INTEGER
        )
        """)
        self.conn.commit()

    def create_tape_tables(self, tape_id):
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS tape_{tape_id} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name TEXT,
            is_dir INTEGER,
            size INTEGER,
            job_id INTEGER,
            FOREIGN KEY(parent_id) REFERENCES tape_{tape_id}(id)
        )
        """)
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS tape_{tape_id}_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        self.conn.commit()

    def new_job(self, tape_id, action, iv_hex=None):
        cur = self.conn.execute(
            "INSERT INTO jobs (tape_id, action, started_at, status, iv_hex, size) VALUES (?,?,?,?,?,0)",
            (tape_id, action, datetime.utcnow().isoformat(), "RUNNING", iv_hex)
        )
        self.conn.commit()
        return cur.lastrowid

    # Modified: removed offset parameter
    def finish_job(self, job_id, status="SUCCESS", size=0, tag_hex=None):
        self.conn.execute(
            "UPDATE jobs SET finished_at=?, status=?, size=?, tag_hex=? WHERE job_id=?",
            (datetime.utcnow().isoformat(), status, size, tag_hex, job_id)
        )
        self.conn.commit()

    def insert_node(self, tape_id, parent_id, name, is_dir, size, job_id):
        cur = self.conn.execute(
            f"INSERT INTO tape_{tape_id} (parent_id,name,is_dir,size,job_id) VALUES (?,?,?,?,?)",
            (parent_id, name, is_dir, size, job_id)
        )
        return cur.lastrowid

    def update_used_capacity(self, tape_id, size_increment):
        self.conn.execute(
            "UPDATE tapes SET used_capacity=used_capacity+? WHERE tape_id=?",
            (size_increment, tape_id)
        )
        self.conn.commit()

    def get_used_capacity(self, tape_id):
        cur = self.conn.execute("SELECT used_capacity FROM tapes WHERE tape_id=?", (tape_id,))
        row = cur.fetchone()
        return row[0] if row else 0

    # Modified: Added description
    def add_tape(self, tape_id, generation, description, encrypted=False):
        self.conn.execute(
            "INSERT OR REPLACE INTO tapes (tape_id,generation,encrypted,created_at,used_capacity,description) VALUES (?,?,?,?,?,?)",
            (tape_id, generation, int(encrypted), datetime.utcnow().isoformat(), 0, description)
        )
        self.conn.commit()
        self.create_tape_tables(tape_id)