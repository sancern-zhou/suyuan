"""
SQLite FTS5 Index for Agent Runs

Full-text search index with trigram tokenizer for Chinese CJK support.
"""

import sqlite3
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class AgentRunsFTSIndex:
    """
    FTS5 index for agent runs logs

    Features:
    - Dual FTS5 tables: unicode61 (English) + trigram (Chinese)
    - Automatic Chinese detection for query routing
    - WAL mode for concurrent access
    - Incremental index updates
    """

    def __init__(self, db_path: str = None):
        """
        Initialize FTS index

        Args:
            db_path: Path to SQLite database (default: backend_data_registry/session_search.db)
        """
        if db_path is None:
            from app.utils.path_config import get_data_registry
            data_dir = get_data_registry()
            db_path = str(data_dir / "session_search.db")

        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._initialized = False

    @property
    def conn(self) -> sqlite3.Connection:
        """Lazy database connection"""
        if self._conn is None:
            self._connect()
        return self._conn

    def _connect(self):
        """Establish database connection with WAL mode"""
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        logger.info("fts_db_connected", db_path=self.db_path)

    def close(self):
        """Close database connection"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def initialize_schema(self):
        """Create FTS5 virtual tables"""
        with self.conn:
            # Default unicode61 table for English
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS agent_runs_fts USING fts5(
                    run_id UNINDEXED,
                    session_id UNINDEXED,
                    content,
                    query,
                    response_preview,
                    start_time UNINDEXED,
                    status UNINDEXED,
                    duration_ms UNINDEXED,
                    tokenize='unicode61 remove_diacritics 2'
                )
            """)

            # Trigram table for Chinese CJK
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS agent_runs_fts_trigram USING fts5(
                    run_id UNINDEXED,
                    session_id UNINDEXED,
                    content,
                    query,
                    response_preview,
                    start_time UNINDEXED,
                    status UNINDEXED,
                    duration_ms UNINDEXED,
                    tokenize='trigram'
                )
            """)

            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS session_runs (
                    run_id TEXT PRIMARY KEY,
                    owner_type TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    session_id TEXT,
                    query TEXT,
                    response_preview TEXT,
                    start_time TEXT,
                    status TEXT,
                    duration_ms REAL,
                    source_path TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_runs_owner_time
                ON session_runs(owner_type, owner_id, start_time DESC)
            """)
            self._conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS session_runs_fts USING fts5(
                    run_id UNINDEXED,
                    owner_type UNINDEXED,
                    owner_id UNINDEXED,
                    session_id UNINDEXED,
                    content,
                    query,
                    response_preview,
                    start_time UNINDEXED,
                    status UNINDEXED,
                    duration_ms UNINDEXED,
                    tokenize='trigram'
                )
            """)

            self._initialized = True
            logger.info("fts_schema_initialized")

    def _contains_cjk(self, text: str) -> bool:
        """
        Check if text contains CJK characters

        CJK ranges:
        - CJK Unified Ideographs: U+4E00-U+9FFF
        - CJK Extension A: U+3400-U+4DBF
        - CJK Extension B: U+20000-U+2A6DF
        - CJK Symbols/Punctuation: U+3000-U+303F
        - Hiragana: U+3040-U+309F
        - Katakana: U+30A0-U+30FF
        - Hangul: U+AC00-U+D7AF
        """
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x309F or
                0x30A0 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF):
                return True
        return False

    def _count_cjk(self, text: str) -> int:
        """Count CJK characters in text"""
        count = 0
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                0x3000 <= cp <= 0x303F or 0x3040 <= cp <= 0x309F or
                0x30A0 <= cp <= 0x30FF or 0xAC00 <= cp <= 0xD7AF):
                count += 1
        return count

    def _escape_fts_query(self, query: str) -> str:
        """
        Escape FTS5 special characters

        Special chars: " ' ( ) * - + < > =
        """
        # Replace double quotes with escaped quotes
        query = query.replace('"', '""')
        return query

    def build_index(self, log_dir: str = None) -> int:
        """
        Build FTS index from agent_runs log files

        Args:
            log_dir: Path to logs/agent_runs directory (default: logs/agent_runs)

        Returns:
            Number of indexed records
        """
        if log_dir is None:
            log_dir = "logs/agent_runs"

        log_path = Path(log_dir)
        if not log_path.exists():
            logger.warning("log_dir_not_found", log_dir=log_dir)
            return 0

        self.initialize_schema()

        indexed_count = 0
        log_files = list(log_path.glob("run_*.json"))

        logger.info("building_fts_index", log_files_count=len(log_files))

        with self.conn:
            for log_file in log_files:
                try:
                    data = json.loads(log_file.read_text(encoding="utf-8"))
                    self._insert_record(data)
                    indexed_count += 1
                except Exception as e:
                    logger.warning(
                        "failed_to_index_log",
                        log_file=str(log_file),
                        error=str(e)
                    )

        logger.info("fts_index_built", indexed_count=indexed_count)
        return indexed_count

    def _record_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract searchable fields from an agent run record."""
        response = data.get("final_answer_preview", "") or data.get("response_preview", "")
        return {
            "run_id": data.get("run_id", ""),
            "session_id": data.get("session_id", ""),
            "query": data.get("query", ""),
            "response_preview": response,
            "start_time": data.get("start_time", ""),
            "status": data.get("status", ""),
            "duration_ms": data.get("stats", {}).get("duration_ms", 0),
            "content": f"{data.get('query', '')} {response}",
        }

    def _insert_record(self, data: Dict[str, Any]):
        """Insert a single record into both FTS tables"""
        fields = self._record_fields(data)

        # Insert into unicode61 table
        self._conn.execute(
            """INSERT OR REPLACE INTO agent_runs_fts
               (run_id, session_id, content, query, response_preview, start_time, status, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["run_id"], fields["session_id"], fields["content"],
                fields["query"], fields["response_preview"], fields["start_time"],
                fields["status"], fields["duration_ms"]
            )
        )

        # Insert into trigram table
        self._conn.execute(
            """INSERT OR REPLACE INTO agent_runs_fts_trigram
               (run_id, session_id, content, query, response_preview, start_time, status, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fields["run_id"], fields["session_id"], fields["content"],
                fields["query"], fields["response_preview"], fields["start_time"],
                fields["status"], fields["duration_ms"]
            )
        )

    def _upsert_scoped_record(
        self,
        data: Dict[str, Any],
        owner_type: str,
        owner_id: str,
        source_path: str = "",
    ):
        """Insert or update a user-scoped run and its FTS row."""
        fields = self._record_fields(data)
        run_id = fields["run_id"]
        if not run_id:
            raise ValueError("run_id is required for scoped session indexing")
        if not owner_type or not owner_id:
            raise ValueError("owner_type and owner_id are required for scoped session indexing")

        updated_at = datetime.utcnow().isoformat()
        self._conn.execute(
            """
            INSERT INTO session_runs (
                run_id, owner_type, owner_id, session_id, query, response_preview,
                start_time, status, duration_ms, source_path, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                owner_type=excluded.owner_type,
                owner_id=excluded.owner_id,
                session_id=excluded.session_id,
                query=excluded.query,
                response_preview=excluded.response_preview,
                start_time=excluded.start_time,
                status=excluded.status,
                duration_ms=excluded.duration_ms,
                source_path=excluded.source_path,
                updated_at=excluded.updated_at
            """,
            (
                run_id, owner_type, owner_id, fields["session_id"], fields["query"],
                fields["response_preview"], fields["start_time"], fields["status"],
                fields["duration_ms"], source_path, updated_at,
            )
        )

        self._conn.execute("DELETE FROM session_runs_fts WHERE run_id = ?", (run_id,))
        self._conn.execute(
            """INSERT INTO session_runs_fts
               (run_id, owner_type, owner_id, session_id, content, query,
                response_preview, start_time, status, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, owner_type, owner_id, fields["session_id"], fields["content"],
                fields["query"], fields["response_preview"], fields["start_time"],
                fields["status"], fields["duration_ms"],
            )
        )

    def add_record(
        self,
        data: Dict[str, Any],
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
        source_path: str = "",
    ):
        """
        Add a new record to the index

        Args:
            data: Agent run data dictionary
        """
        if not self._initialized:
            self.initialize_schema()
        with self.conn:
            if owner_type or owner_id:
                self._upsert_scoped_record(data, owner_type or "", owner_id or "", source_path)
            else:
                self._insert_record(data)

    def search(
        self,
        query: str,
        limit: int = 5,
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search FTS index

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching records with snippet highlights
        """
        if not self._initialized:
            self.initialize_schema()

        query = query.strip()
        if not query:
            return []

        if owner_type or owner_id:
            if not owner_type or not owner_id:
                return []
            return self._search_scoped(query, limit, owner_type, owner_id)

        # Detect CJK and route to appropriate table
        cjk_count = self._count_cjk(query)

        if cjk_count >= 3:
            # Use trigram table for Chinese queries
            results = self._search_trigram(query, limit)
        elif cjk_count > 0:
            # Short CJK queries: use LIKE fallback
            results = self._search_like(query, limit)
        else:
            # Use default unicode61 table for English
            results = self._search_unicode(query, limit)

        return results

    def _search_scoped(
        self,
        query: str,
        limit: int,
        owner_type: str,
        owner_id: str,
    ) -> List[Dict[str, Any]]:
        """Search user-scoped social session runs."""
        if 0 < self._count_cjk(query) < 3:
            return self._search_scoped_like(query, limit, owner_type, owner_id)

        try:
            cursor = self._conn.execute("""
                SELECT
                    run_id, session_id, query, response_preview,
                    start_time, status, duration_ms,
                    bm25(session_runs_fts) AS rank
                FROM session_runs_fts
                WHERE session_runs_fts MATCH ?
                  AND owner_type = ?
                  AND owner_id = ?
                ORDER BY rank
                LIMIT ?
            """, (self._escape_fts_query(query), owner_type, owner_id, limit))
            return [dict(row) for row in cursor.fetchall()]
        except sqlite3.OperationalError:
            return self._search_scoped_like(query, limit, owner_type, owner_id)

    def _search_scoped_like(
        self,
        query: str,
        limit: int,
        owner_type: str,
        owner_id: str,
    ) -> List[Dict[str, Any]]:
        """LIKE fallback for short CJK terms within a scoped owner."""
        cursor = self._conn.execute("""
            SELECT
                run_id, session_id, query, response_preview,
                start_time, status, duration_ms
            FROM session_runs_fts
            WHERE owner_type = ?
              AND owner_id = ?
              AND (query LIKE ? OR response_preview LIKE ?)
            ORDER BY start_time DESC
            LIMIT ?
        """, (owner_type, owner_id, f"%{query}%", f"%{query}%", limit))
        return [dict(row) for row in cursor.fetchall()]

    def _search_unicode(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using default unicode61 table"""
        escaped_query = self._escape_fts_query(query)

        try:
            cursor = self._conn.execute(f"""
                SELECT
                    run_id, session_id, query, response_preview,
                    start_time, status, duration_ms,
                    bm25(agent_runs_fts) AS rank
                FROM agent_runs_fts
                WHERE agent_runs_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (escaped_query, limit))

            return [dict(row) for row in cursor.fetchall()]

        except sqlite3.OperationalError:
            # FTS query syntax error, try simple query
            cursor = self._conn.execute(f"""
                SELECT
                    run_id, session_id, query, response_preview,
                    start_time, status, duration_ms
                FROM agent_runs_fts
                WHERE query LIKE ? OR response_preview LIKE ?
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", limit))

            return [dict(row) for row in cursor.fetchall()]

    def _search_trigram(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Search using trigram table for Chinese"""
        escaped_query = self._escape_fts_query(query)

        try:
            cursor = self._conn.execute(f"""
                SELECT
                    run_id, session_id, query, response_preview,
                    start_time, status, duration_ms,
                    bm25(agent_runs_fts_trigram) AS rank
                FROM agent_runs_fts_trigram
                WHERE agent_runs_fts_trigram MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (escaped_query, limit))

            return [dict(row) for row in cursor.fetchall()]

        except sqlite3.OperationalError:
            # Fallback to LIKE for short queries
            return self._search_like(query, limit)

    def _search_like(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Fallback LIKE search for short CJK queries"""
        cursor = self._conn.execute(f"""
            SELECT
                run_id, session_id, query, response_preview,
                start_time, status, duration_ms
            FROM agent_runs_fts
            WHERE query LIKE ? OR response_preview LIKE ?
            ORDER BY start_time DESC
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        if not self._initialized:
            self.initialize_schema()
        try:
            cursor = self._conn.execute("SELECT COUNT(*) as count FROM agent_runs_fts")
            row = cursor.fetchone()
            total_records = row["count"] if row else 0
        except Exception:
            total_records = 0

        return {
            "total_records": total_records,
            "db_path": self.db_path,
            "initialized": self._initialized
        }


# Global index instance
_global_index: Optional[AgentRunsFTSIndex] = None


def get_fts_index() -> AgentRunsFTSIndex:
    """Get or create global FTS index instance"""
    global _global_index
    if _global_index is None:
        _global_index = AgentRunsFTSIndex()
    return _global_index
