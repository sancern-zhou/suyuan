"""
FACSIMILE Mechanism Loader

解析FACSIMILE格式的化学机理文件(.fac)，提取物种和反应信息。

支持的机理:
- RACM2 (102物种, 504反应) - 来自参考项目OBM-deliver_20200901

参考:
- D:\溯源\参考\OBM-deliver_20200901\ekma_v0\ekma.fac
"""

import os
import re
import json
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
import structlog

# 稀疏矩阵支持 - 【优化】加速p/d矩阵运算
try:
    from scipy import sparse
    SPARSE_AVAILABLE = True
except ImportError:
    SPARSE_AVAILABLE = False
    structlog.get_logger().warning("scipy_not_available", message="Sparse matrix optimization disabled. Install scipy for faster computation.")

logger = structlog.get_logger()

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
MECHANISMS_DIR = os.path.join(MODULE_DIR, "mechanisms")


@dataclass
class Reaction:
    """化学反应数据类"""
    index: int
    rate_expr: str
    reactants: List[Tuple[str, float]] = field(default_factory=list)
    products: List[Tuple[str, float]] = field(default_factory=list)
    rate_constant: float = 0.0


@dataclass
class RACM2Mechanism:
    """RACM2机理数据类"""
    name: str
    num_species: int
    num_reactions: int
    species_list: List[str]
    species_indices: Dict[str, int]
    reactions: List[Reaction]
    rate_expressions: Dict[int, str]
    production_matrix: Optional[np.ndarray] = None
    destruction_matrix: Optional[np.ndarray] = None


# RACM2物种名称列表 (102种)
RACM2_SPECIES = [
    # 索引 0-9
    "O3P",      # O(3P) 原子氧
    "O1D",      # O(1D) 激发态氧
    "O3",       # 臭氧
    "NO",       # 一氧化氮
    "NO2",      # 二氧化氮
    "NO3",      # 硝酸根自由基
    "N2O5",     # 五氧化二氮
    "HNO3",     # 硝酸
    "HNO4",     # 过氧硝酸
    "H2O2",     # 过氧化氢
    # 索引 10-19
    "CO",       # 一氧化碳
    "HO",       # 羟基自由基 (OH)
    "HO2",      # 过氧氢自由基
    "SO2",      # 二氧化硫
    "SULF",     # 硫酸
    "CH4",      # 甲烷
    "ETH",      # 乙烷
    "HC3",      # 丙烷类 (C3烷烃)
    "HC5",      # 戊烷类 (C5烷烃)
    "HC8",      # 辛烷类 (C8烷烃)
    # 索引 20-29
    "ETE",      # 乙烯
    "OLT",      # 末端烯烃
    "OLI",      # 内部烯烃
    "DIEN",     # 二烯烃
    "ISO",      # 异戊二烯
    "API",      # α-蒎烯
    "LIM",      # 柠檬烯
    "TOL",      # 甲苯
    "XYL",      # 二甲苯
    "CSL",      # 甲酚
    # 索引 30-39
    "HCHO",     # 甲醛
    "ALD",      # 乙醛
    "KET",      # 酮类
    "GLY",      # 乙二醛
    "MGLY",     # 甲基乙二醛
    "DCB",      # 不饱和二羰基
    "MACR",     # 甲基丙烯醛
    "UDD",      # 不饱和二羰基醇
    "HKET",     # 羟基酮
    "ONIT",     # 有机硝酸酯
    # 索引 40-49
    "PAN",      # 过氧乙酰硝酸酯
    "TPAN",     # 过氧丙酰硝酸酯
    "MPAN",     # 甲基过氧乙酰硝酸酯
    "OP1",      # 甲基过氧化氢
    "OP2",      # 高级过氧化氢
    "PAA",      # 过氧乙酸
    "ORA1",     # 甲酸
    "ORA2",     # 乙酸
    "MO2",      # 甲基过氧自由基
    "ETHP",     # 乙基过氧自由基
    # 索引 50-59
    "HC3P",     # C3烷基过氧自由基
    "HC5P",     # C5烷基过氧自由基
    "HC8P",     # C8烷基过氧自由基
    "ETEP",     # 乙烯基过氧自由基
    "OLTP",     # 末端烯基过氧自由基
    "OLIP",     # 内部烯基过氧自由基
    "ISOP",     # 异戊二烯过氧自由基
    "APIP",     # α-蒎烯过氧自由基
    "LIMP",     # 柠檬烯过氧自由基
    "TOLP",     # 甲苯过氧自由基
    # 索引 60-69
    "XYLP",     # 二甲苯过氧自由基
    "CSLP",     # 甲酚过氧自由基
    "ACO3",     # 乙酰过氧自由基
    "TCO3",     # 丙酰过氧自由基
    "KETP",     # 酮基过氧自由基
    "OLNN",     # 烯烃硝酸酯过氧自由基1
    "OLND",     # 烯烃硝酸酯过氧自由基2
    "ADCN",     # 醛类硝酸酯过氧自由基
    "ADDC",     # 芳烃加成产物
    "XO2",      # 额外RO2
    # 索引 70-79
    "N2O",      # 一氧化二氮
    "H2",       # 氢气
    "H2O",      # 水
    "O2",       # 氧气
    "N2",       # 氮气
    "M",        # 第三体
    "TERP",     # 萜烯类总和
    "BENZ",     # 苯
    "BENZP",    # 苯过氧自由基
    "EPX",      # 环氧化物
    # 索引 80-89
    "PHEN",     # 苯酚
    "MCT",      # 甲基儿茶酚
    "MAHP",     # 甲基过氧化氢醇
    "ISHP",     # 异戊二烯过氧化氢
    "MACP",     # 甲基丙烯醛过氧自由基
    "MCP",      # MACR过氧自由基
    "MVKP",     # MVK过氧自由基
    "UALP",     # 不饱和醛过氧自由基
    "HPC52O2",  # HPALD过氧自由基
    "HPALD",    # 过氧化醛
    # 索引 90-101
    "PACALD",   # 过氧乙酰醛
    "CO2H3CHO", # 羟基丙烯醛
    "HO12CO3C4",# 丁烯二醇醛
    "IEPOX",    # 异戊二烯环氧化物
    "MVK",      # 甲基乙烯基酮
    "HMVK",     # 羟基MVK
    "HMAC",     # 羟基MACR
    "DIBOO",    # 二异丁烯过氧自由基
    "MAOO",     # MACR臭氧化物
    "HC3N",     # C3硝酸酯
    "HC5N",     # C5硝酸酯
    "HC8N",     # C8硝酸酯
]


class FacsimileParser:
    """
    FACSIMILE格式机理文件解析器
    
    解析.fac文件，提取:
    1. 物种数量和反应数量
    2. 速率常数表达式 k<i>=...
    3. 反应速率表达式 v<i>=k<i>*c<j>*c<k>
    4. 生成/消耗矩阵 p<i>=..., d<i>=...
    """
    
    def __init__(self):
        self.num_species = 0
        self.num_reactions = 0
        self.rate_expressions: Dict[int, str] = {}
        self.reaction_rates: Dict[int, str] = {}  # v<i>=表达式
        self.production: Dict[int, Dict[int, float]] = {}
        self.destruction: Dict[int, Dict[int, float]] = {}
    
    def parse(self, filepath: str) -> RACM2Mechanism:
        """
        解析FACSIMILE机理文件
        
        Args:
            filepath: .fac文件路径
        
        Returns:
            RACM2Mechanism对象
        """
        # 解析FACSIMILE文件
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # 提取物种和反应数量
        self._parse_header(content)
        
        # 提取速率常数表达式
        self._parse_rate_constants(content)
        
        # 提取反应速率表达式 v<i>=k<i>*c<j>*c<k>
        self._parse_reaction_rates(content)
        
        # 提取生成/消耗矩阵
        self._parse_production_destruction(content)
        
        # 构建机理对象
        mechanism = RACM2Mechanism(
            name="RACM2",
            num_species=self.num_species,
            num_reactions=self.num_reactions,
            species_list=RACM2_SPECIES[:self.num_species],
            species_indices={s: i for i, s in enumerate(RACM2_SPECIES[:self.num_species])},
            reactions=[],
            rate_expressions=self.rate_expressions
        )

        return mechanism
    
    def _parse_header(self, content: str):
        """解析文件头部，提取物种和反应数量"""
        # INTEGER #nvar 102;
        nvar_match = re.search(r'INTEGER\s+#nvar\s+(\d+)', content)
        if nvar_match:
            self.num_species = int(nvar_match.group(1))
        
        # INTEGER #nreac 504;
        nreac_match = re.search(r'INTEGER\s+#nreac\s+(\d+)', content)
        if nreac_match:
            self.num_reactions = int(nreac_match.group(1))
    
    def _parse_rate_constants(self, content: str):
        """解析速率常数表达式"""
        # 匹配 k<index,*>=expression;
        # 使用 re.DOTALL 让 . 匹配换行符，处理跨行表达式
        pattern = r'k<(\d+),\*>=(.+?);'
        matches = re.findall(pattern, content, re.DOTALL)

        for idx_str, expr in matches:
            idx = int(idx_str)
            # 清理表达式：移除换行符和多余空格
            expr = expr.replace('\n', '').replace('\r', '')
            expr = ' '.join(expr.split())  # 压缩多个空格为单个
            expr = expr.strip()
            # 转换FACSIMILE语法到Python
            expr = self._convert_expression(expr)
            self.rate_expressions[idx] = expr
    
    def _convert_expression(self, expr: str) -> str:
        """
        将FACSIMILE表达式转换为Python可执行格式
        
        FACSIMILE语法:
        - @ 表示指数运算
        - D-xx 表示科学计数法
        - s<i,j> 表示参数
        - c<i,j> 表示浓度
        """
        # 替换科学计数法 1.5D-12 -> 1.5e-12
        expr = re.sub(r'(\d+\.?\d*)D([+-]?\d+)', r'\1e\2', expr)
        
        # 替换指数运算 @( -> **(
        expr = expr.replace('@', '**')
        
        # 替换参数索引 s<i,*> -> params[i]
        expr = re.sub(r's<(\d+),\*>', r'params[\1]', expr)
        expr = re.sub(r's<(\d+),0>', r'params[\1]', expr)
        
        # 替换浓度索引 c<i,*> -> conc[i]
        # fac文件使用0-based索引，与Python一致
        # 例如: c<5,*>(fac) = NO2 = conc[5](Python)
        expr = re.sub(r'c<(\d+),\*>', r'conc[\1]', expr)
        expr = re.sub(r'c<(\d+),0>', r'conc[\1]', expr)
        
        # 替换数学函数
        expr = expr.replace('AMAX', 'max')
        expr = expr.replace('AMIN', 'min')
        expr = expr.replace('EXP', 'np.exp')
        expr = expr.replace('exp', 'np.exp')
        expr = expr.replace('log10', 'np.log10')
        expr = expr.replace('COS', 'np.cos')
        expr = expr.replace('SIN', 'np.sin')
        
        return expr
    
    def _parse_reaction_rates(self, content: str):
        """
        解析反应速率表达式 v<i>=k<i>*c<j>*c<k>

        例如:
        v<0,*>=k<0,*>*c<35,*>*c<35,*>;  -> k[0]*c[35]*c[35]
        v<1,*>=k<1,*>*c<3,*>*c<35,*>;   -> k[1]*c[3]*c[35]
        """
        # 匹配 v<index,*>=expression;
        # 使用 re.DOTALL 处理跨行表达式
        pattern = r'v<(\d+),\*>=(.+?);'
        matches = re.findall(pattern, content, re.DOTALL)

        for idx_str, expr in matches:
            idx = int(idx_str)
            # 清理表达式：移除换行符和多余空格
            expr = expr.replace('\n', '').replace('\r', '')
            expr = ' '.join(expr.split())
            expr = expr.strip()
            # 转换表达式
            expr = self._convert_reaction_rate_expr(expr)
            self.reaction_rates[idx] = expr

        logger.debug(
            "reaction_rates_parsed",
            count=len(self.reaction_rates)
        )
    
    def _convert_reaction_rate_expr(self, expr: str) -> str:
        """
        将反应速率表达式转换为Python格式
        
        v<i>=k<i>*c<j>*c<k> -> k[i]*c[j]*c[k]
        """
        # 替换k<i,*> -> k[i]
        expr = re.sub(r'k<(\d+),\*>', r'k[\1]', expr)
        expr = re.sub(r'k<(\d+),0>', r'k[\1]', expr)
        
        # 替换c<i,*> -> c[i] (fac使用0-based索引，与Python一致)
        expr = re.sub(r'c<(\d+),\*>', r'c[\1]', expr)
        expr = re.sub(r'c<(\d+),0>', r'c[\1]', expr)
        
        # 替换s<i,*> -> s[i]
        expr = re.sub(r's<(\d+),\*>', r's[\1]', expr)
        expr = re.sub(r's<(\d+),0>', r's[\1]', expr)
        
        # 替换@指数运算 -> **
        expr = expr.replace('@', '**')
        
        return expr
    
    def _parse_production_destruction(self, content: str):
        """解析生成和消耗系数矩阵"""
        # 匹配 p<species,*>=expression;
        # 使用 re.DOTALL 处理跨行表达式
        p_pattern = r'p<(\d+),\*>=(.+?);'
        p_matches = re.findall(p_pattern, content, re.DOTALL)

        for species_idx, expr in p_matches:
            idx = int(species_idx)
            # 清理表达式：移除换行符和多余空格
            expr = expr.replace('\n', '').replace('\r', '')
            expr = ' '.join(expr.split())
            self.production[idx] = self._parse_pd_expression(expr)

        # 匹配 d<species,*>=expression;
        d_pattern = r'd<(\d+),\*>=(.+?);'
        d_matches = re.findall(d_pattern, content, re.DOTALL)

        for species_idx, expr in d_matches:
            idx = int(species_idx)
            # 清理表达式：移除换行符和多余空格
            expr = expr.replace('\n', '').replace('\r', '')
            expr = ' '.join(expr.split())
            self.destruction[idx] = self._parse_pd_expression(expr)
    
    def _parse_pd_expression(self, expr: str) -> Dict[int, float]:
        """解析生成/消耗表达式，提取反应索引和系数"""
        coefficients = {}
        
        # 匹配 coef*v<reaction_idx,*>
        pattern = r'([\d.]*)\*?v<(\d+),\*>'
        matches = re.findall(pattern, expr)
        
        for coef_str, reaction_idx in matches:
            idx = int(reaction_idx)
            coef = float(coef_str) if coef_str else 1.0
            coefficients[idx] = coef
        
        return coefficients


class MechanismLoader:
    """
    化学机理加载器
    
    支持加载:
    1. RACM2机理 (102物种, 504反应)
    2. 简化机理 (12物种, 10反应) - 降级使用
    """
    
    AVAILABLE_MECHANISMS = {
        "RACM2": "racm2_ekma.fac",
        "RACM2_PO3": "racm2_po3.fac",
    }
    
    def __init__(self):
        self.parser = FacsimileParser()
        self._cache: Dict[str, RACM2Mechanism] = {}
    
    def load(self, mechanism_name: str = "RACM2") -> RACM2Mechanism:
        """
        加载指定机理
        
        Args:
            mechanism_name: 机理名称 (RACM2, RACM2_PO3)
        
        Returns:
            RACM2Mechanism对象
        """
        if mechanism_name in self._cache:
            return self._cache[mechanism_name]
        
        if mechanism_name not in self.AVAILABLE_MECHANISMS:
            logger.warning(
                "mechanism_not_found",
                requested=mechanism_name,
                available=list(self.AVAILABLE_MECHANISMS.keys())
            )
            mechanism_name = "RACM2"
        
        filename = self.AVAILABLE_MECHANISMS[mechanism_name]
        filepath = os.path.join(MECHANISMS_DIR, filename)
        
        if not os.path.exists(filepath):
            logger.error("mechanism_file_not_found", filepath=filepath)
            raise FileNotFoundError(f"Mechanism file not found: {filepath}")
        
        mechanism = self.parser.parse(filepath)
        self._cache[mechanism_name] = mechanism
        
        return mechanism
    
    def get_species_list(self, mechanism_name: str = "RACM2") -> List[str]:
        """获取物种列表"""
        mechanism = self.load(mechanism_name)
        return mechanism.species_list
    
    def get_species_index(self, species_name: str, mechanism_name: str = "RACM2") -> int:
        """获取物种索引"""
        mechanism = self.load(mechanism_name)
        return mechanism.species_indices.get(species_name, -1)
    
    def is_available(self, mechanism_name: str) -> bool:
        """检查机理是否可用"""
        if mechanism_name not in self.AVAILABLE_MECHANISMS:
            return False
        
        filename = self.AVAILABLE_MECHANISMS[mechanism_name]
        filepath = os.path.join(MECHANISMS_DIR, filename)
        return os.path.exists(filepath)


class RACM2ODESystem:
    """
    RACM2完整ODE求解系统

    实现完整的RACM2化学机理ODE:
    - 102个物种
    - 504个反应
    - 基于FACSIMILE格式的p/d矩阵
    - 预计算k值缓存（ekma.kv风格）
    - 稀疏矩阵加速（可选）

    ODE方程: dc/dt = p - d
    其中:
    - p<i> = Σ(产率系数 * 反应速率)  对所有生成物种i的反应
    - d<i> = Σ(消耗系数 * 反应速率)  对所有消耗物种i的反应
    """

    def __init__(self, mechanism: RACM2Mechanism, parser: "FacsimileParser"):
        self.mechanism = mechanism
        self.num_species = mechanism.num_species
        self.num_reactions = mechanism.num_reactions
        self.rate_expressions = mechanism.rate_expressions

        # 生成和损失系数矩阵 {species_idx: {reaction_idx: coefficient}}
        self.production = parser.production
        self.destruction = parser.destruction

        # 反应速率表达式 {reaction_idx: expression}
        self.reaction_rates = parser.reaction_rates

        # 编译后的速率函数缓存
        self._rate_funcs: Dict[int, Callable] = {}
        self._compile_rate_functions()

        # 【优化1】构建稀疏矩阵（加速p/d计算）
        self._use_sparse = SPARSE_AVAILABLE
        if self._use_sparse:
            self._build_sparse_matrices()
        else:
            self.production_matrix = None
            self.destruction_matrix = None

        # 【优化2】预计算k值缓存（ekma.kv风格）
        self._k_cache: Optional[np.ndarray] = None
        self._k_params: Optional[Dict] = None
        self._k_cache_dir = os.path.join(MODULE_DIR, "k_cache")
        self._load_k_cache()  # 尝试加载预计算缓存

    # ========== 【优化1】稀疏矩阵实现 ==========

    def _build_sparse_matrices(self):
        """
        构建稀疏的生成/损失矩阵

        矩阵形状: (num_species, num_reactions)
        production_matrix[species, reaction] = 产率系数
        destruction_matrix[species, reaction] = 消耗系数
        """
        if not SPARSE_AVAILABLE:
            logger.warning("scipy_not_available_sparse_disabled")
            return

        # 构建 COO 格式稀疏矩阵
        p_rows, p_cols, p_data = [], [], []
        d_rows, d_cols, d_data = [], [], []

        # 生成矩阵
        for species_idx, reactions in self.production.items():
            for reaction_idx, coef in reactions.items():
                p_rows.append(species_idx)
                p_cols.append(reaction_idx)
                p_data.append(coef)

        # 损失矩阵
        for species_idx, reactions in self.destruction.items():
            for reaction_idx, coef in reactions.items():
                d_rows.append(species_idx)
                d_cols.append(reaction_idx)
                d_data.append(coef)

        # 转换为 CSR 格式（适合矩阵向量乘法）
        self.production_matrix = sparse.csr_matrix(
            (p_data, (p_rows, p_cols)),
            shape=(self.num_species, self.num_reactions)
        )
        self.destruction_matrix = sparse.csr_matrix(
            (d_data, (d_rows, d_cols)),
            shape=(self.num_species, self.num_reactions)
        )

        # 记录非零元素数量
        p_nnz = len(p_data)
        d_nnz = len(d_data)
        total_elements = self.num_species * self.num_reactions

    def _calculate_dydt_dense(self, v: np.ndarray) -> np.ndarray:
        """
        原始稠密方法计算dydt（作为备用或验证）
        """
        dydt = np.zeros(self.num_species)

        for species_idx in range(self.num_species):
            # 生成项
            if species_idx in self.production:
                for reaction_idx, coef in self.production[species_idx].items():
                    if reaction_idx < len(v):
                        dydt[species_idx] += coef * v[reaction_idx]

            # 损失项
            if species_idx in self.destruction:
                for reaction_idx, coef in self.destruction[species_idx].items():
                    if reaction_idx < len(v):
                        dydt[species_idx] -= coef * v[reaction_idx]

        return dydt

    # ========== 【优化2】k值缓存实现 ==========

    def _load_k_cache(self) -> bool:
        """
        加载预计算的k值缓存

        缓存文件格式: k_cache/default.json

        Returns:
            是否成功加载缓存
        """
        os.makedirs(self._k_cache_dir, exist_ok=True)

        # 默认缓存路径
        default_cache_path = os.path.join(self._k_cache_dir, "default.json")

        if not os.path.exists(default_cache_path):
            return False

        try:
            with open(default_cache_path, 'r') as f:
                cache_data = json.load(f)

            self._k_cache = np.array(cache_data['k_values'])
            self._k_params = cache_data['params']

            return True

        except Exception as e:
            return False

    def _save_k_cache(self, temperature: float, pressure: float,
                      solar_zenith_angle: float):
        """
        保存k值缓存供后续使用
        """
        # 计算标准条件下的k值
        k_values = self._precompute_rate_constants(
            temperature=temperature,
            pressure=pressure,
            solar_zenith_angle=solar_zenith_angle,
            relative_humidity=0.5
        )

        cache_data = {
            'k_values': k_values.tolist(),
            'params': {
                'temperature': temperature,
                'pressure': pressure,
                'solar_zenith_angle': solar_zenith_angle
            },
            'created_at': datetime.now().isoformat(),
            'mechanism': 'RACM2',
            'num_species': self.num_species,
            'num_reactions': self.num_reactions,
            'description': '预计算的RACM2速率常数，标准大气条件'
        }

        cache_path = os.path.join(self._k_cache_dir, "default.json")
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)

    def _compile_rate_functions(self):
        """预编译速率常数表达式"""
        for i, expr in self.rate_expressions.items():
            try:
                # 【修复】确保lambda参数顺序与调用顺序一致
                # 调用顺序: _rate_funcs[i](params, conc, np, max, min)
                # lambda必须匹配: params, conc, ...
                code = f"lambda params, conc, np, max, min: {expr}"
                self._rate_funcs[i] = eval(code)
            except Exception as e:
                logger.debug(f"rate_compile_error", reaction=i, error=str(e))
                self._rate_funcs[i] = lambda p, c, n, mx, mn: 1e-20

    def _precompute_rate_constants(
        self,
        temperature: float,
        pressure: float,
        solar_zenith_angle: float,
        relative_humidity: float = 0.5
    ) -> np.ndarray:
        """
        【优化】预计算所有反应速率常数（ekma.kv风格）

        对于CONST参数（参考项目使用），k值只计算一次并缓存。
        这避免了每次ODE评估时重复计算504个k值。

        Args:
            temperature: 温度 (K)
            pressure: 压力 (Pa)
            solar_zenith_angle: 太阳天顶角 (度)
            relative_humidity: 相对湿度 (0-1)

        Returns:
            预计算的速率常数数组 (大小: num_reactions)
        """
        # 构建参数数组
        params = self._build_params(
            temperature, pressure, solar_zenith_angle,
            relative_humidity, np.zeros(self.num_species)
        )

        # 预计算所有k值
        k = np.zeros(self.num_reactions)

        for i in range(self.num_reactions):
            if i in self._rate_funcs:
                try:
                    with np.errstate(all='ignore'):
                        val = self._rate_funcs[i](params, np.zeros(self.num_species), np, max, min)
                    if np.isfinite(val) and val > 0:
                        # 【关键修复】不要过度限制k值，特别是光解速率
                        # J_NO2约5e-4，O3+NO约1e-14，不应该统一限制为1e-6
                        if val > 1e-3:
                            k[i] = val  # 光解速率可以很大
                        else:
                            k[i] = max(val, 1e-30)  # 双分子反应保持极小值
                    else:
                        k[i] = 1e-30
                except Exception:
                    k[i] = 1e-30
            else:
                k[i] = 1e-30

        return np.maximum(k, 1e-30)

    def get_cached_k(
        self,
        temperature: float,
        pressure: float,
        solar_zenith_angle: float,
        relative_humidity: float = 0.5
    ) -> np.ndarray:
        """
        获取预计算的k值（带缓存）

        如果参数没有变化，返回缓存的k值；
        否则重新计算并更新缓存。
        首次运行时自动保存缓存。

        Args:
            temperature: 温度 (K)
            pressure: 压力 (Pa)
            solar_zenith_angle: 太阳天顶角 (度)
            relative_humidity: 相对湿度 (0-1)

        Returns:
            速率常数数组
        """
        current_params = {
            'temperature': temperature,
            'pressure': pressure,
            'solar_zenith_angle': solar_zenith_angle,
            'relative_humidity': relative_humidity
        }

        # 检查是否需要重新计算
        needs_recompute = (
            self._k_cache is None or
            self._k_params is None or
            self._k_params != current_params
        )

        if needs_recompute:
            # 重新计算k值
            self._k_cache = self._precompute_rate_constants(
                temperature, pressure, solar_zenith_angle, relative_humidity
            )
            self._k_params = current_params

            # 【优化】首次运行或参数变化时保存缓存
            cache_path = os.path.join(self._k_cache_dir, "default.json")
            if not os.path.exists(cache_path):
                self._save_k_cache(temperature, pressure, solar_zenith_angle)

            logger.debug(
                "k_values_recomputed",
                temperature=temperature,
                pressure=pressure,
                solar_zenith_angle=solar_zenith_angle
            )

        return self._k_cache.copy()  # 返回副本，避免外部修改
    
    def calculate_dydt(
        self,
        y: np.ndarray,
        t: float,
        temperature: float,
        pressure: float,
        solar_zenith_angle: float,
        relative_humidity: float = 0.5
    ) -> np.ndarray:
        """
        计算ODE右端项 dy/dt

        【优化】使用预计算k值缓存 + 稀疏矩阵加速p/d计算

        Args:
            y: 物种浓度向量 (molecules/cm³)
            t: 时间 (秒)
            temperature: 温度 (K)
            pressure: 压力 (Pa)
            solar_zenith_angle: 太阳天顶角 (度)
            relative_humidity: 相对湿度 (0-1)

        Returns:
            浓度变化率向量 (molecules/cm³/s)
        """
        # 确保非负浓度
        conc = np.maximum(y, 0)

        # 【优化】获取预计算的k值（使用缓存）
        k = self.get_cached_k(
            temperature, pressure, solar_zenith_angle, relative_humidity
        )

        # 构建参数（只用于需要浓度相关的反应）
        params = self._build_params(
            temperature, pressure, solar_zenith_angle,
            relative_humidity, conc
        )

        # 抑制数值计算警告
        with np.errstate(all='ignore'):
            # 计算反应速率 v = k * [A] * [B]
            v = self._calculate_reaction_rates(k, conc, params)

            # 【优化】使用稀疏矩阵或原始方法计算dydt
            if self._use_sparse and self.production_matrix is not None:
                # 稀疏矩阵方法: dydt = P @ v - D @ v
                production = self.production_matrix @ v
                destruction = self.destruction_matrix @ v
                dydt = production - destruction
            else:
                # 原始稠密方法
                dydt = self._calculate_dydt_dense(v)

        # 处理可能的 NaN/Inf
        dydt = np.nan_to_num(dydt, nan=0.0, posinf=0.0, neginf=0.0)

        return dydt
    
    def _build_params(
        self,
        temperature: float,
        pressure: float,
        solar_zenith_angle: float,
        relative_humidity: float,
        conc: np.ndarray
    ) -> np.ndarray:
        """
        构建FACSIMILE参数数组

        关键修复：设置正确的光解速率常数（参考项目实测值）
        - J_NO2 (NO2光解): 5.73e-4 s^-1 (实测值，来自data_2019_06_28_r.xls)
        - J_O3 (O3光解): 约1e-5 s^-1

        这些值是O3能否正确增长的关键
        """
        params = np.zeros(100)

        # 空气浓度 M (molecules/cm³)
        M = pressure / (1.38e-23 * temperature) * 1e-6

        # 基本物理参数
        params[2] = temperature  # 温度 (K)
        params[3] = pressure     # 压力 (Pa)
        params[4] = M            # 空气浓度

        # 太阳天顶角
        cos_sza = max(0.0, np.cos(np.radians(solar_zenith_angle)))

        # 【关键修复】设置正确的光解速率常数
        # 参考项目实测J_NO2值: 5.73e-4 s^-1 (来自data_2019_06_28_r.xls)
        # J_O3 (O3光解): 约1e-5 s^-1 (白天)
        J_NO2 = 5.73e-4 * cos_sza  # NO2光解速率
        J_O3 = 1e-5 * cos_sza      # O3光解速率

        # s[16]用于O3光解反应v56
        # 原始fac中s[16,0]=1/(24*3600)=1.16e-5，约等于J_O3
        params[16] = J_O3  # s<16> = J_O3

        # s[40]用于NO2光解反应
        params[40] = J_NO2  # s<40> = J_NO2

        # s[9]在原始fac中是计算值，这里直接设置
        params[9] = J_O3  # s<9> = J_O3

        # s[15]是光解开关因子，白天=1
        params[15] = 1.0  # s<15> = 开关因子 (白天=1)

        # 固定气体浓度
        params[46] = 1.0  # 云修正因子
        params[48] = 0.0  # 云修正指数
        params[50] = 0.0  # 云修正常数

        # O2, N2浓度
        params[55] = 0.20946 * M  # O2
        params[49] = 0.78084 * M  # N2

        # 水汽浓度
        T_C = temperature - 273.15
        p_sat = 611.21 * np.exp((18.678 - T_C/234.5) * (T_C/(257.14 + T_C)))
        H2O = relative_humidity * p_sat / (1.38e-23 * temperature) * 1e-6
        params[25] = H2O

        # VOCs和NOx相关参数 (从浓度中提取)
        if len(conc) > 70:
            params[51] = conc[70] if conc[70] > 0 else 1e6  # NO3
            params[56] = conc[2] if conc[2] > 0 else 1e8   # O3

        # 更多的s参数映射 (来自.fac文件的parset)
        params[80] = 1.0  # 归一化因子

        return params
    
    def _calculate_rate_constants(
        self,
        params: np.ndarray,
        conc: np.ndarray,
        temperature: float
    ) -> np.ndarray:
        """计算所有反应的速率常数，带数值稳定性保护"""
        k = np.zeros(self.num_reactions)

        for i in range(self.num_reactions):
            if i in self._rate_funcs:
                try:
                    # 使用errstate防止溢出
                    with np.errstate(all='ignore'):
                        val = self._rate_funcs[i](params, conc, np, max, min)
                    # 【关键修复】不要过度限制k值，特别是光解速率
                    if np.isfinite(val) and val > 0:
                        if val > 1e-3:
                            k[i] = val  # 光解速率可以很大
                        else:
                            k[i] = max(val, 1e-30)  # 双分子反应保持极小值
                    else:
                        k[i] = 1e-30
                except Exception:
                    k[i] = 1e-30
            else:
                k[i] = 1e-30

        return np.maximum(k, 1e-30)  # 确保非负
    
    def _calculate_reaction_rates(
        self,
        k: np.ndarray,
        conc: np.ndarray,
        params: np.ndarray
    ) -> np.ndarray:
        """
        计算反应速率 v = k * [A] * [B]

        根据.fac文件中的v<i>=表达式计算，带数值稳定性保护
        """
        v = np.zeros(self.num_reactions)

        for i, expr in self.reaction_rates.items():
            if i < len(v):
                try:
                    # 表达式已转换为Python格式
                    local_vars = {
                        'k': k,
                        'c': conc,
                        's': params,
                        'np': np,
                    }
                    with np.errstate(all='ignore'):
                        val = eval(expr, {"__builtins__": {}}, local_vars)
                    # 检查并限制反应速率范围
                    if np.isfinite(val) and val >= 0:
                        # 反应速率上限: 限制为合理范围
                        v[i] = min(val, 1e15)  # 上限
                    else:
                        v[i] = 0.0
                except Exception:
                    v[i] = 0.0

        return np.maximum(v, 0)  # 确保非负


class RACM2RateCalculator:
    """
    RACM2速率常数计算器
    
    根据温度、压力、光照条件计算反应速率常数
    """
    
    def __init__(self, mechanism: RACM2Mechanism):
        self.mechanism = mechanism
        self.num_reactions = mechanism.num_reactions
        self.ode_system: Optional[RACM2ODESystem] = None
    
    def calculate_rates(
        self,
        temperature: float,
        pressure: float,
        concentrations: np.ndarray,
        solar_zenith_angle: float = 30.0,
        relative_humidity: float = 0.5
    ) -> np.ndarray:
        """
        计算所有反应的速率常数
        
        Args:
            temperature: 温度 (K)
            pressure: 压力 (Pa)
            concentrations: 物种浓度数组
            solar_zenith_angle: 太阳天顶角 (度)
            relative_humidity: 相对湿度 (0-1)
        
        Returns:
            速率常数数组
        """
        # 基本参数
        M = pressure / (1.38e-23 * temperature) * 1e-6  # molecules/cm³
        
        # 构建参数字典
        params = self._build_params(
            temperature, pressure, M, 
            solar_zenith_angle, relative_humidity
        )
        
        # 计算速率常数
        rates = np.zeros(self.num_reactions)
        
        for i, expr in self.mechanism.rate_expressions.items():
            if i < self.num_reactions:
                try:
                    rates[i] = self._eval_rate_expression(
                        expr, params, concentrations, temperature
                    )
                except Exception as e:
                    logger.debug(f"rate_calc_error", reaction=i, error=str(e))
                    rates[i] = 1e-20  # 默认极小值
        
        return rates
    
    def _build_params(
        self,
        temperature: float,
        pressure: float,
        M: float,
        solar_zenith_angle: float,
        relative_humidity: float
    ) -> np.ndarray:
        """构建参数数组"""
        params = np.zeros(100)
        
        # 基本物理参数
        params[2] = temperature  # 温度
        params[3] = pressure     # 压力
        params[4] = M            # 空气浓度
        
        # 光化学参数
        cos_sza = np.cos(np.radians(solar_zenith_angle))
        params[11] = max(cos_sza, 0.01)  # cos(SZA)
        
        # 湿度相关
        params[25] = relative_humidity * np.exp(21.36469 - 5339.66/temperature) / pressure * M
        
        # 光解速率因子
        j_factor = max(cos_sza, 0.0)
        params[33] = j_factor  # 光解因子
        params[15] = 1.0       # 开关因子
        params[16] = 1.0 / (24 * 3600)  # 日变化因子
        
        # O2和N2浓度
        params[55] = 0.20946 * M  # O2
        params[49] = 0.78084 * M  # N2
        
        return params
    
    def _eval_rate_expression(
        self,
        expr: str,
        params: np.ndarray,
        conc: np.ndarray,
        temperature: float
    ) -> float:
        """计算单个速率表达式"""
        # 简化常见表达式模式
        # k = A * exp(-Ea/T)
        arrhenius_match = re.match(
            r'([\d.e+-]+)\*np\.exp\(\(-1\.\)\*\(([-\d.]+)\)/params\[2\]\)',
            expr
        )
        if arrhenius_match:
            A = float(arrhenius_match.group(1))
            Ea = float(arrhenius_match.group(2))
            return A * np.exp(-Ea / temperature)
        
        # 简单常数
        try:
            return float(expr)
        except ValueError:
            pass
        
        # 完整表达式求值
        try:
            local_vars = {
                'params': params,
                'conc': conc,
                'np': np,
                'max': max,
                'min': min,
            }
            return float(eval(expr, {"__builtins__": {}}, local_vars))
        except Exception:
            return 1e-20


# 全局加载器实例
_loader = MechanismLoader()


def load_mechanism(name: str = "RACM2") -> RACM2Mechanism:
    """加载机理的便捷函数"""
    return _loader.load(name)


def get_racm2_species() -> List[str]:
    """获取RACM2物种列表"""
    return RACM2_SPECIES.copy()


def is_mechanism_available(name: str) -> bool:
    """检查机理是否可用"""
    return _loader.is_available(name)
