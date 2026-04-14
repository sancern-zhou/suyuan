"""
Geographic Information Matcher for Query Enhancement

Layered matching strategy:
1. Venue mapping (highest priority, O(n) substring search)
2. City + Station matching (substring containment)
3. Alias expansion (predefined abbreviations)
4. Station name to code mapping (from station_district_results_with_type_id.json)
5. City/District name to code mapping (from geo_mappings.json)
"""
import json
import structlog
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = structlog.get_logger()


class GeoMatcher:
    """
    Lightweight geographic information matcher using layered matching strategy.

    Strategy:
    - Layer 1: Exact venue mapping (hash lookup + substring)
    - Layer 2: City and station substring matching
    - Layer 3: Alias expansion for common abbreviations
    - Layer 4: Station name to code mapping (from station_district_results_with_type_id.json)
    - Layer 5: City/District name to code mapping (from geo_mappings.json)

    No complex fuzzy matching or AC automaton - just simple, fast substring matching.
    """

    _instance: Optional["GeoMatcher"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Core data structures
        self.venues = {}  # venue_name -> station_name (Layer 1)
        self.venue_list = []  # For efficient substring search

        self.cities = set()  # Unique city names
        self.city_list = []  # For substring search

        self.stations = []  # Station metadata
        self.station_index = {}  # station_name -> station_data

        # Station aliases (Layer 3)
        self.station_aliases = {
            '天河': ['天河奥体', '天河五山', '天河龙洞'],
            '奥体': ['天河奥体'],
            '体育西': ['体育西'],
            '白云': ['白云嘉禾', '白云新市', '白云竹料', '白云石井', '白云江高', '白云山'],
            '番禺': ['番禺大学城', '番禺中学', '番禺大石', '番禺沙湾', '番禺大夫山', '番禺南村', '番禺亚运城'],
            '增城': ['增城荔城', '增城派潭', '增城新塘', '增城中新', '增城石滩'],
            '南沙': ['南沙街', '南沙沙螺湾', '南沙科大', '南沙榄核', '南沙黄阁', '南沙新垦', '南沙蒲州', '南沙大稳'],
            '花都': ['花都师范', '花都竹洞', '花都花东', '花都赤坭', '花都梯面'],
            '从化': ['从化天湖', '从化良口', '从化街口'],
            '黄埔': ['黄埔港', '黄埔西区', '黄埔永和', '黄埔文冲', '黄埔科学城'],
        }

        # geo_mappings.json 数据
        self.station_codes = {}  # station_name -> station_code
        self.city_codes = {}  # city_name -> city_code
        self.district_codes = {}  # district_name -> district_code

        # API名称到标准名称的映射（用于处理API返回的别名）
        self.api_name_to_standard = {}  # api_station_name -> standard_station_name

        self._load_data()
        self._initialized = True

    def _load_data(self):
        """Load geographic data from configuration files."""
        self._load_stations()
        self._load_venues()
        self._load_geo_mappings()
        logger.info(
            "geo_matcher_initialized",
            stations=len(self.stations),
            cities=len(self.cities),
            venues=len(self.venues),
            aliases=len(self.station_aliases),
            station_codes=len(self.station_codes),
            city_codes=len(self.city_codes),
            district_codes=len(self.district_codes)
        )

    def _load_stations(self):
        """Load stations and cities from station_district_results_with_type_id.json."""
        station_file = Path(__file__).parent.parent.parent / "config" / "station_district_results_with_type_id.json"

        try:
            with open(station_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            results = data.get("data", [])
            for station in results:
                station_name = station.get("站点名称", "").strip()
                city_name = station.get("城市名称", "").strip()
                station_code = station.get("唯一编码", "").strip()

                if not station_name:
                    continue

                station_data = {
                    "name": station_name,
                    "code": station_code,
                    "city": city_name,
                    "latitude": station.get("纬度", ""),
                    "longitude": station.get("经度", ""),
                }
                self.stations.append(station_data)
                self.station_index[station_name] = station_data

                # Build station_codes mapping (name -> code)
                if station_code:
                    self.station_codes[station_name] = station_code

                if city_name:
                    self.cities.add(city_name)
                    # Also add variant without "市" suffix
                    if city_name.endswith("市"):
                        self.cities.add(city_name[:-1])

            # Convert to sorted list for efficient searching
            self.city_list = sorted(self.cities, key=len, reverse=True)

            logger.info(
                "stations_loaded",
                count=len(self.stations),
                cities=len(self.cities),
                station_codes=len(self.station_codes)
            )

        except Exception as e:
            logger.error("station_load_failed", error=str(e), exc_info=True)

    def _load_venues(self):
        """Load venue-to-station mapping from markdown file."""
        venue_file = Path(__file__).parent.parent.parent.parent / "站点-体育场馆映射关系.md"

        try:
            with open(venue_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            # File is ONE long line with entries separated by spaces
            # Format: "序号\t站点\t场馆列表 序号\t站点\t场馆列表 ..."
            # Split by regex: space followed by digit + tab
            import re
            entries = re.split(r'\s+(?=\d+\t)', content)

            for entry in entries:
                entry = entry.strip()
                if not entry:
                    continue

                # Parse format: "序号\t站点名称\t场馆1、场馆2、场馆3"
                parts = entry.split('\t')
                if len(parts) >= 3:
                    station_name = parts[1].strip()
                    venues_str = parts[2].strip()

                    # Split multiple venues
                    venues = [
                        v.strip()
                        for v in venues_str.replace('、', ',').split(',')
                    ]

                    for venue in venues:
                        if venue:
                            self.venues[venue] = station_name

            # Sort by length (longest first) for greedy matching
            self.venue_list = sorted(self.venues.keys(), key=len, reverse=True)

            logger.info("venues_loaded", count=len(self.venues))

        except Exception as e:
            logger.error("venue_load_failed", error=str(e), exc_info=True)

    def _load_geo_mappings(self):
        """Load city/district code mappings from geo_mappings.json.

        Note: Station codes are loaded from station_district_results_with_type_id.json
        in _load_stations() method.
        """
        config_file = Path(__file__).parent.parent.parent / "config" / "geo_mappings.json"

        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Only load city and district codes (stations loaded separately)
            self.city_codes = data.get("cities", {})
            self.district_codes = data.get("districts", {})

            logger.info(
                "geo_mappings_loaded",
                cities=len(self.city_codes),
                districts=len(self.district_codes)
            )

        except Exception as e:
            logger.error("geo_mappings_load_failed", error=str(e), exc_info=True)

    def stations_to_codes(self, names: List[str]) -> List[str]:
        """
        站点名称映射到编码

        Args:
            names: 站点名称列表，如 ["东莞", "新兴", "从化天湖"]

        Returns:
            站点编码列表，如 ["1037b", "1042b", "1004b"]
        """
        return self._names_to_codes(names, self.station_codes, "站点")

    def cities_to_codes(self, names: List[str]) -> List[str]:
        """
        城市名称映射到编码

        Args:
            names: 城市名称列表，如 ["广州", "深圳", "东莞"]

        Returns:
            城市编码列表，如 ["440100", "440300", "441900"]
        """
        return self._names_to_codes(names, self.city_codes, "城市")

    def districts_to_codes(self, names: List[str]) -> List[str]:
        """
        区县名称映射到编码

        Args:
            names: 区县名称列表，如 ["天河区", "白云区", "福田区"]

        Returns:
            区县编码列表，如 ["440100009", "440100001", "440300002"]
        """
        return self._names_to_codes(names, self.district_codes, "区县")

    def resolve_location(self, location: str) -> Tuple[str, str]:
        """
        解析地理位置，返回(类型, 编码)

        Args:
            location: 地理位置名称（站点、区县、城市）

        Returns:
            (类型, 编码) 元组，如 ("station", "1037b") 或 ("city", "440100")
        """
        # 先尝试站点匹配
        if location in self.station_codes:
            return "station", self.station_codes[location]

        # 再尝试区县匹配
        if location in self.district_codes:
            return "district", self.district_codes[location]

        # 最后尝试城市匹配
        if location in self.city_codes:
            return "city", self.city_codes[location]

        # 如果是编码格式（包含字母和数字），直接返回
        if any(ch.isalpha() for ch in location) and any(ch.isdigit() for ch in location):
            return "station_code", location

        # 模糊匹配
        for key, value in self.station_codes.items():
            if location in key or key in location:
                return "station", value

        for key, value in self.district_codes.items():
            if location in key or key in location:
                return "district", value

        for key, value in self.city_codes.items():
            if location in key or key in location:
                return "city", value

        logger.warning("location_not_found", location=location)
        return "unknown", ""

    def _names_to_codes(self, names: List[str], table: Dict[str, str], tag: str) -> List[str]:
        """
        通用名称到编码的映射方法

        Args:
            names: 名称列表
            table: 映射表
            tag: 类型标签（用于日志）

        Returns:
            编码列表
        """
        codes: List[str] = []

        for loc in names or []:
            loc = (loc or "").strip()
            if not loc:
                continue

            # 精确匹配
            if loc in table:
                codes.append(table[loc])
                continue

            # 如果 loc 本身就是编码格式（包含字母和数字）
            if any(ch.isalpha() for ch in loc) and any(ch.isdigit() for ch in loc):
                codes.append(loc)
                continue

            # 模糊匹配
            matched = False
            for key, value in table.items():
                if loc in key or key in loc:
                    codes.append(value)
                    logger.info(
                        "fuzzy_match_success",
                        location=loc,
                        matched_key=key,
                        code=value,
                        type=tag
                    )
                    matched = True
                    break

            if not matched:
                logger.warning("location_match_failed", location=loc, type=tag)

        return codes

    def extract_geo_entities(self, query: str) -> Dict[str, Any]:
        """
        Extract geographic entities using layered matching strategy.

        Strategy:
        1. Venue mapping (highest priority)
        2. City + Station substring matching
        3. Alias expansion

        Args:
            query: User query string

        Returns:
            Dict with extracted entities and metadata
        """
        result = {
            "venue": None,
            "venue_mapped_station": None,
            "cities": [],
            "stations": [],
            "has_venue": False,
            "has_city": False,
            "has_station": False,
        }

        # Layer 1: Venue mapping (highest priority)
        matched_venue = self._match_venue(query)
        if matched_venue:
            result["venue"] = matched_venue["venue"]
            result["venue_mapped_station"] = matched_venue["station"]
            result["has_venue"] = True

            # Also find the city of the mapped station
            station_data = self.station_index.get(matched_venue["station"])
            if station_data:
                result["cities"] = [station_data["city"]]
                result["has_city"] = True

        # Layer 2: City matching
        if not result["has_city"]:
            matched_cities = self._match_cities(query)
            if matched_cities:
                result["cities"] = matched_cities
                result["has_city"] = True

        # Layer 3: Station matching
        city_filter = result["cities"][0] if result["cities"] else None
        matched_stations = self._match_stations(query, city_filter)

        if matched_stations:
            result["stations"] = matched_stations
            result["has_station"] = True

        logger.info(
            "geo_extraction_complete",
            query=query[:50],
            has_venue=result["has_venue"],
            has_city=result["has_city"],
            has_station=result["has_station"],
            station_count=len(result["stations"])
        )

        return result

    def _match_venue(self, query: str) -> Optional[Dict[str, str]]:
        """
        Layer 1: Match venue using substring search.

        Returns first match (longest venue name first).
        """
        for venue in self.venue_list:
            if venue in query:
                return {
                    "venue": venue,
                    "station": self.venues[venue]
                }
        return None

    def _match_cities(self, query: str, top_k: int = 3) -> List[str]:
        """
        Layer 2: Match cities using substring containment.

        Returns cities sorted by length (longest first).
        """
        matched = []
        for city in self.city_list:
            if city in query:
                matched.append(city)
                if len(matched) >= top_k:
                    break
        return matched

    def _match_stations(
        self,
        query: str,
        city_filter: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Layer 3: Match stations using substring + alias expansion.

        Args:
            query: User query
            city_filter: Optional city to filter results
            top_k: Maximum results

        Returns:
            List of station metadata dicts
        """
        matched = []

        # Direct substring matching
        for station in self.stations:
            station_name = station["name"]

            # City filter
            if city_filter:
                if station["city"] != city_filter and station["city"] != f"{city_filter}市":
                    continue

            # Substring match (bidirectional)
            if station_name in query or query in station_name:
                matched.append(station)
                if len(matched) >= top_k:
                    return matched

        # Alias expansion if no direct match
        if not matched:
            for alias, station_names in self.station_aliases.items():
                if alias in query:
                    for station_name in station_names:
                        station_data = self.station_index.get(station_name)
                        if station_data:
                            # City filter
                            if city_filter:
                                if station_data["city"] != city_filter and station_data["city"] != f"{city_filter}市":
                                    continue
                            matched.append(station_data)
                            if len(matched) >= top_k:
                                break
                    if matched:
                        break

        return matched

    def format_for_llm(self, geo_entities: Dict[str, Any]) -> str:
        """
        Format extracted entities as context for LLM prompt.

        Args:
            geo_entities: Result from extract_geo_entities()

        Returns:
            Formatted string for prompt injection
        """
        if not (geo_entities["has_venue"] or geo_entities["has_city"] or geo_entities["has_station"]):
            return ""

        lines = []
        lines.append("## [地理] 候选地理信息（从查询中提取）")
        lines.append("")

        # Venue (highest priority)
        if geo_entities["has_venue"]:
            lines.append("### [场馆] 匹配到的体育场馆（广东省全运会）：")
            lines.append(f"- **场馆名称**: {geo_entities['venue']}")
            lines.append(f"- **对应站点**: {geo_entities['venue_mapped_station']}")
            lines.append("")
            lines.append("**[重要]**: 检测到体育场馆，请优先使用对应站点进行分析。")
            lines.append("")

        # Cities
        if geo_entities["has_city"]:
            lines.append("### [城市] 候选城市：")
            for city in geo_entities["cities"]:
                lines.append(f"- {city}")
            lines.append("")

        # Stations
        if geo_entities["has_station"]:
            lines.append("### [站点] 候选监测站点：")
            for station in geo_entities["stations"][:5]:
                lines.append(
                    f"- **{station['name']}** ({station['city']}) "
                    f"[编码: {station['code']}]"
                )
            lines.append("")

        lines.append("**提示**: 请从以上候选中选择最匹配的地理信息填入参数。")
        lines.append("")

        return "\n".join(lines)


# Global instance
geo_matcher = GeoMatcher()


def get_geo_matcher() -> GeoMatcher:
    """获取 GeoMatcher 单例"""
    return geo_matcher
