"""
Phase 2-2: Trajectory Clustering Testing

轨迹聚类分析测试
测试场景：
1. Ensemble轨迹生成
2. Angle-based距离计算
3. 层次聚类分析
4. K-means聚类分析
5. 聚类可视化生成
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.trajectory.trajectory_calculator import TrajectoryCalculatorService


async def test_ensemble_generation():
    """测试ensemble轨迹生成"""
    print("\n" + "=" * 60)
    print("TEST 1: Ensemble Trajectory Generation")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    start = time.time()
    result = await service.calculate_ensemble_trajectories(
        lat=23.13,
        lon=113.26,
        start_time=start_time,
        hours=72,
        height=100,
        ensemble_count=6
    )
    elapsed = time.time() - start

    print(f"\nExecution time: {elapsed:.2f}s")
    print(f"Success: {result.get('success')}")
    print(f"Ensemble count: {result.get('ensemble_count')}")

    if result.get("success"):
        print(f"Trajectories generated: {len(result['trajectories'])}")
        for i, traj in enumerate(result["trajectories"]):
            print(f"  Trajectory {i}: start_time={traj['start_time']}, points={len(traj['data'])}")

    return result


async def test_hierarchical_clustering():
    """测试层次聚类分析"""
    print("\n" + "=" * 60)
    print("TEST 2: Hierarchical Clustering")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    start = time.time()
    result = await service.perform_trajectory_clustering(
        lat=23.13,
        lon=113.26,
        start_time=start_time,
        hours=72,
        height=100,
        ensemble_count=8,
        n_clusters=3,
        clustering_method="hierarchical"
    )
    elapsed = time.time() - start

    print(f"\nExecution time: {elapsed:.2f}s")
    print(f"Success: {result.get('success')}")

    if result.get("success"):
        print(f"\nClustering Results:")
        print(f"  Total clusters: {len(result['data'])}")
        print(f"  Visuals generated: {len(result['visuals'])}")

        print(f"\nCluster Statistics:")
        for cluster in result["data"]:
            print(f"  Cluster {cluster['cluster_id']}:")
            print(f"    Size: {cluster['size']} trajectories")
            print(f"    Percentage: {cluster['percentage']:.1f}%")
            print(f"    Dominant direction: {cluster['dominant_direction']}")
            print(f"    Avg intra-cluster distance: {cluster['avg_intra_cluster_distance']:.4f}")

        print(f"\nMetadata:")
        print(f"  Schema version: {result['metadata']['schema_version']}")
        print(f"  Generator: {result['metadata']['generator']}")
        print(f"  Clustering method: {result['metadata']['analysis_params']['clustering_method']}")
        print(f"  Distance metric: {result['metadata']['analysis_params']['distance_metric']}")

        print(f"\nSummary: {result.get('summary')}")
    else:
        print(f"ERROR: {result.get('error')}")

    return result


async def test_kmeans_clustering():
    """测试K-means聚类分析"""
    print("\n" + "=" * 60)
    print("TEST 3: K-means Clustering")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    start = time.time()
    result = await service.perform_trajectory_clustering(
        lat=23.13,
        lon=113.26,
        start_time=start_time,
        hours=72,
        height=100,
        ensemble_count=8,
        n_clusters=3,
        clustering_method="kmeans"
    )
    elapsed = time.time() - start

    print(f"\nExecution time: {elapsed:.2f}s")
    print(f"Success: {result.get('success')}")

    if result.get("success"):
        print(f"\nClustering Results:")
        print(f"  Total clusters: {len(result['data'])}")

        print(f"\nCluster Statistics:")
        for cluster in result["data"]:
            print(f"  Cluster {cluster['cluster_id']}: {cluster['size']} trajectories ({cluster['percentage']:.1f}%), direction: {cluster['dominant_direction']}")
    else:
        print(f"ERROR: {result.get('error')}")

    return result


async def test_different_cluster_counts():
    """测试不同聚类数量"""
    print("\n" + "=" * 60)
    print("TEST 4: Different Cluster Counts (2, 3, 4)")
    print("=" * 60)

    service = TrajectoryCalculatorService()
    start_time = datetime(2024, 10, 1, 12, 0, 0)

    results = []
    for n_clusters in [2, 3, 4]:
        print(f"\nTesting with n_clusters={n_clusters}")

        result = await service.perform_trajectory_clustering(
            lat=23.13,
            lon=113.26,
            start_time=start_time,
            hours=72,
            height=100,
            ensemble_count=8,
            n_clusters=n_clusters,
            clustering_method="hierarchical"
        )

        if result.get("success"):
            print(f"  Success: {len(result['data'])} clusters generated")
            results.append({
                "n_clusters": n_clusters,
                "success": True,
                "cluster_count": len(result["data"])
            })
        else:
            print(f"  Failed: {result.get('error')}")
            results.append({
                "n_clusters": n_clusters,
                "success": False,
                "error": result.get("error")
            })

    return results


async def run_all_tests():
    """运行所有聚类测试"""
    print("=" * 80)
    print("PHASE 2-2: TRAJECTORY CLUSTERING TESTS")
    print("=" * 80)

    test_results = {}

    # Test 1: Ensemble generation
    try:
        ensemble_result = await test_ensemble_generation()
        test_results["ensemble_generation"] = {
            "success": ensemble_result.get("success"),
            "ensemble_count": ensemble_result.get("ensemble_count")
        }
    except Exception as e:
        print(f"\nTest 1 FAILED: {e}")
        test_results["ensemble_generation"] = {"success": False, "error": str(e)}

    # Test 2: Hierarchical clustering
    try:
        hierarchical_result = await test_hierarchical_clustering()
        test_results["hierarchical_clustering"] = {
            "success": hierarchical_result.get("success"),
            "n_clusters": len(hierarchical_result.get("data", []))
        }
    except Exception as e:
        print(f"\nTest 2 FAILED: {e}")
        test_results["hierarchical_clustering"] = {"success": False, "error": str(e)}

    # Test 3: K-means clustering
    try:
        kmeans_result = await test_kmeans_clustering()
        test_results["kmeans_clustering"] = {
            "success": kmeans_result.get("success"),
            "n_clusters": len(kmeans_result.get("data", []))
        }
    except Exception as e:
        print(f"\nTest 3 FAILED: {e}")
        test_results["kmeans_clustering"] = {"success": False, "error": str(e)}

    # Test 4: Different cluster counts
    try:
        cluster_count_results = await test_different_cluster_counts()
        test_results["different_cluster_counts"] = cluster_count_results
    except Exception as e:
        print(f"\nTest 4 FAILED: {e}")
        test_results["different_cluster_counts"] = {"success": False, "error": str(e)}

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    total_tests = 4
    passed_tests = sum(1 for result in [
        test_results["ensemble_generation"],
        test_results["hierarchical_clustering"],
        test_results["kmeans_clustering"],
        {"success": all(r["success"] for r in test_results["different_cluster_counts"])}
    ] if result.get("success"))

    print(f"\nTotal tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success rate: {(passed_tests / total_tests) * 100:.1f}%")

    # Save results
    output_file = Path(__file__).parent / "phase2_clustering_test_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "test_date": datetime.now().isoformat(),
            "phase": "2.2",
            "test_results": test_results,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "success_rate": (passed_tests / total_tests) * 100
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_file}")
    print("=" * 80)

    return passed_tests >= 3  # Require at least 3/4 tests to pass


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)
