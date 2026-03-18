#!/usr/bin/env python3
"""
附近站点API服务启动文件
独立运行的Flask应用，提供附近站点查找服务
"""

import sys
import os
import logging
from flask import Flask, jsonify, request
# 从工具类模块导入NearestStationFinder（确保无循环导入）
from src.utils.nearest_station_finder import NearestStationFinder
# 导入企业查询引擎
from src.utils.enterprise_query_engine import EnterpriseQueryEngine
from api_upwind.controller import bp as upwind_bp

# 添加项目根目录到Python路径（确保模块导入正常）
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 创建Flask应用
app = Flask(__name__)
app.register_blueprint(upwind_bp)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化站点查找器实例
finder = None
# 初始化企业查询引擎实例
enterprise_engine = None

def init_nearest_stations_service():
    """初始化附近站点服务，加载站点数据"""
    global finder, enterprise_engine
    try:
        # 实例化站点查找器（此时nearest_station_finder.py已修复循环导入问题）
        finder = NearestStationFinder()
        logger.info(f"附近站点查找器初始化成功，加载了 {len(finder.stations)} 个站点")

        # 初始化企业查询引擎
        enterprise_engine = EnterpriseQueryEngine()
        logger.info(f"企业查询引擎初始化成功，加载了 {enterprise_engine.get_total_count()} 条企业记录")

        return True
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        return False

# API接口：根据站点编码查询附近站点
@app.route('/api/nearest-stations/by-station-code', methods=['GET'])
def find_nearest_by_station_code():
    try:
        # 获取请求参数
        station_code = request.args.get('station_code')
        max_distance = float(request.args.get('max_distance', 10.0))
        max_results = int(request.args.get('max_results', 10))
        
        if not station_code:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_code'
            }), 400
        
        # 调用查找器方法（依赖修复后的NearestStationFinder）
        results = finder.find_nearest_stations(station_code, max_distance, max_results)
        
        return jsonify({
            'status': 'success',
            'data': results
        })
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# API接口：根据站点名称查询附近站点（新增功能）
@app.route('/api/nearest-stations/by-station-name', methods=['GET'])
def find_nearest_by_station_name():
    try:
        # 获取请求参数
        station_name = request.args.get('station_name')
        max_distance = float(request.args.get('max_distance', 10.0))
        max_results = int(request.args.get('max_results', 10))
        
        if not station_name:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_name'
            }), 400
        
        # 调用按名称查询的方法（已在查找器中实现）
        results = finder.find_nearest_stations_by_name(station_name, max_distance, max_results)
        
        return jsonify({
            'status': 'success',
            'data': results
        })
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# API接口：根据经纬度查询附近站点
@app.route('/api/nearest-stations/by-coordinates', methods=['GET'])
def find_nearest_by_coordinates():
    try:
        # 获取请求参数
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        max_distance = float(request.args.get('max_distance', 10.0))
        max_results = int(request.args.get('max_results', 10))
        
        # 调用经纬度查询方法
        results = finder.find_nearest_stations_by_coordinates(lat, lon, max_distance, max_results)
        
        return jsonify({
            'status': 'success',
            'data': results
        })
        
    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# Dify工具接口：根据站点编码查询（POST）
@app.route('/api/nearest-stations/dify/by-station-code', methods=['POST'])
def dify_find_nearest_by_station_code():
    try:
        data = request.get_json()
        station_code = data.get('station_code')
        max_distance = float(data.get('max_distance', 10.0))
        max_results = int(data.get('max_results', 10))
        
        if not station_code:
            return jsonify({
                'success': False,
                'message': '缺少必需参数: station_code'
            }), 400
        
        results = finder.find_nearest_stations(station_code, max_distance, max_results)
        formatted_results = [
            {
                'station_name': s['站点名称'],
                'distance': s['距离'],
                'station_code': s['唯一编码']
            } for s in results
        ]
        
        return jsonify({
            'success': True,
            'results': formatted_results
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }), 500

# Dify工具接口：根据站点名称查询（POST，新增功能）
@app.route('/api/nearest-stations/dify/by-station-name', methods=['POST'])
def dify_find_nearest_by_station_name():
    try:
        data = request.get_json()
        station_name = data.get('station_name')
        max_distance = float(data.get('max_distance', 10.0))
        max_results = int(data.get('max_results', 10))
        
        if not station_name:
            return jsonify({
                'success': False,
                'message': '缺少必需参数: station_name'
            }), 400
        
        results = finder.find_nearest_stations_by_name(station_name, max_distance, max_results)
        formatted_results = [
            {
                'station_name': s['站点名称'],
                'distance': s['距离'],
                'station_code': s['唯一编码']
            } for s in results
        ]
        
        return jsonify({
            'success': True,
            'results': formatted_results
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }), 500

# Dify工具接口：根据经纬度查询（POST）
@app.route('/api/nearest-stations/dify/by-coordinates', methods=['POST'])
def dify_find_nearest_by_coordinates():
    try:
        data = request.get_json()
        lat = float(data.get('lat'))
        lon = float(data.get('lon'))
        max_distance = float(data.get('max_distance', 10.0))
        max_results = int(data.get('max_results', 10))
        
        results = finder.find_nearest_stations_by_coordinates(lat, lon, max_distance, max_results)
        formatted_results = [
            {
                'station_name': s['站点名称'],
                'distance': s['距离'],
                'station_code': s['唯一编码']
            } for s in results
        ]
        
        return jsonify({
            'success': True,
            'results': formatted_results
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }), 500

# 健康检查接口
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'service': 'nearest-stations-api',
        'stations_count': len(finder.stations) if finder else 0,
        'enterprises_count': enterprise_engine.get_total_count() if enterprise_engine else 0
    })

# 区县信息查询API
@app.route('/api/station-district/by-station-code', methods=['GET'])
def get_station_district_by_code():
    """根据站点编码查询站点所在区县信息"""
    try:
        station_code = request.args.get('station_code')
        if not station_code:
            return jsonify({
                'status': 'error',
                'message': '请提供站点编码参数 station_code'
            }), 400
        
        district_info = finder.get_station_district(station_code)
        if not district_info:
            return jsonify({
                'status': 'error',
                'message': f'未找到站点编码为 {station_code} 的站点'
            }), 404
        
        return jsonify({
            'status': 'success',
            'data': district_info
        })
        
    except Exception as e:
        logger.error(f"查询站点区县信息失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

@app.route('/api/station-district/by-district-name', methods=['GET'])
def get_stations_by_district():
    """根据区县名称查询该区县下的所有站点"""
    try:
        district_name = request.args.get('district_name')
        if not district_name:
            return jsonify({
                'status': 'error',
                'message': '请提供区县名称参数 district_name'
            }), 400
        
        stations = finder.get_stations_by_district(district_name)
        
        return jsonify({
            'status': 'success',
            'total': len(stations),
            'data': stations
        })
        
    except Exception as e:
        logger.error(f"查询区县站点失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

@app.route('/api/station-district/summary', methods=['GET'])
def get_districts_summary():
    """获取所有区县的站点统计信息"""
    try:
        summary = finder.get_districts_summary()
        
        return jsonify({
            'status': 'success',
            'total_districts': len(summary),
            'data': summary
        })
        
    except Exception as e:
        logger.error(f"获取区县统计失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 按城市查询辖内所有站点（支持可选返回字段）
@app.route('/api/nearest-stations/by-city-neighbors', methods=['GET'])
def get_city_neighbor_stations():
    """根据城市名称，计算城市中心点，与其他城市中心点距离，返回最近的3-5个城市及其站点信息

    参数：
    - city_name: 必填，城市名称（模糊匹配，如“广州”匹配“广州市”）
    - k: 可选，返回最近城市的数量（3-5之间），默认3
    - fields: 可选，逗号分隔返回字段（name,code,lat,lon,district,township,type_id），默认与/by-city一致
    - station_type_id: 可选，按站点类型ID精确筛选

    返回：
    {
      status, city_query, center: {lat,lon}, k, neighbors: [
        { city: 城市名, distance: 距离km, stations_count, center:{lat,lon}, stations:[...按字段投影...] }
      ]
    }
    """
    try:
        city_name = request.args.get('city_name')
        if not city_name:
            return jsonify({'status':'error','message':'请提供城市名称参数 city_name'}), 400

        # 解析k
        try:
            k_param = int(request.args.get('k', 3))
        except ValueError:
            return jsonify({'status':'error','message':'参数 k 必须为整数'}), 400
        k = max(3, min(5, k_param))

        # 站点类型筛选
        station_type_id_param = request.args.get('station_type_id')
        station_type_id_filter = None
        if station_type_id_param:
            try:
                station_type_id_filter = float(station_type_id_param)
            except ValueError:
                return jsonify({'status':'error','message':f'站点类型ID参数格式错误: {station_type_id_param}'}), 400

        # 字段解析与映射
        fields_param = request.args.get('fields', '').strip()
        requested_fields = [f.strip().lower() for f in fields_param.split(',') if f.strip()] if fields_param else []
        field_map = {
            'name': '站点名称',
            'code': '唯一编码',
            'lat': '纬度',
            'lon': '经度',
            'district': '所属区县',
            'township': '乡镇',
            'type_id': '站点类型ID'
        }
        default_fields = ['name', 'code', 'lat', 'lon', 'district', 'township', 'type_id']
        effective_fields = requested_fields if requested_fields else default_fields

        # 构建按城市分组与城市中心点
        from collections import defaultdict
        city_groups = defaultdict(list)
        for s in finder.stations:
            city = s.get('所属城市') or s.get('城市') or ''
            if not city:
                continue
            if s.get('纬度') is None or s.get('经度') is None:
                continue
            city_groups[city].append(s)

        def compute_centroid(stations_list):
            if not stations_list:
                return None
            lat_sum = sum(s['纬度'] for s in stations_list if s.get('纬度') is not None)
            lon_sum = sum(s['经度'] for s in stations_list if s.get('经度') is not None)
            n = len(stations_list)
            return lat_sum / n, lon_sum / n

        # 目标城市的站点集合（支持包含匹配）
        city_lower = city_name.lower()
        target_stations = []
        for c, sts in city_groups.items():
            c_lower = str(c).lower()
            if city_lower in c_lower or c_lower in city_lower:
                target_stations.extend(sts)

        if not target_stations:
            return jsonify({'status':'error','message':f'未找到城市: {city_name} 的站点记录'}), 404

        target_center = compute_centroid(target_stations)

        # 计算其他城市的中心点与距离
        def haversine(lat1, lon1, lat2, lon2):
            import math
            R = 6371.0
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            return R * c

        neighbors = []
        tgt_lat, tgt_lon = target_center
        for c, sts in city_groups.items():
            # 跳过目标城市本身（若匹配到多个别名，仍以字符串不同来判断包含关系）
            c_lower = str(c).lower()
            if city_lower in c_lower or c_lower in city_lower:
                continue
            centroid = compute_centroid(sts)
            if not centroid:
                continue
            dist = round(haversine(tgt_lat, tgt_lon, centroid[0], centroid[1]), 2)
            neighbors.append((c, dist, centroid, sts))

        neighbors.sort(key=lambda x: x[1])
        neighbors = neighbors[:k]

        # 构造返回数据，按字段投影与类型筛选
        def project(station):
            projected = {}
            for f in effective_fields:
                key = field_map.get(f)
                if key:
                    projected[key] = station.get(key)
            return projected if projected else station

        neighbor_payload = []
        for c, dist, centroid, sts in neighbors:
            filtered_sts = sts
            if station_type_id_filter is not None:
                filtered_sts = [s for s in filtered_sts if s.get('站点类型ID') == station_type_id_filter]
            data = [project(s) for s in filtered_sts]
            neighbor_payload.append({
                'city': c,
                'distance': dist,
                'stations_count': len(data),
                'center': {'lat': round(centroid[0], 6), 'lon': round(centroid[1], 6)},
                'stations': data
            })

        return jsonify({
            'status': 'success',
            'city_query': city_name,
            'k': k,
            'center': {'lat': round(target_center[0], 6), 'lon': round(target_center[1], 6)},
            'fields': effective_fields,
            'station_type_id_filter': station_type_id_filter,
            'neighbors': neighbor_payload
        })

    except Exception as e:
        logger.error(f"按城市周边查询站点失败: {e}")
        return jsonify({'status':'error','message':f'查询失败: {str(e)}'}), 500

# 按城市查询辖内所有站点（支持可选返回字段）
@app.route('/api/station-district/by-city', methods=['GET'])
def get_stations_by_city():
    """根据城市名称查询该城市下辖所有站点

    可选字段(fields)逗号分隔：name,code,lat,lon,district,township,type_id
    默认返回：站点名称、唯一编码、经纬度、所属区县、所属乡镇、站点类型ID
    支持站点类型ID筛选：station_type_id参数，默认不筛选
    """
    try:
        city_name = request.args.get('city_name')
        if not city_name:
            return jsonify({
                'status': 'error',
                'message': '请提供城市名称参数 city_name'
            }), 400

        # 获取站点类型ID筛选参数
        station_type_id_param = request.args.get('station_type_id')
        station_type_id_filter = None
        if station_type_id_param:
            try:
                station_type_id_filter = float(station_type_id_param)
            except ValueError:
                return jsonify({
                    'status': 'error',
                    'message': f'站点类型ID参数格式错误: {station_type_id_param}'
                }), 400

        # 解析可选字段
        fields_param = request.args.get('fields', '').strip()
        requested_fields = [f.strip().lower() for f in fields_param.split(',') if f.strip()] if fields_param else []

        # 字段映射表
        field_map = {
            'name': '站点名称',
            'code': '唯一编码',
            'lat': '纬度',
            'lon': '经度',
            'district': '所属区县',
            'township': '乡镇',
            'type_id': '站点类型ID'
        }

        # 默认字段（新增站点类型ID）
        default_fields = ['name', 'code', 'lat', 'lon', 'district', 'township', 'type_id']
        effective_fields = requested_fields if requested_fields else default_fields

        # 过滤该城市下的所有站点（大小写不敏感，支持包含匹配，如“广州”匹配“广州市”）
        city_lower = city_name.lower()
        city_stations = [s for s in finder.stations
                         if city_lower in str(s.get('所属城市', '')).lower()
                         or str(s.get('所属城市', '')).lower() in city_lower]

        # 应用站点类型ID筛选
        if station_type_id_filter is not None:
            city_stations = [s for s in city_stations 
                           if s.get('站点类型ID') == station_type_id_filter]

        # 构造输出
        def project(station):
            projected = {}
            for f in effective_fields:
                key = field_map.get(f)
                if key:
                    projected[key] = station.get(key)
            return projected if projected else station

        data = [project(s) for s in city_stations]

        # 生成站点类型ID统计信息
        type_id_stats = {}
        for station in city_stations:
            type_id = station.get('站点类型ID')
            if type_id is not None:
                type_id_stats[type_id] = type_id_stats.get(type_id, 0) + 1

        return jsonify({
            'status': 'success',
            'city_query': city_name,
            'station_type_id_filter': station_type_id_filter,
            'total': len(data),
            'fields': effective_fields,
            'station_type_stats': type_id_stats,
            'data': data
        })

    except Exception as e:
        logger.error(f"按城市查询站点失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

@app.route('/api/station-district/by-station-name', methods=['GET'])
def get_station_district_by_name():
    """根据站点名称查询站点所在区县信息"""
    try:
        station_name = request.args.get('station_name')
        top_k = int(request.args.get('top_k', 1))

        if not station_name:
            return jsonify({
                'status': 'error',
                'message': '请提供站点名称参数 station_name'
            }), 400

        district_info = finder.get_station_district_by_name(station_name, top_k)

        if not district_info:
            return jsonify({
                'status': 'error',
                'message': f'未找到名称包含 "{station_name}" 的站点'
            }), 404

        return jsonify({
            'status': 'success',
            'data': district_info
        })

    except Exception as e:
        logger.error(f"查询站点区县信息失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# ======== 企业查询相关API ========

# 根据经纬度查询附近企业
@app.route('/api/enterprises/by-coordinates', methods=['GET'])
def find_enterprises_by_coordinates():
    """根据经纬度查询附近企业"""
    try:
        # 获取请求参数
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        max_distance = float(request.args.get('max_distance', 5.0))
        max_results = int(request.args.get('max_results', 100))
        industry_filter = request.args.get('industry_filter')

        # 获取排放阈值过滤参数
        emission_threshold = {}
        for pollutant in ['SO2', 'NOx', 'PM2.5', 'PM10', 'CO', 'VOCs']:
            threshold = request.args.get(f'{pollutant}_threshold')
            if threshold:
                emission_threshold[pollutant] = float(threshold)

        # 查询企业
        results = enterprise_engine.find_enterprises_by_coordinates(
            lat, lon, max_distance, max_results, industry_filter,
            emission_threshold if emission_threshold else None
        )

        return jsonify({
            'status': 'success',
            'total': len(results),
            'query_params': {
                'lat': lat,
                'lon': lon,
                'max_distance': max_distance,
                'max_results': max_results,
                'industry_filter': industry_filter,
                'emission_threshold': emission_threshold
            },
            'data': results
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"查询附近企业失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 根据站点编码查询附近企业
@app.route('/api/enterprises/by-station-code', methods=['GET'])
def find_enterprises_by_station_code():
    """根据站点编码查询附近企业"""
    try:
        # 获取请求参数
        station_code = request.args.get('station_code')
        max_distance = float(request.args.get('max_distance', 5.0))
        max_results = int(request.args.get('max_results', 100))
        industry_filter = request.args.get('industry_filter')

        if not station_code:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_code'
            }), 400

        # 获取排放阈值过滤参数
        emission_threshold = {}
        for pollutant in ['SO2', 'NOx', 'PM2.5', 'PM10', 'CO', 'VOCs']:
            threshold = request.args.get(f'{pollutant}_threshold')
            if threshold:
                emission_threshold[pollutant] = float(threshold)

        # 查询企业
        results = enterprise_engine.find_enterprises_by_station_code(
            station_code, finder, max_distance, max_results, industry_filter,
            emission_threshold if emission_threshold else None
        )

        return jsonify({
            'status': 'success',
            'total': len(results),
            'query_params': {
                'station_code': station_code,
                'max_distance': max_distance,
                'max_results': max_results,
                'industry_filter': industry_filter,
                'emission_threshold': emission_threshold
            },
            'data': results
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"查询附近企业失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 根据站点名称查询附近企业
@app.route('/api/enterprises/by-station-name', methods=['GET'])
def find_enterprises_by_station_name():
    """根据站点名称查询附近企业"""
    try:
        # 获取请求参数
        station_name = request.args.get('station_name')
        max_distance = float(request.args.get('max_distance', 5.0))
        max_results = int(request.args.get('max_results', 100))
        industry_filter = request.args.get('industry_filter')
        simple_result = request.args.get('simple_result', 'false').lower() == 'true'

        if not station_name:
            return jsonify({
                'status': 'error',
                'message': '缺少必需参数: station_name'
            }), 400

        # 获取排放阈值过滤参数
        emission_threshold = {}
        for pollutant in ['SO2', 'NOx', 'PM2.5', 'PM10', 'CO', 'VOCs']:
            threshold = request.args.get(f'{pollutant}_threshold')
            if threshold:
                emission_threshold[pollutant] = float(threshold)

        # 查询企业
        results = enterprise_engine.find_enterprises_by_station_name(
            station_name, finder, max_distance, max_results, industry_filter,
            emission_threshold if emission_threshold else None
        )

        # 如果需要简化结果，只保留企业名称和经纬度
        if simple_result:
            results = [enterprise_engine._simplify_enterprise_result(enterprise) for enterprise in results]

        return jsonify({
            'status': 'success',
            'total': len(results),
            'query_params': {
                'station_name': station_name,
                'max_distance': max_distance,
                'max_results': max_results,
                'industry_filter': industry_filter,
                'emission_threshold': emission_threshold,
                'simple_result': simple_result
            },
            'data': results
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"查询附近企业失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 获取行业统计信息
@app.route('/api/enterprises/industry-stats', methods=['GET'])
def get_industry_statistics():
    """获取指定范围内的行业统计信息"""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        max_distance = float(request.args.get('max_distance', 10.0))

        stats = enterprise_engine.get_industry_statistics(lat, lon, max_distance)

        return jsonify({
            'status': 'success',
            'query_params': {
                'lat': lat,
                'lon': lon,
                'max_distance': max_distance
            },
            'data': stats
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"获取行业统计失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 获取排放汇总信息
@app.route('/api/enterprises/emission-summary', methods=['GET'])
def get_emission_summary():
    """获取指定范围内的排放汇总信息"""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        max_distance = float(request.args.get('max_distance', 10.0))

        summary = enterprise_engine.get_emission_summary(lat, lon, max_distance)

        return jsonify({
            'status': 'success',
            'query_params': {
                'lat': lat,
                'lon': lon,
                'max_distance': max_distance
            },
            'data': summary
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"获取排放汇总失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 获取排放量最高的企业
@app.route('/api/enterprises/top-emission', methods=['GET'])
def get_top_emission_enterprises():
    """获取指定范围内某种污染物排放量最高的企业"""
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        max_distance = float(request.args.get('max_distance', 10.0))
        pollutant = request.args.get('pollutant', 'VOCs')
        top_n = int(request.args.get('top_n', 10))

        results = enterprise_engine.get_top_emission_enterprises(
            lat, lon, max_distance, pollutant, top_n
        )

        return jsonify({
            'status': 'success',
            'total': len(results),
            'query_params': {
                'lat': lat,
                'lon': lon,
                'max_distance': max_distance,
                'pollutant': pollutant,
                'top_n': top_n
            },
            'data': results
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'参数错误: {str(e)}'
        }), 400
    except Exception as e:
        logger.error(f"获取高排放企业失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 根据企业名称搜索企业（支持单个和批量查询）
@app.route('/api/enterprises/search', methods=['GET', 'POST'])
def search_enterprises_by_name():
    """根据企业名称搜索企业，支持单个名称和批量名称数组查询"""
    try:
        if request.method == 'GET':
            # GET方法：单个企业名称查询
            enterprise_name = request.args.get('enterprise_name')
            max_results = int(request.args.get('max_results', 50))

            if not enterprise_name:
                return jsonify({
                    'status': 'error',
                    'message': '缺少必需参数: enterprise_name'
                }), 400

            results = enterprise_engine.search_enterprises_by_name(enterprise_name, max_results)

            return jsonify({
                'status': 'success',
                'total': len(results),
                'query_params': {
                    'enterprise_name': enterprise_name,
                    'max_results': max_results,
                    'search_mode': 'single'
                },
                'data': results
            })

        else:
            # POST方法：批量企业名称数组查询
            data = request.get_json()

            if not data:
                return jsonify({
                    'status': 'error',
                    'message': '请求体不能为空'
                }), 400

            # 支持两种格式：
            # 1. {"enterprise_names": ["name1", "name2", "name3"]}
            # 2. {"enterprise_name": "single_name"}
            enterprise_names = data.get('enterprise_names')
            enterprise_name = data.get('enterprise_name')
            max_results = int(data.get('max_results', 500))

            if enterprise_names:
                # 批量查询模式
                if not isinstance(enterprise_names, list):
                    return jsonify({
                        'status': 'error',
                        'message': 'enterprise_names 必须是字符串数组'
                    }), 400

                if len(enterprise_names) == 0:
                    return jsonify({
                        'status': 'error',
                        'message': 'enterprise_names 数组不能为空'
                    }), 400

                results = enterprise_engine.search_enterprises_by_names(enterprise_names, max_results)

                return jsonify({
                    'status': 'success',
                    'total': len(results),
                    'query_params': {
                        'enterprise_names': enterprise_names,
                        'enterprise_names_count': len(enterprise_names),
                        'max_results': max_results,
                        'search_mode': 'batch'
                    },
                    'data': results
                })

            elif enterprise_name:
                # 单个查询模式（POST方式）
                results = enterprise_engine.search_enterprises_by_name(enterprise_name, max_results)

                return jsonify({
                    'status': 'success',
                    'total': len(results),
                    'query_params': {
                        'enterprise_name': enterprise_name,
                        'max_results': max_results,
                        'search_mode': 'single'
                    },
                    'data': results
                })

            else:
                return jsonify({
                    'status': 'error',
                    'message': '缺少必需参数: enterprise_name 或 enterprise_names'
                }), 400

    except Exception as e:
        logger.error(f"搜索企业失败: {e}")
        return jsonify({
            'status': 'error',
            'message': f'查询失败: {str(e)}'
        }), 500

# 根路径说明
@app.route('/')
def index():
    return jsonify({
        'message': '附近站点查找服务（支持名称查询、区县信息和企业查询）',
        'version': '3.0.0',
        'endpoints': {
            '附近站点查询': {
                'by_station_code': '/api/nearest-stations/by-station-code?station_code=xxx&max_distance=xxx&max_results=xxx',
                'by_station_name': '/api/nearest-stations/by-station-name?station_name=xxx&max_distance=xxx&max_results=xxx',
                'by_coordinates': '/api/nearest-stations/by-coordinates?lat=xxx&lon=xxx&max_distance=xxx&max_results=xxx',
                'dify_by_station_code': '/api/nearest-stations/dify/by-station-code (POST)',
                'dify_by_station_name': '/api/nearest-stations/dify/by-station-name (POST)',
                'dify_by_coordinates': '/api/nearest-stations/dify/by-coordinates (POST)'
            },
            '区县信息查询': {
                'by_station_code': '/api/station-district/by-station-code?station_code=xxx',
                'by_district_name': '/api/station-district/by-district-name?district_name=xxx',
                'by_station_name': '/api/station-district/by-station-name?station_name=xxx',
                'summary': '/api/station-district/summary'
            },
            '企业查询': {
                'by_coordinates': '/api/enterprises/by-coordinates?lat=xxx&lon=xxx&max_distance=xxx&max_results=xxx&industry_filter=xxx&[污染物]_threshold=xxx',
                'by_station_code': '/api/enterprises/by-station-code?station_code=xxx&max_distance=xxx&max_results=xxx&industry_filter=xxx',
                'by_station_name': '/api/enterprises/by-station-name?station_name=xxx&max_distance=xxx&max_results=xxx&industry_filter=xxx',
                'industry_stats': '/api/enterprises/industry-stats?lat=xxx&lon=xxx&max_distance=xxx',
                'emission_summary': '/api/enterprises/emission-summary?lat=xxx&lon=xxx&max_distance=xxx',
                'top_emission': '/api/enterprises/top-emission?lat=xxx&lon=xxx&max_distance=xxx&pollutant=xxx&top_n=xxx',
                'search': '/api/enterprises/search?enterprise_name=xxx&max_results=xxx'
            }
        },
        '支持的污染物类型': ['SO2', 'NOx', 'PM2.5', 'PM10', 'CO', 'VOCs'],
        '数据统计': {
            'stations_count': len(finder.stations) if finder else 0,
            'enterprises_count': enterprise_engine.get_total_count() if enterprise_engine else 0
        }
    })

if __name__ == '__main__':
    # 初始化服务（依赖修复后的查找器）
    if not init_nearest_stations_service():
        logger.error("服务初始化失败，退出程序")
        sys.exit(1)
    
    # 启动服务（使用9095端口，开启调试模式）
    app.run(host='0.0.0.0', port=9095, debug=True)