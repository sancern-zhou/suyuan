"""
测试脚本：检查当前观测气象数据中是否存在无风速、风向数据的情况
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.db.database import async_session
from sqlalchemy import select, func, case, and_, or_
from app.db.models.weather_models import ERA5ReanalysisData, ObservedWeatherData
import structlog

logger = structlog.get_logger()


async def check_era5_wind_data():
    """检查ERA5数据中的风速风向缺失情况"""
    print("=" * 80)
    print("ERA5 数据风速风向检查")
    print("=" * 80)

    async with async_session() as session:
        # 1. 检查总记录数
        total_result = await session.execute(
            select(func.count()).select_from(ERA5ReanalysisData)
        )
        total_count = total_result.scalar()
        print(f"\n总记录数: {total_count}")

        if total_count == 0:
            print("数据库中没有ERA5数据")
            return

        # 2. 检查风速为NULL的记录数
        wind_speed_null_result = await session.execute(
            select(func.count()).select_from(ERA5ReanalysisData).where(
                ERA5ReanalysisData.wind_speed_10m.is_(None)
            )
        )
        wind_speed_null_count = wind_speed_null_result.scalar()
        print(f"风速为NULL的记录数: {wind_speed_null_count} ({wind_speed_null_count/total_count*100:.2f}%)")

        # 3. 检查风向为NULL的记录数
        wind_direction_null_result = await session.execute(
            select(func.count()).select_from(ERA5ReanalysisData).where(
                ERA5ReanalysisData.wind_direction_10m.is_(None)
            )
        )
        wind_direction_null_count = wind_direction_null_result.scalar()
        print(f"风向为NULL的记录数: {wind_direction_null_count} ({wind_direction_null_count/total_count*100:.2f}%)")

        # 4. 检查风速或风向任一为NULL的记录数
        either_null_result = await session.execute(
            select(func.count()).select_from(ERA5ReanalysisData).where(
                or_(
                    ERA5ReanalysisData.wind_speed_10m.is_(None),
                    ERA5ReanalysisData.wind_direction_10m.is_(None)
                )
            )
        )
        either_null_count = either_null_result.scalar()
        print(f"风速或风向任一为NULL的记录数: {either_null_count} ({either_null_count/total_count*100:.2f}%)")

        # 5. 检查两者都为NULL的记录数
        both_null_result = await session.execute(
            select(func.count()).select_from(ERA5ReanalysisData).where(
                and_(
                    ERA5ReanalysisData.wind_speed_10m.is_(None),
                    ERA5ReanalysisData.wind_direction_10m.is_(None)
                )
            )
        )
        both_null_count = both_null_result.scalar()
        print(f"风速和风向都为NULL的记录数: {both_null_count} ({both_null_count/total_count*100:.2f}%)")

        # 6. 查看最新的几条数据样本
        print("\n最新5条数据样本:")
        latest_result = await session.execute(
            select(ERA5ReanalysisData)
            .order_by(ERA5ReanalysisData.time.desc())
            .limit(5)
        )
        latest_records = latest_result.scalars().all()

        for i, record in enumerate(latest_records, 1):
            wind_speed = record.wind_speed_10m
            wind_direction = record.wind_direction_10m

            wind_speed_str = f"{wind_speed:.1f} km/h" if wind_speed is not None else "NULL"
            wind_dir_str = f"{wind_direction:.0f}°" if wind_direction is not None else "NULL"

            status = "OK" if (wind_speed is not None and wind_direction is not None) else "MISSING"

            print(f"  {i}. [{status}] {record.time.isoformat()} | 风速: {wind_speed_str:12s} | 风向: {wind_dir_str:8s} | 位置: ({record.lat:.2f}, {record.lon:.2f})")

        # 7. 统计有数据的时间范围
        time_range_result = await session.execute(
            select(
                func.min(ERA5ReanalysisData.time).label('min_time'),
                func.max(ERA5ReanalysisData.time).label('max_time')
            )
        )
        time_range = time_range_result.first()
        if time_range and time_range.min_time and time_range.max_time:
            print(f"\n数据时间范围: {time_range.min_time} 至 {time_range.max_time}")


async def check_observed_wind_data():
    """检查观测数据中的风速风向缺失情况"""
    print("\n" + "=" * 80)
    print("观测站数据风速风向检查")
    print("=" * 80)

    async with async_session() as session:
        # 1. 检查总记录数
        total_result = await session.execute(
            select(func.count()).select_from(ObservedWeatherData)
        )
        total_count = total_result.scalar()
        print(f"\n总记录数: {total_count}")

        if total_count == 0:
            print("数据库中没有观测站数据")
            return

        # 2. 检查风速为NULL的记录数
        wind_speed_null_result = await session.execute(
            select(func.count()).select_from(ObservedWeatherData).where(
                ObservedWeatherData.wind_speed_10m.is_(None)
            )
        )
        wind_speed_null_count = wind_speed_null_result.scalar()
        print(f"风速为NULL的记录数: {wind_speed_null_count} ({wind_speed_null_count/total_count*100:.2f}%)")

        # 3. 检查风向为NULL的记录数
        wind_direction_null_result = await session.execute(
            select(func.count()).select_from(ObservedWeatherData).where(
                ObservedWeatherData.wind_direction_10m.is_(None)
            )
        )
        wind_direction_null_count = wind_direction_null_result.scalar()
        print(f"风向为NULL的记录数: {wind_direction_null_count} ({wind_direction_null_count/total_count*100:.2f}%)")

        # 4. 检查风速或风向任一为NULL的记录数
        either_null_result = await session.execute(
            select(func.count()).select_from(ObservedWeatherData).where(
                or_(
                    ObservedWeatherData.wind_speed_10m.is_(None),
                    ObservedWeatherData.wind_direction_10m.is_(None)
                )
            )
        )
        either_null_count = either_null_result.scalar()
        print(f"风速或风向任一为NULL的记录数: {either_null_count} ({either_null_count/total_count*100:.2f}%)")


async def check_recent_data():
    """检查最近24小时的数据"""
    print("\n" + "=" * 80)
    print("最近24小时数据检查")
    print("=" * 80)

    end_time = datetime.now()
    start_time = end_time - timedelta(hours=24)

    async with async_session() as session:
        # ERA5数据
        era5_result = await session.execute(
            select(
                ERA5ReanalysisData.lat,
                ERA5ReanalysisData.lon,
                func.count().label('total'),
                func.sum(
                    case(
                        (ERA5ReanalysisData.wind_speed_10m.is_(None), 1),
                        else_=0
                    )
                ).label('ws_null')
            )
            .where(
                and_(
                    ERA5ReanalysisData.time >= start_time,
                    ERA5ReanalysisData.time <= end_time
                )
            )
            .group_by(ERA5ReanalysisData.lat, ERA5ReanalysisData.lon)
        )

        era5_stats = era5_result.fetchall()
        print(f"\nERA5数据 (最近24小时):")
        if era5_stats:
            for stat in era5_stats:
                lat, lon, total, ws_null = stat
                ws_pct = ws_null / total * 100 if total > 0 else 0
                print(f"  网格点 ({lat:.2f}, {lon:.2f}): 总计={total:3d} | "
                      f"风速NULL={ws_null:3d} ({ws_pct:5.1f}%)")
        else:
            print("  最近24小时没有ERA5数据")


async def main():
    print("\n" + "=" * 80)
    print("气象数据风速风向缺失情况检查")
    print("=" * 80)
    print(f"检查时间: {datetime.now().isoformat()}\n")

    try:
        await check_era5_wind_data()
        await check_observed_wind_data()
        await check_recent_data()

        print("\n" + "=" * 80)
        print("检查完成")
        print("=" * 80)

    except Exception as e:
        logger.error("检查失败", error=str(e), exc_info=True)
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
