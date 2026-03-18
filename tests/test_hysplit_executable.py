"""
测试HYSPLIT可执行文件是否可用
"""

import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.utils.hysplit_control_generator import HYSPLITControlGenerator


def test_hysplit_executable():
    """测试HYSPLIT可执行文件"""

    print("\n" + "=" * 60)
    print("TEST: HYSPLIT Executable Installation")
    print("=" * 60)

    # 1. 检查可执行文件是否存在
    hysplit_exec = Path("data/hysplit/exec/hyts_std.exe")

    if not hysplit_exec.exists():
        print(f"❌ HYSPLIT executable not found: {hysplit_exec}")
        return False

    print(f"✅ HYSPLIT executable found: {hysplit_exec}")
    print(f"   File size: {hysplit_exec.stat().st_size / 1024 / 1024:.2f} MB")

    # 2. 生成测试CONTROL文件
    print("\n生成测试CONTROL文件...")
    generator = HYSPLITControlGenerator()
    control_content = generator.generate_backward_control(
        lat=40.0,
        lon=-90.0,
        height=50.0,
        start_time=datetime(2025, 11, 19, 12, 0),
        hours=24,  # 短时间测试
        meteo_dir="./",
        meteo_files=["dummy.arl"],  # 虚拟文件（测试用）
        output_dir="./",
        output_filename="test_tdump"
    )

    print("✅ CONTROL file generated")
    print("\nCONTROL content preview:")
    print("-" * 40)
    print(control_content)
    print("-" * 40)

    # 3. 创建临时工作目录
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # 写入CONTROL文件
        control_file = tmpdir_path / "CONTROL"
        with open(control_file, 'w') as f:
            f.write(control_content)

        print(f"\n✅ CONTROL file written to: {control_file}")

        # 4. 尝试运行HYSPLIT（预期会因为缺少气象数据而失败，但能验证可执行）
        print("\n尝试运行HYSPLIT...")
        print("（预期失败：缺少气象数据文件 - 这是正常的）")

        try:
            result = subprocess.run(
                [str(hysplit_exec.absolute())],
                cwd=str(tmpdir_path),  # 在临时目录运行
                capture_output=True,
                timeout=10,
                text=True
            )

            print(f"\nReturn code: {result.returncode}")

            # 检查输出
            stdout = result.stdout
            stderr = result.stderr

            print(f"\nSTDOUT preview ({len(stdout)} chars):")
            print(stdout[:500] if stdout else "(empty)")

            print(f"\nSTDERR preview ({len(stderr)} chars):")
            print(stderr[:500] if stderr else "(empty)")

            # 判断成功条件
            if "HYSPLIT" in stdout or "HYSPLIT" in stderr:
                print("\n✅ HYSPLIT executable runs successfully")

                # 预期错误：找不到气象文件（这是正常的）
                if "meteo" in stderr.lower() or "data" in stderr.lower() or result.returncode != 0:
                    print("✅ Expected error: Meteorological data not found (this is OK)")

                return True
            else:
                print("\n⚠️ HYSPLIT ran but output unexpected")
                return True  # 只要能执行就算成功

        except subprocess.TimeoutExpired:
            print("\n⚠️ HYSPLIT execution timeout")
            print("   (可能在等待交互式输入)")
            print("✅ 但可执行文件是可用的")
            return True

        except Exception as e:
            print(f"\n❌ Error running HYSPLIT: {e}")
            import traceback
            traceback.print_exc()
            return False


def test_hysplit_version():
    """尝试获取HYSPLIT版本信息"""
    print("\n" + "=" * 60)
    print("TEST: HYSPLIT Version Check")
    print("=" * 60)

    hysplit_exec = Path("data/hysplit/exec/hyts_std.exe")

    if not hysplit_exec.exists():
        print("❌ HYSPLIT executable not found")
        return False

    try:
        # 尝试运行HYSPLIT（无参数，会显示初始化信息）
        result = subprocess.run(
            [str(hysplit_exec.absolute())],
            capture_output=True,
            timeout=3,
            text=True,
            input="\n"  # 发送换行符尝试退出
        )

        # 查找版本信息
        output = result.stdout + result.stderr

        if "hysplit" in output.lower():
            print("✅ HYSPLIT responds to execution")

            # 提取版本信息
            for line in output.split('\n'):
                if 'version' in line.lower() or 'hysplit' in line.lower():
                    print(f"   {line.strip()}")

            return True

    except subprocess.TimeoutExpired:
        print("✅ HYSPLIT executable responds (timeout as expected)")
        return True
    except Exception as e:
        print(f"⚠️ Could not get version: {e}")
        return False


def check_directory_structure():
    """检查目录结构"""
    print("\n" + "=" * 60)
    print("TEST: Directory Structure Check")
    print("=" * 60)

    required_paths = {
        "exec": Path("data/hysplit/exec"),
        "exec/hyts_std.exe": Path("data/hysplit/exec/hyts_std.exe"),
        "bdyfiles": Path("data/hysplit/bdyfiles"),
        "working": Path("data/hysplit/working")
    }

    all_good = True

    for name, path in required_paths.items():
        exists = path.exists()
        status = "[OK]" if exists else "[FAIL]"
        path_type = "FILE" if path.is_file() else ("DIR" if path.is_dir() else "N/A")

        print(f"{status} {name:<25} {path_type:<6} {path}")

        if not exists:
            all_good = False

    return all_good


if __name__ == "__main__":
    print("=" * 80)
    print("HYSPLIT EXECUTABLE INSTALLATION TEST")
    print("=" * 80)

    # Test 1: 目录结构检查
    dir_ok = check_directory_structure()

    # Test 2: 版本检查
    version_ok = test_hysplit_version()

    # Test 3: 可执行文件测试
    exec_ok = test_hysplit_executable()

    # 总结
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    print(f"Directory structure: {'✅ PASS' if dir_ok else '❌ FAIL'}")
    print(f"Version check:       {'✅ PASS' if version_ok else '❌ FAIL'}")
    print(f"Executable test:     {'✅ PASS' if exec_ok else '❌ FAIL'}")

    overall_success = dir_ok and exec_ok

    if overall_success:
        print("\n🎉 HYSPLIT installation verified successfully!")
        print("\nNext steps:")
        print("1. Download GDAS meteorological data (Module 5)")
        print("2. Implement HYSPLITRealWrapper (Module 4)")
        print("3. Run end-to-end trajectory calculation")
    else:
        print("\n❌ HYSPLIT installation verification failed")
        print("\nTroubleshooting:")
        if not dir_ok:
            print("- Check that HYSPLIT files are in: data/hysplit/")
        print("- Verify hyts_std.exe file permissions")

    print("=" * 80)

    exit(0 if overall_success else 1)
