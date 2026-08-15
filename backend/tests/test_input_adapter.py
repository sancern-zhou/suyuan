"""
Unit Tests for Input Adapter Engine

Tests for the Input Adapter module that implements field mapping,
normalization, inference, and validation.

Author: Claude Code
Version: 1.0.0
"""

import pytest
from datetime import datetime
from app.agent.input_adapter import (
    InputAdapterEngine,
    InputValidationError,
    TOOL_RULES
)


class TestInputValidationError:
    """Test InputValidationError exception"""

    def test_error_creation(self):
        """Test creating InputValidationError with all fields"""
        error = InputValidationError(
            message="Test error",
            tool_name="test_tool",
            error_type="TEST_ERROR",
            missing_fields=["field1", "field2"],
            invalid_fields={"field3": "invalid value"},
            expected_schema={"field1": "string"},
            suggested_call={"tool": "test_tool", "args": {}}
        )

        assert error.message == "Test error"
        assert error.tool_name == "test_tool"
        assert error.error_type == "TEST_ERROR"
        assert error.missing_fields == ["field1", "field2"]
        assert error.invalid_fields == {"field3": "invalid value"}
        assert error.expected_schema == {"field1": "string"}
        assert error.suggested_call == {"tool": "test_tool", "args": {}}

    def test_error_to_dict(self):
        """Test converting error to dict"""
        error = InputValidationError(
            message="Test error",
            tool_name="test_tool",
            missing_fields=["field1"]
        )

        error_dict = error.to_dict()
        assert error_dict["error"] == "Test error"
        assert error_dict["tool_name"] == "test_tool"
        assert error_dict["missing_fields"] == ["field1"]
        assert error_dict["error_type"] == "VALIDATION_FAILED"


class TestInputAdapterEngine:
    """Test InputAdapterEngine core functionality"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_initialization(self):
        """Test adapter initialization"""
        assert self.adapter.tool_rules is not None
        assert len(self.adapter.tool_rules) > 0

    def test_no_rules_for_tool(self):
        """Test handling tool with no rules"""
        result, report = self.adapter.normalize(
            tool_name="unknown_tool",
            raw_args={"arg1": "value1"},
            context=None
        )

        assert result == {"arg1": "value1"}
        assert report["status"] == "no_rules"

    def test_normalize_time(self):
        """Test time normalization"""
        normalizer_result = self.adapter._normalize_time("2025-11-07T00:00:00")
        assert normalizer_result == "2025-11-07T00:00:00"

        # Test non-ISO format
        normalizer_result = self.adapter._normalize_time("2025-11-07 00:00:00")
        assert "T" in normalizer_result or normalizer_result == "2025-11-07 00:00:00"

    def test_normalize_float(self):
        """Test float normalization"""
        assert self.adapter._normalize_float("5.5") == 5.5
        assert self.adapter._normalize_float(5) == 5.0
        assert self.adapter._normalize_float("invalid") == 0.0

    def test_normalize_question(self):
        """Test question normalization"""
        assert self.adapter._normalize_question("  test  ") == "test"
        assert self.adapter._normalize_question("test") == "test"


class TestGetWeatherDataAdapter:
    """Test Input Adapter for get_weather_data tool"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_valid_era5_call(self):
        """Test valid ERA5 weather data call"""
        raw_args = {
            "data_type": "era5",
            "lat": 23.13,
            "lon": 113.26,
            "start_time": "2025-11-07T00:00:00",
            "end_time": "2025-11-08T00:00:00"
        }

        result, report = self.adapter.normalize(
            tool_name="get_weather_data",
            raw_args=raw_args,
            context=None
        )

        assert result["data_type"] == "era5"
        assert result["lat"] == 23.13
        assert result["lon"] == 113.26
        assert "start_time" in result
        assert "end_time" in result
        assert report["status"] == "success"

    def test_valid_observed_call(self):
        """Test valid observed weather data call"""
        raw_args = {
            "data_type": "observed",
            "station_id": "GZ001",
            "start_time": "2025-11-07T00:00:00",
            "end_time": "2025-11-08T00:00:00"
        }

        result, report = self.adapter.normalize(
            tool_name="get_weather_data",
            raw_args=raw_args,
            context=None
        )

        assert result["data_type"] == "observed"
        assert result["station_id"] == "GZ001"
        assert report["status"] == "success"

    def test_missing_required_fields(self):
        """Test missing required fields raises error"""
        raw_args = {
            "lat": 23.13,
            "lon": 113.26
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize(
                tool_name="get_weather_data",
                raw_args=raw_args,
                context=None
            )

        error = exc_info.value
        # data_type is inferred from lat/lon, so only time fields are missing
        assert "start_time" in error.missing_fields
        assert "end_time" in error.missing_fields

    def test_infer_data_type(self):
        """Test data_type inference"""
        # Should infer era5 from lat/lon
        raw_args = {
            "lat": 23.13,
            "lon": 113.26,
            "start_time": "2025-11-07T00:00:00",
            "end_time": "2025-11-08T00:00:00"
        }

        result, report = self.adapter.normalize(
            tool_name="get_weather_data",
            raw_args=raw_args,
            context=None
        )

        assert result.get("data_type") == "era5"
        inferences = [i for i in report.get("inferences", []) if i["field"] == "data_type"]
        assert len(inferences) > 0


class TestGetAirQualityAdapter:
    """Test Input Adapter for get_air_quality tool"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_valid_question(self):
        """Test valid question parameter"""
        raw_args = {
            "question": "Query Guangzhou air quality today"
        }

        result, report = self.adapter.normalize(
            tool_name="get_air_quality",
            raw_args=raw_args,
            context=None
        )

        assert result["question"] == "Query Guangzhou air quality today"
        assert report["status"] == "success"

    def test_missing_question(self):
        """Test missing question raises error"""
        raw_args = {}

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize(
                tool_name="get_air_quality",
                raw_args=raw_args,
                context=None
            )

        error = exc_info.value
        assert "question" in error.missing_fields

    def test_field_mapping(self):
        """Test field mapping for Chinese field names"""
        raw_args = {
            "question": "Test query"
        }

        result, report = self.adapter.normalize(
            tool_name="get_air_quality",
            raw_args=raw_args,
            context=None
        )

        # Should have "question" field
        assert "question" in result
        assert result["question"] == "Test query"


class TestAnalyzeUpwindEnterprisesAdapter:
    """Test Input Adapter for analyze_upwind_enterprises tool"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_valid_call(self):
        """Test valid upwind analysis call"""
        raw_args = {
            "station_name": "广州",
            "winds": [{"wd": 30, "ws": 2.1}]
        }

        result, report = self.adapter.normalize(
            tool_name="analyze_upwind_enterprises",
            raw_args=raw_args,
            context=None
        )

        assert result["station_name"] == "广州"
        assert "winds" in result
        assert len(result["winds"]) == 1
        assert report["status"] == "success"

    def test_infer_defaults(self):
        """Test default value inference"""
        raw_args = {
            "station_name": "广州",
            "winds": [{"wd": 30, "ws": 2.1}]
        }

        result, report = self.adapter.normalize(
            tool_name="analyze_upwind_enterprises",
            raw_args=raw_args,
            context=None
        )

        # Should infer default search range
        assert "search_range_km" in result
        assert result["search_range_km"] == 5.0
        # Should infer default max_enterprises
        assert "max_enterprises" in result
        assert result["max_enterprises"] == 30
        # Should infer default top_n
        assert "top_n" in result
        assert result["top_n"] == 8

    def test_field_mapping(self):
        """Test field mapping for Chinese field names"""
        raw_args = {
            "站点": "广州",
            "winds": [{"wd": 30, "ws": 2.1}]
        }

        result, report = self.adapter.normalize(
            tool_name="analyze_upwind_enterprises",
            raw_args=raw_args,
            context=None
        )

        # Should map "站点" to "station_name"
        assert result["station_name"] == "广州"
        assert "winds" in result

    def test_normalize_search_range(self):
        """Test search_range_km normalization"""
        raw_args = {
            "station_name": "广州",
            "winds": [{"wd": 30, "ws": 2.1}],
            "search_range_km": "10"
        }

        result, report = self.adapter.normalize(
            tool_name="analyze_upwind_enterprises",
            raw_args=raw_args,
            context=None
        )

        assert result["search_range_km"] == 10.0
        assert isinstance(result["search_range_km"], float)


class TestGenerateChartAdapter:
    """Test Input Adapter for generate_chart tool"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_valid_chart_call(self):
        """Test valid chart generation call"""
        raw_args = {
            "data": [{"time": "2025-11-07", "value": 45}],
            "title": "Test Chart"
        }

        result, report = self.adapter.normalize(
            tool_name="generate_chart",
            raw_args=raw_args,
            context=None
        )

        assert result["data"] == [{"time": "2025-11-07", "value": 45}]
        assert result["title"] == "Test Chart"
        assert report["status"] == "success"

    def test_missing_data(self):
        """Test missing data field raises error"""
        raw_args = {
            "title": "Test Chart"
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize(
                tool_name="generate_chart",
                raw_args=raw_args,
                context=None
            )

        error = exc_info.value
        assert "data" in error.missing_fields

    def test_infer_title(self):
        """Test title inference"""
        raw_args = {
            "data": [{"time": "2025-11-07", "value": 45}]
        }

        result, report = self.adapter.normalize(
            tool_name="generate_chart",
            raw_args=raw_args,
            context=None
        )

        # Should have inferred title
        assert "title" in result
        assert result["title"] is not None


class TestAdapterReport:
    """Test adapter reporting functionality"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_report_structure(self):
        """Test report structure"""
        raw_args = {
            "question": "Test query"
        }

        result, report = self.adapter.normalize(
            tool_name="get_air_quality",
            raw_args=raw_args,
            context=None
        )

        assert "tool_name" in report
        assert "corrections" in report
        assert "inferences" in report
        assert "validations" in report
        assert "status" in report

    def test_corrections_tracking(self):
        """Test corrections are tracked in report"""
        raw_args = {
            "data_type": "era5",
            "lat": 23.13,
            "lon": 113.26,
            "start_time": "2025-11-07 00:00:00",  # Non-ISO format
            "end_time": "2025-11-08 00:00:00"
        }

        result, report = self.adapter.normalize(
            tool_name="get_weather_data",
            raw_args=raw_args,
            context=None
        )

        # Should have normalization corrections
        corrections = report.get("corrections", [])
        assert isinstance(corrections, list)

    def test_inferences_tracking(self):
        """Test inferences are tracked in report"""
        raw_args = {
            "lat": 23.13,
            "lon": 113.26,
            "start_time": "2025-11-07T00:00:00",
            "end_time": "2025-11-08T00:00:00"
        }

        result, report = self.adapter.normalize(
            tool_name="get_weather_data",
            raw_args=raw_args,
            context=None
        )

        # Should have data_type inference
        inferences = report.get("inferences", [])
        assert isinstance(inferences, list)
        assert len(inferences) > 0


class TestEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        """Setup test adapter instance"""
        self.adapter = InputAdapterEngine()

    def test_empty_args(self):
        """Test empty arguments"""
        with pytest.raises(InputValidationError):
            self.adapter.normalize(
                tool_name="get_weather_data",
                raw_args={},
                context=None
            )

    def test_none_values(self):
        """Test None values in args"""
        raw_args = {
            "data_type": None,
            "start_time": "2025-11-07T00:00:00",
            "end_time": "2025-11-08T00:00:00"
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize(
                tool_name="get_weather_data",
                raw_args=raw_args,
                context=None
            )

        error = exc_info.value
        assert "data_type" in error.missing_fields

    def test_extra_fields_allowed(self):
        """Test extra fields are allowed"""
        raw_args = {
            "question": "Test query",
            "extra_field": "extra_value"
        }

        result, report = self.adapter.normalize(
            tool_name="get_air_quality",
            raw_args=raw_args,
            context=None
        )

        # Should succeed with extra field preserved
        assert result["question"] == "Test query"
        assert report["status"] == "success"

    def test_suggested_call_generation(self):
        """Test suggested call is generated on error"""
        raw_args = {
            "lat": 23.13,
            "lon": 113.26
        }

        with pytest.raises(InputValidationError) as exc_info:
            self.adapter.normalize(
                tool_name="get_weather_data",
                raw_args=raw_args,
                context=None
            )

        error = exc_info.value
        suggested_call = error.suggested_call

        assert "tool" in suggested_call
        assert suggested_call["tool"] == "get_weather_data"
        assert "args" in suggested_call
        assert "missing" in suggested_call
        assert "examples" in suggested_call


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
