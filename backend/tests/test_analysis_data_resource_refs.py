from app.tools.analysis.aggregate_data.tool import AggregateDataTool
from app.tools.analysis.calculate_pm_pmf.tool import CalculatePMFTool
from app.tools.analysis.calculate_vocs_pmf.tool import CalculateVOCSPMFTool
from app.tools.analysis.meteorological_trajectory_analysis.tool import MeteorologicalTrajectoryAnalysisTool
from app.tools.analysis.trajectory_source_analysis.tool import TrajectorySourceAnalysisTool


class FakeAggregateContext:
    def get_raw_data(self, data_id):
        assert data_id == "source_data:v1:abc"
        return [
            {"city": "广州", "value": 1},
            {"city": "广州", "value": 2},
        ]

    def save_data(self, data, schema, metadata):
        assert schema == "aggregated_result"
        assert metadata["source_data_id"] == "source_data:v1:abc"
        return "aggregated_result:v1:def"


async def test_aggregate_data_returns_data_refs_and_resume_context():
    result = await AggregateDataTool().execute(
        context=FakeAggregateContext(),
        data_id="source_data:v1:abc",
        aggregations=[{"function": "SUM", "column": "value", "alias": "total_value"}],
        group_by=["city"],
    )

    assert result["success"] is True
    assert result["refs"]["data"] == [
        {
            "data_id": "source_data:v1:abc",
            "usage": "source",
            "tool": "read_data_registry",
        },
        {
            "data_id": "aggregated_result:v1:def",
            "usage": "generated",
            "tool": "read_data_registry",
        },
    ]
    assert result["llm_resume"] == {
        "source_data_ids": ["source_data:v1:abc"],
        "data_ids": ["aggregated_result:v1:def"],
        "tool_hint": "Use read_data_registry(data_id='aggregated_result:v1:def') to inspect the generated data.",
    }


def test_pmf_tools_attach_data_refs_and_resume_context():
    pm_result = {
        "success": True,
        "data_id": "pmf_result:v1:pm",
        "metadata": {
            "data_id": "particulate:v1:source",
            "gas_data_id": "gas:v1:source",
            "source_data_ids": ["particulate:v1:source", "pmf_result:v1:pm", "gas:v1:source"],
        },
    }
    vocs_result = {
        "success": True,
        "data_id": "pmf_result:v1:vocs",
        "metadata": {
            "data_id": "vocs:v1:source",
            "source_data_ids": ["vocs:v1:source", "pmf_result:v1:vocs"],
        },
    }

    CalculatePMFTool()._attach_resume_context(pm_result)
    CalculateVOCSPMFTool()._attach_resume_context(vocs_result)

    assert pm_result["refs"]["data"] == [
        {
            "data_id": "particulate:v1:source",
            "usage": "source",
            "tool": "read_data_registry",
        },
        {
            "data_id": "gas:v1:source",
            "usage": "source",
            "tool": "read_data_registry",
        },
        {
            "data_id": "pmf_result:v1:pm",
            "usage": "generated",
            "tool": "read_data_registry",
        },
    ]
    assert pm_result["llm_resume"]["source_data_ids"] == ["particulate:v1:source", "gas:v1:source"]
    assert pm_result["llm_resume"]["data_ids"] == ["pmf_result:v1:pm"]
    assert "read_data_registry" in pm_result["llm_resume"]["tool_hint"]

    assert vocs_result["refs"]["data"] == [
        {
            "data_id": "vocs:v1:source",
            "usage": "source",
            "tool": "read_data_registry",
        },
        {
            "data_id": "pmf_result:v1:vocs",
            "usage": "generated",
            "tool": "read_data_registry",
        },
    ]
    assert vocs_result["llm_resume"]["source_data_ids"] == ["vocs:v1:source"]
    assert vocs_result["llm_resume"]["data_ids"] == ["pmf_result:v1:vocs"]


def test_trajectory_tools_attach_generated_data_refs():
    meteo_result = {
        "success": True,
        "data_id": "trajectory_endpoints:v1:abc",
        "metadata": {"generator": "meteorological_trajectory_analysis"},
    }
    source_result = {
        "success": True,
        "data_id": "trajectory_analysis_result:v1:def",
        "metadata": {"generator": "analyze_trajectory_sources"},
    }

    MeteorologicalTrajectoryAnalysisTool()._attach_resume_context(meteo_result)
    TrajectorySourceAnalysisTool()._attach_resume_context(source_result)

    assert meteo_result["refs"]["data"] == [
        {
            "data_id": "trajectory_endpoints:v1:abc",
            "usage": "generated",
            "tool": "read_data_registry",
        }
    ]
    assert meteo_result["llm_resume"]["data_ids"] == ["trajectory_endpoints:v1:abc"]
    assert "read_data_registry" in meteo_result["llm_resume"]["tool_hint"]

    assert source_result["refs"]["data"] == [
        {
            "data_id": "trajectory_analysis_result:v1:def",
            "usage": "generated",
            "tool": "read_data_registry",
        }
    ]
    assert source_result["llm_resume"]["data_ids"] == ["trajectory_analysis_result:v1:def"]
