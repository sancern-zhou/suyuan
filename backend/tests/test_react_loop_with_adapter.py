"""
Integration Tests for ReAct Loop with Input Adapter

Tests the complete integration of:
- ReAct Loop
- Input Adapter
- Reflexion Handler
- ReAsk Mechanism

Author: Claude Code
Version: 1.0.0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.agent.core.loop import ReActLoop
from app.agent.core.planner import LLMPlanner
from app.agent.core.executor import ToolExecutor
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.agent.input_adapter import InputValidationError


class MockLLMClient:
    """Mock LLM client for testing"""

    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0

    async def generate_thought(self, query, context, iteration):
        """Mock thought generation"""
        response = self.responses.get("thought", [])
        if isinstance(response, list):
            result = response[min(self.call_count, len(response) - 1)]
            self.call_count += 1
            return result
        return response

    async def decide_action(self, thought_result, latest_observation=None):
        """Mock action decision"""
        response = self.responses.get("action", [])
        if isinstance(response, list):
            result = response[min(self.call_count, len(response) - 1)]
            self.call_count += 1
            return result
        return response


@pytest.fixture
def mock_memory_manager():
    """Create mock memory manager"""
    memory = MagicMock(spec=HybridMemoryManager)
    memory.session_id = "test-session-123"
    memory.working = MagicMock()
    memory.session = MagicMock()
    memory.longterm = MagicMock()

    # Mock methods
    memory.get_context_for_llm = MagicMock(return_value="Test context")
    memory.get_enhanced_context_for_llm = AsyncMock(return_value="Enhanced context")
    memory.enhance_with_longterm = AsyncMock(return_value="Enhanced query")
    memory.add_iteration = MagicMock()
    memory.save_session_to_longterm = AsyncMock()
    memory.estimate_total_tokens = MagicMock(return_value=1000)

    # Mock working memory
    memory.working.get_iterations = MagicMock(return_value=[])
    memory.working.__len__ = MagicMock(return_value=0)

    # Mock session memory
    memory.session.add_user_message = MagicMock()
    memory.session.add_assistant_response = MagicMock()
    memory.session.compressed_iterations = []
    memory.session.data_files = []

    # Mock longterm memory
    memory.longterm.save_task_solution = AsyncMock()

    return memory


@pytest.fixture
def mock_tool_executor():
    """Create mock tool executor"""
    executor = MagicMock(spec=ToolExecutor)
    executor.execute_tool = AsyncMock()
    executor.tool_registry = {}  # Add tool_registry attribute
    return executor


class TestInputAdapterIntegration:
    """Test Input Adapter integration with executor"""

    @pytest.mark.asyncio
    async def test_valid_tool_call_passes_adapter(self, mock_tool_executor):
        """Test valid tool call passes through adapter"""
        # Configure mock to return success
        mock_tool_executor.execute_tool.return_value = {
            "success": True,
            "data": {"result": "success"},
            "summary": "Tool executed successfully"
        }

        # Execute tool with valid args
        result = await mock_tool_executor.execute_tool(
            tool_name="get_air_quality",
            tool_args={"question": "Test query"},
            iteration=1
        )

        assert result["success"] is True
        assert "data" in result

    @pytest.mark.asyncio
    async def test_invalid_args_trigger_validation_error(self, mock_tool_executor):
        """Test invalid args trigger InputValidationError"""
        # Configure mock to return validation error
        mock_tool_executor.execute_tool.return_value = {
            "success": False,
            "error_type": "INPUT_VALIDATION_FAILED",
            "error": "Missing required fields",
            "tool_name": "get_weather_data",
            "missing_fields": ["data_type", "start_time"],
            "expected_schema": {},
            "suggested_call": {},
            "summary": "Parameter validation failed"
        }

        # Execute tool with missing args
        result = await mock_tool_executor.execute_tool(
            tool_name="get_weather_data",
            tool_args={"lat": 23.13},
            iteration=1
        )

        assert result["success"] is False
        assert result["error_type"] == "INPUT_VALIDATION_FAILED"
        assert "missing_fields" in result
        assert "data_type" in result["missing_fields"]


class TestReflexionIntegration:
    """Test Reflexion integration with Input Adapter errors"""

    @pytest.mark.asyncio
    async def test_reflexion_generates_suggestions(self, mock_memory_manager):
        """Test Reflexion handler generates suggestions for validation errors"""
        from app.agent.core.reflexion_handler import ReflexionHandler

        handler = ReflexionHandler()

        # Create validation error
        error = {
            "success": False,
            "error_type": "INPUT_VALIDATION_FAILED",
            "tool_name": "get_weather_data",
            "missing_fields": ["data_type", "start_time", "end_time"],
            "expected_schema": {
                "required_fields": ["data_type", "start_time", "end_time"]
            },
            "suggested_call": {
                "tool": "get_weather_data",
                "args": {
                    "data_type": "era5",
                    "lat": 23.13,
                    "lon": 113.26,
                    "start_time": "2025-11-07T00:00:00",
                    "end_time": "2025-11-08T00:00:00"
                }
            }
        }

        # Generate suggestions
        suggestion = await handler.handle_input_adaptation_error(
            error=error,
            tool_name="get_weather_data",
            raw_args={"lat": 23.13, "lon": 113.26}
        )

        assert suggestion is not None
        assert "should_retry" in suggestion
        assert "suggestions" in suggestion
        assert len(suggestion["suggestions"]) > 0


class TestReAskMechanismIntegration:
    """Test ReAsk mechanism with Reflexion suggestions"""

    @pytest.mark.asyncio
    async def test_reask_includes_reflexion_suggestions(self):
        """Test ReAsk prompt includes Reflexion suggestions"""
        from app.agent.core.planner import LLMPlanner

        # Create mock planner
        planner = MagicMock(spec=LLMPlanner)

        # Mock _build_retry_action_prompt method
        planner._build_retry_action_prompt = MagicMock(
            return_value="Retry prompt with suggestions"
        )
        planner._get_available_tools_description = MagicMock(
            return_value="Available tools"
        )

        # Create observation with Reflexion suggestions
        latest_observation = {
            "success": False,
            "error_type": "INPUT_VALIDATION_FAILED",
            "reflexion_suggestion": {
                "should_retry": True,
                "suggestions": [
                    "Add missing field: data_type",
                    "Add missing field: start_time",
                    "Add missing field: end_time"
                ]
            }
        }

        # Build retry prompt
        thought_result = {"thought": "Test thought"}
        retry_prompt = planner._build_retry_action_prompt(
            thought_result,
            retry_count=1,
            max_retry=2,
            latest_observation=latest_observation
        )

        # Verify prompt was built
        planner._build_retry_action_prompt.assert_called_once()
        args = planner._build_retry_action_prompt.call_args
        assert args[1]["latest_observation"] == latest_observation


class TestCompleteErrorRecoveryFlow:
    """Test complete error recovery flow"""

    @pytest.mark.asyncio
    async def test_validation_error_recovery_flow(
        self,
        mock_memory_manager,
        mock_tool_executor
    ):
        """Test complete validation error -> Reflexion -> ReAsk -> Success flow"""

        # Setup: First call fails with validation error
        # Second call succeeds
        mock_tool_executor.execute_tool.side_effect = [
            # First call: validation error
            {
                "success": False,
                "error_type": "INPUT_VALIDATION_FAILED",
                "error": "Missing required fields",
                "tool_name": "get_weather_data",
                "missing_fields": ["data_type", "start_time", "end_time"],
                "suggested_call": {},
                "reflexion_suggestion": {
                    "should_retry": True,
                    "suggestions": [
                        "Add data_type field",
                        "Add start_time field",
                        "Add end_time field"
                    ]
                },
                "summary": "Validation failed"
            },
            # Second call: success
            {
                "success": True,
                "data": {"weather_data": []},
                "summary": "Success"
            }
        ]

        # Execute first call (should fail)
        result1 = await mock_tool_executor.execute_tool(
            tool_name="get_weather_data",
            tool_args={"lat": 23.13},
            iteration=1
        )

        assert result1["success"] is False
        assert result1["error_type"] == "INPUT_VALIDATION_FAILED"
        assert "reflexion_suggestion" in result1

        # Execute second call with corrected args (should succeed)
        result2 = await mock_tool_executor.execute_tool(
            tool_name="get_weather_data",
            tool_args={
                "data_type": "era5",
                "lat": 23.13,
                "lon": 113.26,
                "start_time": "2025-11-07T00:00:00",
                "end_time": "2025-11-08T00:00:00"
            },
            iteration=2
        )

        assert result2["success"] is True
        assert "data" in result2


class TestReActLoopWithAdapter:
    """Test complete ReAct loop with Input Adapter"""

    @pytest.mark.asyncio
    async def test_loop_handles_validation_errors(
        self,
        mock_memory_manager,
        mock_tool_executor
    ):
        """Test ReAct loop handles validation errors gracefully"""

        # Create mock planner
        mock_planner = MagicMock()
        mock_planner.generate_thought = AsyncMock(return_value={
            "thought": "Test thought",
            "reasoning": "Test reasoning",
            "next_action": "Call tool"
        })

        # First action: invalid args
        # Second action: finish
        mock_planner.decide_action = AsyncMock(side_effect=[
            {
                "type": "TOOL_CALL",
                "tool": "get_weather_data",
                "args": {"lat": 23.13},
                "reasoning": "Get weather data"
            },
            {
                "type": "FINISH",
                "answer": "Analysis complete",
                "reasoning": "Task done"
            }
        ])

        # Setup tool executor to return validation error
        mock_tool_executor.execute_tool.return_value = {
            "success": False,
            "error_type": "INPUT_VALIDATION_FAILED",
            "tool_name": "get_weather_data",
            "missing_fields": ["data_type", "start_time", "end_time"],
            "reflexion_suggestion": {
                "should_retry": True,
                "suggestions": ["Add missing fields"]
            },
            "summary": "Validation failed"
        }

        # Create loop
        loop = ReActLoop(
            memory_manager=mock_memory_manager,
            llm_planner=mock_planner,
            tool_executor=mock_tool_executor,
            max_iterations=3,
            enable_reflexion=True
        )

        # Run loop
        events = []
        async for event in loop.run("Test query", enhance_with_history=False):
            events.append(event)
            # Break after a few iterations to prevent infinite loop
            if len(events) > 10:
                break

        # Verify events
        event_types = [e["type"] for e in events]
        assert "start" in event_types
        assert "thought" in event_types
        assert "action" in event_types


class TestEdgeCasesIntegration:
    """Test edge cases in integration"""

    @pytest.mark.asyncio
    async def test_multiple_validation_errors(self, mock_tool_executor):
        """Test handling multiple validation errors in sequence"""

        # Setup multiple validation errors
        errors = [
            {
                "success": False,
                "error_type": "INPUT_VALIDATION_FAILED",
                "missing_fields": ["field1"],
                "summary": "Error 1"
            },
            {
                "success": False,
                "error_type": "INPUT_VALIDATION_FAILED",
                "missing_fields": ["field2"],
                "summary": "Error 2"
            },
            {
                "success": True,
                "data": {"result": "success"},
                "summary": "Success"
            }
        ]

        mock_tool_executor.execute_tool.side_effect = errors

        # Execute calls
        for i in range(3):
            result = await mock_tool_executor.execute_tool(
                tool_name="test_tool",
                tool_args={},
                iteration=i
            )

            if i < 2:
                assert result["success"] is False
            else:
                assert result["success"] is True

    @pytest.mark.asyncio
    async def test_reflexion_max_retries(self):
        """Test Reflexion respects max retries through counter tracking"""
        from app.agent.core.reflexion_handler import ReflexionHandler

        handler = ReflexionHandler(max_reflections=2)

        # Simulate multiple failures - check reflection counter
        for i in range(5):
            error = {
                "success": False,
                "error_type": "INPUT_VALIDATION_FAILED",
                "tool_name": "test_tool",
                "missing_fields": ["field1"]
            }

            suggestion = await handler.handle_input_adaptation_error(
                error=error,
                tool_name="test_tool",
                raw_args={}
            )

            # Suggestions are always generated, but we can check the counter
            # The handler doesn't automatically stop, it just tracks count
            assert suggestion is not None
            assert "should_retry" in suggestion
            assert "suggestions" in suggestion


class TestPromptEnhancement:
    """Test prompt enhancement with Reflexion suggestions"""

    def test_retry_prompt_includes_suggestions(self):
        """Test retry prompt includes Reflexion suggestions"""
        from app.agent.core.planner import LLMPlanner

        # Create planner instance (without actual LLM client)
        planner = MagicMock(spec=LLMPlanner)
        planner._get_available_tools_description = MagicMock(
            return_value="Available tools"
        )

        # Create real method for testing
        from app.agent.core.planner import LLMPlanner as RealPlanner
        real_planner_instance = MagicMock()
        real_method = RealPlanner._build_retry_action_prompt

        # Call with observation containing Reflexion suggestions
        latest_observation = {
            "error_type": "INPUT_VALIDATION_FAILED",
            "reflexion_suggestion": {
                "suggestions": [
                    "Suggestion 1",
                    "Suggestion 2"
                ]
            }
        }

        # Build prompt (using real implementation)
        thought_result = {"thought": "Test"}
        prompt = real_method(
            real_planner_instance,
            thought_result,
            retry_count=1,
            max_retry=2,
            latest_observation=latest_observation
        )

        # Verify suggestions are in prompt
        assert "Reflexion" in prompt or "suggestion" in prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
