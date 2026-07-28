from app.tools.query.local_satellite_image_tool import LocalSatelliteImageTool


class GetSentinel5PImageTool(LocalSatelliteImageTool):
    def __init__(self) -> None:
        super().__init__(
            name="get_sentinel5p_image",
            description=(
                "读取本地 DataRegistry 中已下载并裁剪的 Sentinel-5P TROPOMI 遥感图片。"
                "支持 no2、so2、co、hcho、o3、aer_ai；不触发远程下载。"
            ),
            schema_name="satellite_s5p_catalogue",
            source_name="Copernicus Sentinel-5P TROPOMI",
        )
