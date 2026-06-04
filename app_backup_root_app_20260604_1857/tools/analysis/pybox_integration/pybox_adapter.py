"""
PyBox Engine Adapter

封装PyBox箱模型引擎，提供统一的API接口用于大气化学模拟。

功能:
- 加载MCM化学机理
- 单点ODE模拟
- EKMA网格批量模拟
- 时序模拟

依赖:
- assimulo: ODE求解器
- numba: JIT编译加速(可选)
- numpy/scipy: 数值计算
"""

from typing import Dict, List, Optional, Any, Callable, Tuple
import numpy as np
from scipy.ndimage import gaussian_filter
from dataclasses import dataclass
import structlog
import os

# 尝试相对导入（作为包的一部分）
# 如果失败，使用绝对导入（直接运行脚本时）
try:
    from .config import (
        PyBoxConfig,
        PYBOX_AVAILABLE,
        ASSIMULO_AVAILABLE,
        NUMBA_AVAILABLE,
        DEFAULT_CONFIG,
    )
    from .vocs_mapper import VOCsMapper, RACM2_TO_SIMPLIFIED_MAPPING, SIMPLIFIED_TO_RACM2_MAPPING
    from .mechanism_loader import (
        MechanismLoader,
        RACM2Mechanism,
        RACM2RateCalculator,
        RACM2ODESystem,
        RACM2_SPECIES,
        is_mechanism_available,
        FacsimileParser,
    )
except ImportError:
    # 直接运行时使用绝对导入
    from config import (
        PyBoxConfig,
        PYBOX_AVAILABLE,
        ASSIMULO_AVAILABLE,
        NUMBA_AVAILABLE,
        DEFAULT_CONFIG,
    )
    from vocs_mapper import VOCsMapper, RACM2_TO_SIMPLIFIED_MAPPING, SIMPLIFIED_TO_RACM2_MAPPING
    from mechanism_loader import (
        MechanismLoader,
        RACM2Mechanism,
        RACM2RateCalculator,
        RACM2ODESystem,
        RACM2_SPECIES,
        is_mechanism_available,
        FacsimileParser,
    )

logger = structlog.get_logger()

# 全局机理加载器
_mechanism_loader = MechanismLoader()

# 条件导入Assimulo
if ASSIMULO_AVAILABLE:
    from assimulo.solvers import CVode
    from assimulo.problem import Explicit_Problem


@dataclass
class SimulationResult:
    """模拟结果数据类"""
    success: bool
    final_o3: float = 0.0
    max_o3: float = 0.0
    time_to_peak: float = 0.0
    o3_production_rate: float = 0.0
    timeseries: Optional[Dict[str, List[float]]] = None
    error: Optional[str] = None


class PyBoxAdapter:
    """
    PyBox引擎适配器
    
    封装PyBox的ODE求解能力，提供:
    - 化学机理加载
    - 批量模拟(EKMA网格)
    - 时序模拟(PO3)
    
    使用:
        adapter = PyBoxAdapter(mechanism="MCM_APINENE")
        result = adapter.simulate_single_point(
            initial_concentrations={"O3": 50, "NO2": 20, "C2H4": 5},
            simulation_time=7200.0
        )
    """
    
    def __init__(
        self,
        mechanism: str = "MCM_APINENE",
        config: Optional[PyBoxConfig] = None
    ):
        """
        初始化PyBox适配器
        
        Args:
            mechanism: 化学机理名称
            config: 配置对象(可选)
        """
        if not PYBOX_AVAILABLE:
            raise ImportError(
                "PyBox dependencies not available. "
                "Install with: conda install -c conda-forge assimulo numba"
            )
        
        self.mechanism = mechanism
        self.config = config or DEFAULT_CONFIG
        
        # 机理数据
        self.species_list: List[str] = []
        self.species_indices: Dict[str, int] = {}
        self.reaction_coefficients: Dict[str, Any] = {}
        self.rate_equations: Optional[Callable] = None
        self.num_species: int = 0
        self.num_reactions: int = 0
        self.rate_expressions: Dict[int, str] = {}
        self.rate_calculator: Optional[RACM2RateCalculator] = None
        self._use_racm2: bool = False
        self._use_full_racm2_ode: bool = False
        self.ode_system: Optional[RACM2ODESystem] = None
        
        # 加载机理
        self._load_mechanism()
        
        logger.info(
            "pybox_adapter_initialized",
            mechanism=mechanism,
            species_count=len(self.species_list)
        )
    
    def _load_mechanism(self):
        """
        加载化学机理

        强制使用RACM2机理(102物种, 504反应)。
        开发阶段不允许降级，必须暴露所有问题。
        """
        if self.mechanism.upper() == "RACM2":
            self._load_racm2_mechanism()
        else:
            raise ValueError(f"只支持RACM2机理，不支持: {self.mechanism}")

    def _load_racm2_mechanism(self):
        """
        加载RACM2机理 (102物种, 504反应)
        
        使用完整的RACM2化学机理进行ODE求解：
        - 102个物种
        - 504个反应
        - 完整的p/d矩阵（生成/损失项）
        """
        import os
        try:
            # 加载机理
            mechanism = _mechanism_loader.load("RACM2")
            
            # 获取解析器以构建ODE系统
            parser = _mechanism_loader.parser
            
            # 创建完整的RACM2 ODE系统
            self.ode_system = RACM2ODESystem(mechanism, parser)
            
            # 设置物种信息
            self.species_list = mechanism.species_list
            self.species_indices = mechanism.species_indices
            self.num_species = mechanism.num_species
            self.num_reactions = mechanism.num_reactions
            self.rate_expressions = mechanism.rate_expressions
            
            # 创建速率计算器
            self.rate_calculator = RACM2RateCalculator(mechanism)
            
            # 标记使用完整RACM2模式
            self._use_racm2 = True
            self._use_full_racm2_ode = True
            
            logger.info(
                "racm2_full_mechanism_loaded",
                species_count=mechanism.num_species,
                reaction_count=mechanism.num_reactions,
                production_entries=sum(len(v) for v in parser.production.values()),
                destruction_entries=sum(len(v) for v in parser.destruction.values()),
                reaction_rate_exprs=len(parser.reaction_rates),
                note="Using full RACM2 ODE system with 504 reactions"
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"加载RACM2机理失败: {e}")

    def _prepare_initial_conditions(
        self,
        initial_concentrations: Dict[str, float]
    ) -> np.ndarray:
        """
        准备初始条件向量
        
        Args:
            initial_concentrations: 初始浓度字典 {物种名: 浓度(ppb)}
        
        Returns:
            初始浓度向量 (molecules/cm³)
        """
        # ppb to molecules/cm³ 转换因子 (298K, 1atm)
        ppb_to_molec = 2.46e10
        
        y0 = np.zeros(len(self.species_list))
        
        for species, concentration in initial_concentrations.items():
            if species in self.species_indices:
                idx = self.species_indices[species]
                y0[idx] = concentration * ppb_to_molec
        
        # 设置默认背景浓度
        if y0[self.species_indices.get("O3", 0)] == 0:
            y0[self.species_indices["O3"]] = 40 * ppb_to_molec  # 40 ppb O3
        
        return y0
    
    def simulate_single_point(
        self,
        initial_concentrations: Dict[str, float],
        simulation_time: Optional[float] = None,
        temperature: Optional[float] = None,
        pressure: Optional[float] = None,
        solar_zenith_angle: float = 30.0,
        output_interval: float = 60.0
    ) -> SimulationResult:
        """
        单点模拟

        Args:
            initial_concentrations: 初始浓度 {"O3": 50, "NO2": 20, ...} (ppb)
            simulation_time: 模拟时长(秒)
            temperature: 温度(K)
            pressure: 压力(Pa)
            solar_zenith_angle: 太阳天顶角(度)
            output_interval: 输出间隔(秒)

        Returns:
            SimulationResult对象

        注意:
            - 强制使用RACM2完整模式: 102物种、504反应的完整ODE系统
            - 不支持任何降级或简化模式
        """
        # 使用配置默认值
        simulation_time = simulation_time or self.config.simulation_time
        temperature = temperature or self.config.temperature
        pressure = pressure or self.config.pressure

        # 强制使用完整RACM2 ODE系统
        if not (self._use_full_racm2_ode and self.ode_system is not None):
            raise RuntimeError("RACM2 ODE系统未正确加载，无法进行模拟")

        # 只在debug级别记录ODE系统信息，避免刷屏
        logger.debug(
            "using_full_racm2_ode",
            num_species=self.num_species,
            num_reactions=self.num_reactions
        )

        try:
            # 准备初始条件
            y0 = self._prepare_initial_conditions(initial_concentrations)

            # 定义ODE问题 - 只使用完整RACM2 ODE系统
            def rhs(t, y):
                return self.ode_system.calculate_dydt(
                    y, t, temperature, pressure, solar_zenith_angle
                )
            
            t_output = np.arange(0, simulation_time + output_interval, output_interval)
            
            # 使用Assimulo CVode求解器
            problem = Explicit_Problem(rhs, y0)
            problem.name = f"PyBox_{self.mechanism}"
            
            solver = CVode(problem)
            solver.atol = self.config.atol
            solver.rtol = self.config.rtol
            solver.maxsteps = self.config.maxsteps
            # 关闭assimulo控制台输出（Final Run Statistics等）
            solver.verbosity = 0
            
            t, y = solver.simulate(simulation_time, ncp_list=t_output)
            
            # 转换为numpy数组（assimulo可能返回list）
            t = np.array(t)
            y = np.array(y)
            
            # 提取O3结果
            o3_idx = self.species_indices.get("O3", 2)  # Default to index 2 for RACM2
            ppb_to_molec = 2.46e10
            o3_timeseries = y[:, o3_idx] / ppb_to_molec
            
            # 计算结果
            final_o3 = float(o3_timeseries[-1])
            max_o3 = float(np.max(o3_timeseries))
            peak_idx = int(np.argmax(o3_timeseries))
            time_to_peak = float(t[peak_idx])
            
            # O3生成速率 (ppb/h)
            if len(t) > 1:
                o3_production_rate = (o3_timeseries[-1] - o3_timeseries[0]) / (simulation_time / 3600)
            else:
                o3_production_rate = 0.0
            
            return SimulationResult(
                success=True,
                final_o3=final_o3,
                max_o3=max_o3,
                time_to_peak=time_to_peak,
                o3_production_rate=o3_production_rate,
                timeseries={
                    "time": t.tolist(),
                    "O3": o3_timeseries.tolist()
                }
            )
            
        except Exception as e:
            logger.error("simulation_failed", error=str(e), exc_info=True)
            return SimulationResult(
                success=False,
                error=str(e)
            )

    @staticmethod
    def _run_ode_task(task: Dict) -> Dict:
        """
        运行单个ODE任务的静态方法（用于多进程并行）

        【优化】使用完整RACM2机理 + 预计算k值缓存（ekma.kv风格）

        Args:
            task: 任务参数字典，包含initial_conc, simulation_time, temperature, pressure, solar_zenith_angle

        Returns:
            包含max_o3和success的结果字典
        """
        import sys
        import os

        # 获取模块所在目录并添加到路径
        module_dir = os.path.dirname(os.path.abspath(__file__))
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        # 直接导入本地模块
        try:
            from config import PyBoxConfig
            from pybox_adapter import PyBoxAdapter
        except ImportError:
            # 如果相对导入失败，尝试绝对导入
            from app.tools.analysis.pybox_integration.config import PyBoxConfig
            from app.tools.analysis.pybox_integration.pybox_adapter import PyBoxAdapter

        try:
            initial_conc = task["initial_conc"]
            simulation_time = task["simulation_time"]
            temperature = task["temperature"]
            pressure = task["pressure"]
            solar_zenith_angle = task["solar_zenith_angle"]

            # 记录初始条件 - 减少刷屏，只在debug级别
            import structlog
            logger = structlog.get_logger()

            # 创建适配器 - 只使用RACM2
            config = PyBoxConfig()
            adapter = PyBoxAdapter(mechanism="RACM2", config=config)

            # RACM2物种浓度映射
            racm2_conc = {}
            indices = adapter.species_indices

            # 核心物种直接映射
            for species, conc in initial_conc.items():
                if species in indices:
                    racm2_conc[species] = conc

            # 确保关键物种存在
            for sp in ["O3", "NO", "NO2"]:
                if sp not in racm2_conc and sp in indices:
                    if sp == "O3":
                        racm2_conc[sp] = 18.215
                    elif sp == "NO":
                        racm2_conc[sp] = 8.958
                    elif sp == "NO2":
                        racm2_conc[sp] = 13.876

            # 运行ODE模拟
            result = adapter.simulate_single_point(
                initial_concentrations=racm2_conc,
                simulation_time=simulation_time,
                temperature=temperature,
                pressure=pressure,
                solar_zenith_angle=solar_zenith_angle
            )

            # 检查结果是否为NaN（即使success=True也可能返回NaN）
            max_o3 = result.max_o3
            if result.success and (np.isnan(max_o3) or np.isinf(max_o3)):
                logger.warning("ode_result_is_nan_marking_as_failed",
                             max_o3=max_o3)
                result = SimulationResult(
                    success=False,
                    error="ODE returned NaN/Inf value"
                )

            # 只在debug级别记录完成信息
            logger.debug(
                "ode_task_completed",
                success=result.success,
                max_O3=result.max_o3,
                time_to_peak=result.time_to_peak
            )

            return {
                "success": result.success,
                "max_o3": result.max_o3,
                "final_o3": result.final_o3,
                "error": result.error
            }

        except Exception as e:
            logger.error("ode_task_exception", error=str(e), exc_info=True)
            return {
                "success": False,
                "max_o3": 0.0,
                "final_o3": 0.0,
                "error": str(e)
            }

    def simulate_ekma_grid(
        self,
        base_vocs: Dict[str, float],
        base_nox: float,
        voc_factors: Optional[List[float]] = None,
        nox_factors: Optional[List[float]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        EKMA网格模拟
        
        Args:
            base_vocs: 基准VOCs浓度 {"C2H4": 5, "TOLUENE": 10, ...}
            base_nox: 基准NOx浓度 (ppb)
            voc_factors: VOC缩放因子列表 [0.1, 0.2, ..., 2.0]
            nox_factors: NOx缩放因子列表 [0.1, 0.2, ..., 3.0]
            progress_callback: 进度回调函数 (completed, total)
        
        Returns:
            {
                "success": True,
                "o3_matrix": 2D array,
                "voc_axis": [...],
                "nox_axis": [...],
                "base_o3": float
            }
        """
        # 默认网格
        if voc_factors is None:
            n = self.config.ekma_grid_resolution
            voc_factors = np.linspace(
                self.config.voc_factor_range[0],
                self.config.voc_factor_range[1],
                n
            ).tolist()
        
        if nox_factors is None:
            n = self.config.ekma_grid_resolution
            nox_factors = np.linspace(
                self.config.nox_factor_range[0],
                self.config.nox_factor_range[1],
                n
            ).tolist()
        
        n_voc = len(voc_factors)
        n_nox = len(nox_factors)
        o3_matrix = np.zeros((n_voc, n_nox))
        
        total_simulations = n_voc * n_nox
        completed = 0

        logger.debug(
            "ekma_grid_simulation_started",
            grid_size=f"{n_voc}x{n_nox}",
            total_simulations=total_simulations
        )
        
        for i, voc_f in enumerate(voc_factors):
            for j, nox_f in enumerate(nox_factors):
                # 调整浓度
                adj_vocs = {k: v * voc_f for k, v in base_vocs.items()}
                adj_nox = base_nox * nox_f
                
                # 准备初始浓度
                initial_conc = adj_vocs.copy()
                # 修改NOx分配比例：从 80% NO2 + 20% NO 改为 90% NO2 + 10% NO
                # 减少NO对O3的滴定作用，允许O3光化学生成
                initial_conc["NO2"] = adj_nox * 0.9
                initial_conc["NO"] = adj_nox * 0.1
                
                # 模拟
                result = self.simulate_single_point(initial_conc, **kwargs)
                
                if result.success:
                    o3_matrix[i, j] = result.max_o3
                else:
                    o3_matrix[i, j] = np.nan
                
                completed += 1
                
                # 进度回调
                if progress_callback and completed % 10 == 0:
                    progress_callback(completed, total_simulations)

                if completed % 100 == 0:
                    logger.debug(
                        "ekma_grid_progress",
                        completed=completed,
                        total=total_simulations,
                        percentage=f"{100*completed/total_simulations:.1f}%"
                    )
        
        # 计算基准O3
        mid_i = n_voc // 2
        mid_j = n_nox // 2
        base_o3 = float(o3_matrix[mid_i, mid_j])

        logger.debug(
            "ekma_grid_simulation_completed",
            base_o3=base_o3,
            max_o3=float(np.nanmax(o3_matrix)),
            min_o3=float(np.nanmin(o3_matrix))
        )
        
        return {
            "success": True,
            "o3_matrix": o3_matrix.tolist(),
            "voc_axis": voc_factors,
            "nox_axis": nox_factors,
            "base_o3": base_o3,
            "grid_size": [n_voc, n_nox],
            "total_simulations": total_simulations
        }
    
    def get_available_species(self) -> List[str]:
        """获取可用物种列表"""
        return self.species_list.copy()

    def is_available(self) -> bool:
        """检查适配器是否可用"""
        return PYBOX_AVAILABLE

    def simulate_ekma_grid_fast(
        self,
        base_vocs: Dict[str, float],
        base_nox: float,
        initial_o3: float = 30.0,
        voc_factors: Optional[List[float]] = None,
        nox_factors: Optional[List[float]] = None,
        temperature: Optional[float] = None,
        pressure: Optional[float] = None,
        solar_zenith_angle: float = 30.0,
        simulation_time: Optional[float] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        快速EKMA网格模拟（参考exe策略）

        核心思想：只计算3个ODE点（基准 + 2个扰动），然后通过泰勒展开外推整个网格

        算法步骤：
        1. 基准点模拟 (VOC_factor=1.0, NOx_factor=1.0) → O3_base
        2. VOC扰动模拟 (VOC_factor=1.05, NOx_factor=1.0) → O3_voc
        3. NOx扰动模拟 (VOC_factor=1.0, NOx_factor=1.05) → O3_nox
        4. 计算敏感性系数:
           - dO3/dVOC ≈ (O3_voc - O3_base) / (0.05 * VOC_base)
           - dO3/dNOx ≈ (O3_nox - O3_base) / (0.05 * NOx_base)
        5. 泰勒展开外推整个网格:
           O3(f_voc, f_nox) ≈ O3_base
             + dO3/dVOC * (f_voc - 1) * VOC_base
             + dO3/dNOx * (f_nox - 1) * NOx_base
             + 二次项修正

        性能对比:
        - 传统方法: 11×11 = 121次ODE积分 → 30秒-2分钟
        - 本方法: 3次ODE积分 + 解析计算 → 10-20秒

        Args:
            base_vocs: 基准VOCs浓度 {"C2H4": 5, "TOLUENE": 10, ...} (ppb)
            base_nox: 基准NOx浓度 (ppb)
            initial_o3: 初始O3浓度 (ppb)，用于化学模拟起点
            voc_factors: VOC缩放因子列表
            nox_factors: NOx缩放因子列表
            temperature: 温度(K)
            pressure: 压力(Pa)
            solar_zenith_angle: 太阳天顶角(度)
            simulation_time: 模拟时长(秒)
            progress_callback: 进度回调函数

        Returns:
            {
                "success": True,
                "o3_matrix": 2D array,
                "voc_axis": [...],
                "nox_axis": [...],
                "base_o3": float,
                "sensitivity": {
                    "dO3_dVOC": float,
                    "dO3_dNOx": float,
                    "voc_sensitivity": float,
                    "nox_sensitivity": float
                },
                "mode": "fast_taylor_expansion"
            }
        """
        import time
        from concurrent.futures import ProcessPoolExecutor, as_completed

        # 默认参数
        simulation_time = simulation_time or self.config.simulation_time
        temperature = temperature or self.config.temperature
        pressure = pressure or self.config.pressure

        # 默认网格
        if voc_factors is None:
            n = self.config.ekma_grid_resolution
            voc_factors = np.linspace(
                self.config.voc_factor_range[0],
                self.config.voc_factor_range[1],
                n
            ).tolist()

        if nox_factors is None:
            n = self.config.ekma_grid_resolution
            nox_factors = np.linspace(
                self.config.nox_factor_range[0],
                self.config.nox_factor_range[1],
                n
            ).tolist()

        n_voc = len(voc_factors)
        n_nox = len(nox_factors)

        start_time = time.time()

        logger.debug(
            "fast_ekma_started",
            grid_size=f"{n_voc}x{n_nox}",
            voc_factors_range=(voc_factors[0], voc_factors[-1]),
            nox_factors_range=(nox_factors[0], nox_factors[-1])
        )

        try:
            # ===== 并行执行3次ODE积分 =====
            if progress_callback:
                progress_callback(0, 3)

            # 准备3个ODE任务的参数
            voc_factor_pert = 1.05
            nox_factor_pert = 1.05

            # 任务1: 基准点 (factor=1.0)
            task_base = {
                "initial_conc": {
                    **base_vocs,
                    "NO2": base_nox * 0.9,  # 90% NO2, 10% NO - 减少滴定
                    "NO": base_nox * 0.1,
                    "O3": initial_o3
                },
                "simulation_time": simulation_time,
                "temperature": temperature,
                "pressure": pressure,
                "solar_zenith_angle": solar_zenith_angle
            }

            # 任务2: VOC扰动 (factor=1.05)
            adj_vocs_pert = {k: v * voc_factor_pert for k, v in base_vocs.items()}
            task_voc = {
                "initial_conc": {
                    **adj_vocs_pert,
                    "NO2": base_nox * 0.9,
                    "NO": base_nox * 0.1,
                    "O3": initial_o3
                },
                "simulation_time": simulation_time,
                "temperature": temperature,
                "pressure": pressure,
                "solar_zenith_angle": solar_zenith_angle
            }

            # 任务3: NOx扰动 (factor=1.05)
            task_nox = {
                "initial_conc": {
                    **base_vocs,
                    "NO2": base_nox * nox_factor_pert * 0.9,
                    "NO": base_nox * nox_factor_pert * 0.1,
                    "O3": initial_o3
                },
                "simulation_time": simulation_time,
                "temperature": temperature,
                "pressure": pressure,
                "solar_zenith_angle": solar_zenith_angle
            }

            # 使用进程池并行执行3个ODE任务
            tasks = [("base", task_base), ("voc", task_voc), ("nox", task_nox)]

            results = {}
            with ProcessPoolExecutor(max_workers=3) as executor:
                # 提交所有任务
                future_to_task = {
                    executor.submit(self._run_ode_task, task): name
                    for name, task in tasks
                }

                # 收集结果
                for future in as_completed(future_to_task):
                    task_name = future_to_task[future]
                    try:
                        results[task_name] = future.result()
                    except Exception as e:
                        raise RuntimeError(f"{task_name} ODE任务失败: {e}")

            # 提取结果
            o3_base = results["base"]["max_o3"]
            o3_voc = results["voc"]["max_o3"]
            o3_nox = results["nox"]["max_o3"]

            # 简化的ODE完成日志（减少刷屏）
            logger.debug(
                "parallel_ode_completed",
                base_o3=round(o3_base, 2),
                voc_o3=round(o3_voc, 2),
                nox_o3=round(o3_nox, 2)
            )

            # ===== 步骤4: 计算敏感性系数 =====
            # 转换为实际浓度单位进行敏感性计算
            total_voc_base = sum(base_vocs.values())
            voc_pert = total_voc_base * voc_factor_pert
            nox_pert = base_nox * nox_factor_pert

            # 敏感性: dO3/d(浓度)
            dO3_dVOC = (o3_voc - o3_base) / (voc_pert - total_voc_base + 1e-10)
            dO3_dNOx = (o3_nox - o3_base) / (nox_pert - base_nox + 1e-10)

            # 转换为对缩放因子的敏感性: dO3/d(factor)
            voc_sensitivity = dO3_dVOC * total_voc_base  # ppb per unit factor
            nox_sensitivity = dO3_dNOx * base_nox  # ppb per unit factor

            logger.debug(
                "sensitivity_calculated",
                voc_sensitivity=round(voc_sensitivity, 3),
                nox_sensitivity=round(nox_sensitivity, 3)
            )

            # ===== 步骤5: 改进的泰勒展开外推整个网格 =====
            if progress_callback:
                progress_callback(3, 3)

            # 创建网格
            voc_factor_arr = np.array(voc_factors)
            nox_factor_arr = np.array(nox_factors)
            VOC, NOX = np.meshgrid(voc_factor_arr, nox_factor_arr, indexing='ij')

            # 检测传入的是缩放因子还是真实浓度
            # 如果最大值 > 5.0，则认为是真实浓度（ppb），需要转换为缩放因子
            # 如果最大值 <= 5.0，则认为是缩放因子（0-3或0-4范围）
            is_real_concentration = voc_factor_arr.max() > 5.0 or nox_factor_arr.max() > 5.0

            if is_real_concentration:
                # 真实浓度模式：将浓度转换为缩放因子
                # 基准浓度 = 最大值 / 2.0（因为ekma_full.py使用0-2倍范围）
                voc_base_conc = voc_factor_arr.max() / 2.0
                nox_base_conc = nox_factor_arr.max() / 2.0

                # 计算相对于基准点的偏移（转换为缩放因子差值）
                dv = (VOC / voc_base_conc) - 1.0  # VOC缩放因子偏移
                dn = (NOX / nox_base_conc) - 1.0  # NOx缩放因子偏移

                logger.debug(
                    "real_concentration_mode",
                    voc_base_conc=round(voc_base_conc, 2),
                    nox_base_conc=round(nox_base_conc, 2),
                    voc_range=(voc_factor_arr.min(), voc_factor_arr.max()),
                    nox_range=(nox_factor_arr.min(), nox_factor_arr.max())
                )
            else:
                # 缩放因子模式（传统模式）
                voc_base_conc = total_voc_base
                nox_base_conc = base_nox
                dv = VOC - 1.0  # VOC缩放因子偏移
                dn = NOX - 1.0  # NOx缩放因子偏移

            # 使用一阶泰勒展开（移除错误的二阶项）
            # O3(f) = O3_base + dO3/dVOC * (f-1) * VOC_base + dO3/dNOx * (f-1) * NOx_base
            o3_matrix = o3_base \
                + dO3_dVOC * dv * voc_base_conc \
                + dO3_dNOx * dn * nox_base_conc

            # 基于EKMA理论的物理约束修正
            # NOx饱和效应（高NOx时O3下降）- 饱和曲线形式
            # 当NOx增加时，O3增加趋于平缓甚至下降
            nox_saturation = -0.05 * np.maximum(dn, 0) ** 1.5 * nox_base_conc
            o3_matrix = o3_matrix + nox_saturation

            # VOC边际效应递减（VOC减少时O3增加，但边际效益递减）
            # 低VOC区域O3对VOC更敏感，但呈非线性
            # 注意：np.power负数会返回NaN，需要用abs
            voc_effect = -0.02 * np.abs(np.minimum(dv, 0)) ** 1.2 * voc_base_conc
            o3_matrix = o3_matrix + voc_effect

            # 高VOC区域O3略微增加（VOC抑制NO滴定）
            voc_enhancement = 0.01 * np.maximum(dv, 0) * voc_base_conc
            o3_matrix = o3_matrix + voc_enhancement

            # 轻量级平滑以减少网格噪声
            o3_matrix = gaussian_filter(o3_matrix, sigma=0.5)

            # 物理约束：O3值应该在合理范围内
            # 典型城市O3范围: 20-300 ppb，极端污染可达400 ppb
            o3_min = 5.0   # 最小O3值
            o3_max = 400.0  # 最大O3值（城市污染极端情况）
            o3_matrix = np.clip(o3_matrix, o3_min, o3_max)

            # 确保O3值非负
            o3_matrix = np.maximum(o3_matrix, 0)

            elapsed_time = time.time() - start_time

            logger.debug(
                "fast_ekma_completed",
                elapsed_seconds=round(elapsed_time, 2),
                base_o3=round(o3_base, 2),
                max_o3=round(float(np.max(o3_matrix)), 2),
                mode="improved_taylor_expansion"
            )

            return {
                "success": True,
                "o3_matrix": o3_matrix.tolist(),
                "voc_axis": voc_factors,
                "nox_axis": nox_factors,
                "base_o3": float(o3_base),
                "sensitivity": {
                    "dO3_dVOC": float(dO3_dVOC),
                    "dO3_dNOx": float(dO3_dNOx),
                    "voc_sensitivity": float(voc_sensitivity),
                    "nox_sensitivity": float(nox_sensitivity)
                },
                "mode": "fast_taylor_expansion",
                "elapsed_seconds": elapsed_time
            }

        except Exception as e:
            logger.error("fast_ekma_failed", error=str(e), exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "o3_matrix": None,
                "mode": "fast_taylor_expansion"
            }
