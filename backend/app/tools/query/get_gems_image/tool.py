from app.tools.query.local_satellite_image_tool import LocalSatelliteImageTool


class GetGemsImageTool(LocalSatelliteImageTool):
    def __init__(self) -> None:
        super().__init__(
            name="get_gems_image",
            description=(
                "读取本地 DataRegistry 中已下载的 GEMS 遥感图片。"
                "支持 HCHO 等产品，优先返回许昌周边裁剪覆盖图；不触发远程下载。"
            ),
            schema_name="satellite_gems_catalogue",
            source_name="NIER GEMS Level-2",
        )
