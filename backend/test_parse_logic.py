"""
测试端点解析逻辑
"""
import sys
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 模拟解析器逻辑
def parse_endpoints(text: str):
    """解析HYSPLIT端点数据"""
    endpoints = []

    for line in text.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<"):
            continue

        parts = line.split()
        if len(parts) >= 12:
            try:
                year = int(parts[2])
                if year < 100:
                    year += 2000

                endpoints.append({
                    "trajectory_id": int(parts[0]),
                    "year": year,
                    "month": int(parts[3]),
                    "day": int(parts[4]),
                    "hour": int(parts[5]),
                    "age_hours": float(parts[8]),
                    "lat": float(parts[9]),
                    "lon": float(parts[10]),
                    "height": float(parts[11]),
                    "pressure": float(parts[12]) if len(parts) > 12 else None,
                    "timestamp": f"{year}-{int(parts[3]):02d}-{int(parts[4]):02d}T{int(parts[5]):02d}:00:00Z"
                })
            except (ValueError, IndexError) as e:
                print(f"  [解析失败] {e}: {line[:50]}")
                continue

    return endpoints


# 测试数据：成功任务的格式
success_data = """     1     1    26     2     2     6     0     0     0.0   35.415  116.588    500.0    964.5
     1     1    26     2     2     5     0     1    -1.0   35.485  116.568    539.1    960.5
     1     1    26     2     2     4     0     2    -2.0   35.539  116.570    565.2    957.9"""

# 测试数据：失败任务的格式
failed_data = """     1     1    26     2     2     6     0     0     0.0   35.415  116.588    100.0   1012.9
     2     1    26     2     2     6     0     0     0.0   35.415  116.588    500.0    964.5
     3     1    26     2     2     6     0     0     0.0   35.415  116.588   1000.0    906.3
     1     1    26     2     2     5     0     1    -1.0   35.481  116.579    100.0   1013.7
     2     1    26     2     2     5     0     1    -1.0   35.485  116.568    539.1    960.5
     3     1    26     2     2     5     0     1    -1.0   35.507  116.535   1056.2    900.4"""

print("="*80)
print("测试解析逻辑")
print("="*80)

print("\n[成功任务数据]")
success_endpoints = parse_endpoints(success_data)
print(f"  解析结果: {len(success_endpoints)} 个端点")
for ep in success_endpoints[:3]:
    print(f"    {ep['timestamp']}: ({ep['lat']}, {ep['lon']}) @ {ep['height']}m")

print("\n[失败任务数据]")
failed_endpoints = parse_endpoints(failed_data)
print(f"  解析结果: {len(failed_endpoints)} 个端点")
for ep in failed_endpoints[:3]:
    print(f"    {ep['timestamp']}: ({ep['lat']}, {ep['lon']}) @ {ep['height']}m")

print("\n[结论]")
if len(failed_endpoints) > 0:
    print("  解析逻辑正常！")
else:
    print("  解析逻辑有问题")
