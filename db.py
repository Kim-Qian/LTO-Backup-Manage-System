import sqlite3
from datetime import datetime


class Database:
    def __init__(self, path="lto.db"):
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_core()

    def _init_core(self):
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tapes (
            tape_id       TEXT PRIMARY KEY,
            generation    TEXT,
            encrypted     INTEGER,
            created_at    TEXT,
            used_capacity INTEGER DEFAULT 0,
            description   TEXT
        )
        """)

        # backup_type: 'FULL' | 'INCREMENTAL' | 'N/A' (for non-backup actions)
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            tape_id     TEXT,
            action      TEXT,
            backup_type TEXT DEFAULT 'FULL',
            started_at  TEXT,
            finished_at TEXT,
            status      TEXT,
            iv_hex      TEXT,
            tag_hex     TEXT,
            size        INTEGER
        )
        """)

        # Label definitions
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tape_labels (
            label_name TEXT PRIMARY KEY,
            color      TEXT DEFAULT '#5588cc',
            created_at TEXT
        )
        """)

        # Many-to-many: tape <-> label
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS tape_label_map (
            tape_id    TEXT,
            label_name TEXT,
            PRIMARY KEY (tape_id, label_name),
            FOREIGN KEY (label_name) REFERENCES tape_labels(label_name) ON DELETE CASCADE
        )
        """)

        self.conn.commit()

    def create_tape_tables(self, tape_id):
        # mtime stores the source file's last-modified timestamp (Unix float).
        # Used by incremental backup to detect changes since last run.
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS tape_{tape_id} (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            name      TEXT,
            is_dir    INTEGER,
            size      INTEGER,
            mtime     REAL DEFAULT 0,
            job_id    INTEGER,
            FOREIGN KEY(parent_id) REFERENCES tape_{tape_id}(id)
        )
        """)
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS tape_{tape_id}_info (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        self.conn.commit()

    # ========================
    # JOB METHODS
    # ========================

    def new_job(self, tape_id, action, iv_hex=None, backup_type="FULL"):
        cur = self.conn.execute(
            "INSERT INTO jobs (tape_id, action, backup_type, started_at, status, iv_hex, size) "
            "VALUES (?,?,?,?,?,?,0)",
            (tape_id, action, backup_type, datetime.utcnow().isoformat(), "RUNNING", iv_hex)
        )
        self.conn.commit()
        return cur.lastrowid

    def finish_job(self, job_id, status="SUCCESS", size=0, tag_hex=None):
        self.conn.execute(
            "UPDATE jobs SET finished_at=?, status=?, size=?, tag_hex=? WHERE job_id=?",
            (datetime.utcnow().isoformat(), status, size, tag_hex, job_id)
        )
        self.conn.commit()

    # ========================
    # NODE / FILE INDEX METHODS
    # ========================

    def insert_node(self, tape_id, parent_id, name, is_dir, size, job_id, mtime=0.0):
        cur = self.conn.execute(
            f"INSERT INTO tape_{tape_id} (parent_id,name,is_dir,size,mtime,job_id) "
            f"VALUES (?,?,?,?,?,?)",
            (parent_id, name, is_dir, size, mtime, job_id)
        )
        return cur.lastrowid

    # ========================
    # TAPE CAPACITY METHODS
    # ========================

    def update_used_capacity(self, tape_id, size_increment):
        self.conn.execute(
            "UPDATE tapes SET used_capacity=used_capacity+? WHERE tape_id=?",
            (size_increment, tape_id)
        )
        self.conn.commit()

    def get_used_capacity(self, tape_id):
        cur = self.conn.execute(
            "SELECT used_capacity FROM tapes WHERE tape_id=?", (tape_id,)
        )
        row = cur.fetchone()
        return row[0] if row else 0

    def add_tape(self, tape_id, generation, description, encrypted=False):
        self.conn.execute(
            "INSERT OR REPLACE INTO tapes "
            "(tape_id,generation,encrypted,created_at,used_capacity,description) "
            "VALUES (?,?,?,?,?,?)",
            (tape_id, generation, int(encrypted), datetime.utcnow().isoformat(), 0, description)
        )
        self.conn.commit()
        self.create_tape_tables(tape_id)

    # ========================
    # LABEL METHODS
    # ========================

    def create_label(self, name, color="#5588cc"):
        """Create a new label. Returns True on success, False if name already exists."""
        try:
            self.conn.execute(
                "INSERT INTO tape_labels (label_name, color, created_at) VALUES (?,?,?)",
                (name, color, datetime.utcnow().isoformat())
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_label(self, name):
        """Delete a label and all its tape assignments (cascade)."""
        self.conn.execute("DELETE FROM tape_labels WHERE label_name=?", (name,))
        self.conn.commit()

    def assign_label(self, tape_id, label_name):
        """Assign a label to a tape. Returns False if already assigned."""
        try:
            self.conn.execute(
                "INSERT INTO tape_label_map (tape_id, label_name) VALUES (?,?)",
                (tape_id, label_name)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_label_from_tape(self, tape_id, label_name):
        self.conn.execute(
            "DELETE FROM tape_label_map WHERE tape_id=? AND label_name=?",
            (tape_id, label_name)
        )
        self.conn.commit()

    def get_labels_for_tape(self, tape_id):
        """Returns sorted list of label names assigned to the given tape."""
        rows = self.conn.execute(
            "SELECT label_name FROM tape_label_map WHERE tape_id=? ORDER BY label_name",
            (tape_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def get_tapes_by_label(self, label_name):
        """Returns sorted list of tape_ids that carry the given label."""
        rows = self.conn.execute(
            "SELECT tape_id FROM tape_label_map WHERE label_name=? ORDER BY tape_id",
            (label_name,)
        ).fetchall()
        return [r[0] for r in rows]

    def list_labels(self):
        """Returns list of (label_name, color, tape_count) tuples."""
        return self.conn.execute("""
            SELECT tl.label_name, tl.color, COUNT(tm.tape_id) AS cnt
            FROM tape_labels tl
            LEFT JOIN tape_label_map tm ON tl.label_name = tm.label_name
            GROUP BY tl.label_name
            ORDER BY tl.label_name
        """).fetchall()
