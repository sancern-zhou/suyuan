"""
Conversation Session Manager for supporting continuous dialogue.

Handles multi-turn conversations with context memory, parameter accumulation,
and analysis result persistence for follow-up questions.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import structlog

logger = structlog.get_logger()


class ConversationSession:
    """
    Represents a single conversation session with a user.

    Tracks:
    - Conversation history (user messages + AI responses)
    - Accumulated parameters across multiple turns
    - Analysis results for follow-up questions
    - Pending clarifications
    """

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or str(uuid.uuid4())
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        # Conversation history
        self.history: List[Dict[str, Any]] = []

        # Accumulated parameters from user input
        self.extracted_params: Dict[str, Any] = {
            "location": None,
            "city": None,
            "pollutant": None,
            "start_time": None,
            "end_time": None,
            "scale": "station"  # Default value
        }

        # Analysis result from last successful analysis
        self.analysis_result: Optional[Dict[str, Any]] = None

        # Parameters that need clarification
        self.pending_clarification: Optional[List[str]] = None

        # Current conversation state
        self.state: str = "INITIAL"  # INITIAL, COLLECTING_PARAMS, ANALYZING, COMPLETED

    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add a message to conversation history."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        self.history.append(message)
        self.updated_at = datetime.utcnow()

        logger.info(
            "message_added_to_session",
            session_id=self.session_id,
            role=role,
            content_length=len(content)
        )

    def update_parameters(self, new_params: Dict[str, Any]):
        """
        Merge new parameters with existing ones.

        New parameters override existing ones if not None.
        """
        for key, value in new_params.items():
            if value is not None:
                self.extracted_params[key] = value

        self.updated_at = datetime.utcnow()

        logger.info(
            "parameters_updated",
            session_id=self.session_id,
            updated_params={k: v for k, v in new_params.items() if v is not None}
        )

    def get_missing_parameters(self) -> List[str]:
        """
        Check which required parameters are still missing.

        Required parameters depend on the analysis scale:
        - station level: location, pollutant, start_time, end_time
        - city level: city, pollutant, start_time, end_time

        Returns:
            List of missing parameter names
        """
        scale = self.extracted_params.get("scale", "station")

        # Determine required params based on scale
        if scale == "city":
            required_params = ["city", "pollutant", "start_time", "end_time"]
        else:  # station (default)
            required_params = ["location", "pollutant", "start_time", "end_time"]

        missing = []

        for param in required_params:
            value = self.extracted_params.get(param)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(param)

        return missing

    def is_ready_for_analysis(self) -> bool:
        """Check if we have all required parameters for analysis."""
        return len(self.get_missing_parameters()) == 0

    def set_analysis_result(self, result: Dict[str, Any]):
        """Store the analysis result for follow-up questions."""
        self.analysis_result = result
        self.state = "COMPLETED"
        self.updated_at = datetime.utcnow()

        # DEBUG: Log detailed info about what's being stored
        logger.info(
            "DEBUG_analysis_result_stored",
            session_id=self.session_id,
            result_is_none=result is None,
            result_type=type(result).__name__,
            result_keys=list(result.keys()) if isinstance(result, dict) else None,
            has_comprehensive=bool(result.get("comprehensive_analysis")) if isinstance(result, dict) else False,
            self_analysis_result_is_none=self.analysis_result is None
        )

    def get_context(self) -> Dict[str, Any]:
        """
        Get full context for LLM processing.

        Returns:
            Dictionary with history, current params, and analysis results
        """
        context = {
            "session_id": self.session_id,
            "history": self.history[-10:],  # Last 10 messages for context
            "extracted_params": self.extracted_params,
            "missing_params": self.get_missing_parameters(),
            "has_analysis_result": self.analysis_result is not None,
            "state": self.state
        }

        # DEBUG: Log context being returned
        logger.info(
            "DEBUG_get_context_called",
            session_id=self.session_id,
            has_analysis_result=context["has_analysis_result"],
            analysis_result_is_none=self.analysis_result is None,
            state=self.state,
            history_count=len(context["history"]),
            missing_params=context["missing_params"]
        )

        return context


class ConversationManager:
    """
    Manages multiple conversation sessions.

    In-memory storage for development. For production, consider Redis or database.
    """

    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        logger.info("conversation_manager_initialized")

    def create_session(self) -> ConversationSession:
        """Create a new conversation session."""
        session = ConversationSession()
        self.sessions[session.session_id] = session

        logger.info("session_created", session_id=session.session_id)
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Retrieve an existing session by ID."""
        return self.sessions.get(session_id)

    def get_or_create_session(self, session_id: Optional[str] = None) -> ConversationSession:
        """
        Get existing session or create new one.

        Args:
            session_id: Optional session ID. If None, creates new session.

        Returns:
            ConversationSession instance
        """
        if session_id and session_id in self.sessions:
            session = self.sessions[session_id]
            logger.info("session_retrieved", session_id=session_id)
            return session

        # Create new session
        session = self.create_session()
        return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info("session_deleted", session_id=session_id)
            return True
        return False

    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """
        Remove sessions older than max_age_hours.

        Should be called periodically to prevent memory leaks.
        """
        now = datetime.utcnow()
        expired_sessions = []

        for session_id, session in self.sessions.items():
            age_hours = (now - session.updated_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.delete_session(session_id)

        if expired_sessions:
            logger.info(
                "sessions_cleaned_up",
                count=len(expired_sessions),
                max_age_hours=max_age_hours
            )


# Global conversation manager instance
conversation_manager = ConversationManager()
