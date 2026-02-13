"""
VOCs Species Mapper

将实测VOC物种名称映射到MCM/RACM2化学机理中的团簇物种。

参考:
- MCM物种命名: http://mcm.york.ac.uk/MCM/
- RACM2物种映射: VOCsList4RACM2.xlsx
"""

from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()

# 从mechanism_loader导入RACM2_SPECIES用于物种名称验证
try:
    from .mechanism_loader import RACM2_SPECIES
except ImportError:
    # 如果导入失败，定义一个空的RACM2物种列表作为降级方案
    RACM2_SPECIES = []


# ============================================================================
# MCM物种映射表 (实测中文名 → MCM物种名)
# ============================================================================
VOCS_TO_MCM_MAPPING = {
    # 烷烃类 (Alkanes)
    "甲烷": "CH4",
    "乙烷": "C2H6",
    "丙烷": "C3H8",
    "正丁烷": "NC4H10",
    "异丁烷": "IC4H10",
    "正戊烷": "NC5H12",
    "异戊烷": "IC5H12",
    "新戊烷": "NEOP",
    "正己烷": "NC6H14",
    "2-甲基戊烷": "M2PE",
    "3-甲基戊烷": "M3PE",
    "2,2-二甲基丁烷": "NEOP",
    "2,3-二甲基丁烷": "M23B",
    "正庚烷": "NC7H16",
    "正辛烷": "NC8H18",
    "正壬烷": "NC9H20",
    "正癸烷": "NC10H22",
    "正十一烷": "NC11H24",
    "正十二烷": "NC12H26",
    "环戊烷": "CYCC5H10",
    "环己烷": "CHEX",
    "甲基环戊烷": "MCYC5",
    "甲基环己烷": "MCH",
    
    # 烯烃类 (Alkenes)
    "乙烯": "C2H4",
    "丙烯": "C3H6",
    "1-丁烯": "BUT1ENE",
    "顺-2-丁烯": "CBUT2ENE",
    "反-2-丁烯": "TBUT2ENE",
    "异丁烯": "MEPROPENE",
    "1-戊烯": "PENT1ENE",
    "顺-2-戊烯": "C2PENE",
    "反-2-戊烯": "T2PENE",
    "2-甲基-1-丁烯": "M2BUT1E",
    "2-甲基-2-丁烯": "M2BUT2E",
    "3-甲基-1-丁烯": "M3BUT1E",
    "1-己烯": "HEX1ENE",
    "异戊二烯": "C5H8",
    "1,3-丁二烯": "C4H6",
    "α-蒎烯": "APINENE",
    "β-蒎烯": "BPINENE",
    "柠檬烯": "LIMONENE",
    
    # 炔烃类 (Alkynes)
    "乙炔": "C2H2",
    "丙炔": "C3H4",
    
    # 芳香烃类 (Aromatics)
    "苯": "BENZENE",
    "甲苯": "TOLUENE",
    "乙苯": "EBENZ",
    "邻-二甲苯": "OXYL", "邻二甲苯": "OXYL",
    "间-二甲苯": "MXYL", "间二甲苯": "MXYL",
    "对-二甲苯": "PXYL", "对二甲苯": "PXYL",
    "间/对-二甲苯": "MXYL",
    "苯乙烯": "STYRENE",
    "异丙苯": "IPBENZ",
    "正丙苯": "PBENZ",
    "1,3,5-三甲基苯": "TM135B", "1,3,5-三甲苯": "TM135B",
    "1,2,4-三甲基苯": "TM124B", "1,2,4-三甲苯": "TM124B",
    "1,2,3-三甲基苯": "TM123B", "1,2,3-三甲苯": "TM123B",
    "邻-乙基甲苯": "OETHTOL", "邻乙基甲苯": "OETHTOL",
    "间-乙基甲苯": "METHTOL", "间乙基甲苯": "METHTOL",
    "对-乙基甲苯": "PETHTOL", "对乙基甲苯": "PETHTOL",
    
    # 含氧VOCs (OVOCs)
    "甲醛": "HCHO",
    "乙醛": "CH3CHO",
    "丙醛": "C2H5CHO",
    "丁醛": "C3H7CHO",
    "戊醛": "C4H9CHO",
    "己醛": "C5H11CHO",
    "丙烯醛": "ACR",
    "甲基丙烯醛": "MACR",
    "苯甲醛": "BENZAL",
    "甲酮": "CH3COCH3",  # 丙酮
    "丙酮": "CH3COCH3",
    "丁酮": "MEK",
    "2-戊酮": "MPRK",
    "3-戊酮": "DIEK",
    "甲基乙烯基酮": "MVK",
    "甲醇": "CH3OH",
    "乙醇": "C2H5OH",
    "异丙醇": "IPROPOL",
    "正丁醇": "NBUTOL",
    "甲酸甲酯": "HCOOCH3",
    "乙酸甲酯": "CH3COOCH3",
    "乙酸乙酯": "CH3COOC2H5",
    
    # 卤代烃类 (Halocarbons)
    "氯甲烷": "CH3CL",
    "二氯甲烷": "CH2CL2",
    "三氯甲烷": "CHCL3",
    "四氯化碳": "CCL4",
    "氯乙烷": "C2H5CL",
    "1,2-二氯乙烷": "CH2CLCH2CL",
    "三氯乙烯": "C2HCL3",
    "四氯乙烯": "C2CL4",
    "氯苯": "CLBENZ",
}


# ============================================================================
# RACM2物种映射表 (实测英文名 → RACM2团簇物种)
# 与 mechanism_loader.py 中的 RACM2_SPECIES 对齐
# 参考: OBM-deliver_20200901/ekma_v0/ekma.fac (102物种, 504反应)
# ============================================================================
VOCS_TO_RACM2_MAPPING = {
    # ========== 烷烃类 → ETH/HC3/HC5/HC8 团簇 ==========
    "甲烷": "CH4", "methane": "CH4",
    "乙烷": "ETH", "ethane": "ETH",
    "丙烷": "HC3", "propane": "HC3",
    "正丁烷": "HC3", "n_butane": "HC3", "n-butane": "HC3",
    "异丁烷": "HC3", "isobutane": "HC3",
    "正戊烷": "HC5", "n_pentane": "HC5", "n-pentane": "HC5",
    "异戊烷": "HC5", "isopentane": "HC5",
    "新戊烷": "HC5", "neopentane": "HC5",
    "正己烷": "HC5", "n_hexane": "HC5", "n-hexane": "HC5",
    "2-甲基戊烷": "HC5", "2_methylpentane": "HC5", "isohexane": "HC5",
    "3-甲基戊烷": "HC5", "3_methylpentane": "HC5",
    "2,2-二甲基丁烷": "HC5", "2_2_dimethylbutane": "HC5",
    "2,3-二甲基丁烷": "HC5", "2_3_dimethylbutane": "HC5",
    "正庚烷": "HC8", "n_heptane": "HC8", "n-heptane": "HC8", "n-C7H16": "HC8",
    "正辛烷": "HC8", "n_octane": "HC8", "n-octane": "HC8", "n-C8H18": "HC8",
    "正壬烷": "HC8", "n_nonane": "HC8", "n-nonane": "HC8", "n-C9H20": "HC8",
    "正癸烷": "HC8", "n_decane": "HC8", "n-decane": "HC8", "n-C10H22": "HC8",
    "正十一烷": "HC8", "n_undecane": "HC8", "n-undecane": "HC8", "n-C11H24": "HC8",
    "正十二烷": "HC8", "n_dodecane": "HC8", "n-dodecane": "HC8", "n-C12H26": "HC8",
    # 支链/环状烷烃 (统一字段映射格式)
    "环戊烷": "HC5", "cyclopentane": "HC5", "c-C5H10": "HC5",
    "环己烷": "HC5", "cyclohexane": "HC5", "c-C6H12": "HC5",
    "甲基环戊烷": "HC5", "methylcyclopentane": "HC5", "c-C5H9-CH3": "HC5",
    "甲基环己烷": "HC8", "methylcyclohexane": "HC8", "c-C6H11-CH3": "HC8",
    # 统一字段映射格式的支链烷烃
    "2,2-二甲基丁烷": "HC5", "2,2-dimethylbutane": "HC5", "2,2-DMB": "HC5",
    "2,3-二甲基丁烷": "HC5", "2,3-dimethylbutane": "HC5", "2,3-DMB": "HC5",
    "2-甲基戊烷": "HC5", "2-methylpentane": "HC5", "2-MP": "HC5",
    "3-甲基戊烷": "HC5", "3-methylpentane": "HC5", "3-MP": "HC5",
    "2,4-二甲基戊烷": "HC5", "2,4-dimethylpentane": "HC5", "2,4-DMP": "HC5",
    "2,3-二甲基戊烷": "HC5", "2,3-dimethylpentane": "HC5", "2,3-DMP": "HC5",
    "2-甲基己烷": "HC5", "2-methylhexane": "HC5", "2-MH": "HC5",
    "3-甲基己烷": "HC5", "3-methylhexane": "HC5", "3-MH": "HC5",
    "2-甲基庚烷": "HC8", "2-methylheptane": "HC8", "2-MHpt": "HC8",
    "3-甲基庚烷": "HC8", "3-methylheptane": "HC8", "3-MHpt": "HC8",
    "2,2,4-三甲基戊烷": "HC8", "2,2,4-trimethylpentane": "HC8", "2,2,4-TMP": "HC8",
    "2,3,4-三甲基戊烷": "HC8", "2,3,4-trimethylpentane": "HC8", "2,3,4-TMP": "HC8",

    # ========== 烯烃类 → ETE/OLT/OLI/DIEN/ISO 团簇 ==========
    "乙烯": "ETE", "ethylene": "ETE", "ethene": "ETE",
    "丙烯": "OLT", "propene": "OLT", "propylene": "OLT",
    "1-丁烯": "OLT", "1_butene": "OLT", "1-butene": "OLT",
    "顺-2-丁烯": "OLI", "cis_2_butene": "OLI", "cis-2-butene": "OLI", "cis_2-butene": "OLI",
    "反-2-丁烯": "OLI", "trans_2_butene": "OLI", "trans-2-butene": "OLI", "trans_2-butene": "OLI",
    "异丁烯": "OLT", "isobutene": "OLT", "isobutylene": "OLT", "2_methylpropene": "OLT",
    "1-戊烯": "OLT", "1_pentene": "OLT", "1-pentene": "OLT",
    "顺-2-戊烯": "OLI", "cis_2_pentene": "OLI", "cis-2-pentene": "OLI",
    "反-2-戊烯": "OLI", "trans_2_pentene": "OLI", "trans-2-pentene": "OLI",
    "2-甲基-1-丁烯": "OLT", "2_methyl_1_butene": "OLT",
    "2-甲基-2-丁烯": "OLI", "2_methyl_2_butene": "OLI",
    "3-甲基-1-丁烯": "OLT", "3_methyl_1_butene": "OLT",
    "1-己烯": "OLT", "1_hexene": "OLT", "1-hexene": "OLT",
    "异戊二烯": "ISO", "isoprene": "ISO",
    "1,3-丁二烯": "DIEN", "1_3_butadiene": "DIEN", "1,3-butadiene": "DIEN",

    # ========== 萜烯类 → API/LIM/TERP 团簇 ==========
    "α-蒎烯": "API", "alpha_pinene": "API", "apinene": "API",
    "β-蒎烯": "API", "beta_pinene": "API", "bpinene": "API",
    "柠檬烯": "LIM", "limonene": "LIM",
    "月桂烯": "LIM", "myrcene": "LIM",
    "萜烯": "TERP", "terpene": "TERP",

    # ========== 炔烃类 → HC3 团簇 ==========
    "乙炔": "HC3", "acetylene": "HC3", "ethyne": "HC3",
    "丙炔": "HC3", "propyne": "HC3",

    # ========== 芳香烃类 → BENZ/TOL/XYL/CSL 团簇 ==========
    "苯": "BENZ", "benzene": "BENZ",
    "甲苯": "TOL", "toluene": "TOL",
    # 乙苯和二甲苯类 → XYL (二甲苯类团簇)
    "乙苯": "XYL", "ethylbenzene": "XYL",
    "邻-二甲苯": "XYL", "邻二甲苯": "XYL", "o_xylene": "XYL", "o-xylene": "XYL", "ortho_xylene": "XYL",
    "o-C8H10": "XYL",  # 统一字段映射格式
    "间-二甲苯": "XYL", "间二甲苯": "XYL", "m_xylene": "XYL", "m-xylene": "XYL", "meta_xylene": "XYL",
    "m-C8H10": "XYL",  # 统一字段映射格式
    "对-二甲苯": "XYL", "对二甲苯": "XYL", "p_xylene": "XYL", "p-xylene": "XYL", "para_xylene": "XYL",
    "p-C8H10": "XYL",  # 统一字段映射格式
    "间/对-二甲苯": "XYL", "m+p-C8H10": "XYL",  # 统一字段映射格式
    # 三甲苯类 → XYL (统一归入二甲苯类团簇)
    "1,3,5-三甲基苯": "XYL", "1,3,5-Trimethylbenzene": "XYL", "1,3,5-TMB": "XYL",
    "1,2,4-三甲基苯": "XYL", "1,2,4-Trimethylbenzene": "XYL", "1,2,4-TMB": "XYL",
    "1,2,3-三甲基苯": "XYL", "1,2,3-Trimethylbenzene": "XYL", "1,2,3-TMB": "XYL",
    # 乙基甲苯类 → XYL (统一归入二甲苯类团簇)
    "邻-乙基甲苯": "XYL", "o_ethyltoluene": "XYL", "o-ethyltoluene": "XYL", "o-ECT": "XYL",
    "间-乙基甲苯": "XYL", "m_ethyltoluene": "XYL", "m-ethyltoluene": "XYL", "m-ECT": "XYL",
    "对-乙基甲苯": "XYL", "p_ethyltoluene": "XYL", "p-ethyltoluene": "XYL", "p-ECT": "XYL",
    # 苯乙烯 → XYL (芳香烃类)
    "苯乙烯": "XYL", "styrene": "XYL",
    "异丙苯": "XYL", "isopropylbenzene": "XYL", "cumene": "XYL", "i-C9H12": "XYL",  # 异丙苯统一归入XYL
    "正丙苯": "XYL", "n_propylbenzene": "XYL", "n-propylbenzene": "XYL", "n-C9H12": "XYL",  # 正丙苯统一归入XYL

    # ========== 醛类 → HCHO/ALD/MACR 团簇 ==========
    "甲醛": "HCHO", "formaldehyde": "HCHO",
    "乙醛": "ALD", "acetaldehyde": "ALD",
    "丙醛": "ALD", "propionaldehyde": "ALD",
    "丁醛": "ALD", "butyraldehyde": "ALD", "n_butyraldehyde": "ALD",
    "戊醛": "ALD", "valeraldehyde": "ALD",
    "己醛": "ALD", "hexaldehyde": "ALD",
    "丙烯醛": "MACR", "acrolein": "MACR",
    "甲基丙烯醛": "MACR", "methacrolein": "MACR",
    "苯甲醛": "ALD", "benzaldehyde": "ALD",
    "乙二醛": "GLY", "glyoxal": "GLY",
    "甲基乙二醛": "MGLY", "methylglyoxal": "MGLY",

    # ========== 酮类 → KET 团簇 ==========
    "丙酮": "KET", "acetone": "KET",
    "丁酮": "KET", "2_butanone": "KET", "2-butanone": "KET", "MEK": "KET",
    "2-戊酮": "KET", "2_pentanone": "KET", "2-pentanone": "KET", "MPK": "KET",
    "3-戊酮": "KET", "3_pentanone": "KET", "3-pentanone": "KET",
    "甲基乙烯基酮": "MVK", "methyl_vinyl_ketone": "MVK", "MVK": "MVK",
    "甲酮": "KET", "ketone": "KET",
    "2-己酮": "KET", "2_hexanone": "KET", "2-hexanone": "KET",
    "4-甲基-2-戊酮": "KET", "4_methyl_2_pentanone": "KET", "MIBK": "KET",

    # ========== 醇类 → HC3/HC5 团簇 (按碳数) ==========
    "甲醇": "HC3", "methanol": "HC3",
    "乙醇": "HC3", "ethanol": "HC3",
    "异丙醇": "HC3", "isopropanol": "HC3", "isopropyl_alcohol": "HC3",
    "正丁醇": "HC5", "n_butanol": "HC5", "n-butanol": "HC5", "butanol": "HC5",

    # ========== 酸类 → ORA1/ORA2 团簇 ==========
    "甲酸": "ORA1", "formic_acid": "ORA1",
    "乙酸": "ORA2", "acetic_acid": "ORA2",

    # ========== 过氧化物 → OP1/OP2 团簇 ==========
    "过氧化氢": "H2O2", "hydrogen_peroxide": "H2O2",
    "甲基过氧化氢": "OP1", "methyl_hydroperoxide": "OP1",

    # ========== 卤代烃类 ==========
    "氯甲烷": "CH3CL", "chloromethane": "CH3CL", "methyl_chloride": "CH3CL",
    "二氯甲烷": "CH2CL2", "dichloromethane": "CH2CL2", "methylene_chloride": "CH2CL2",
    "三氯甲烷": "CHCL3", "chloroform": "CHCL3",
    "四氯化碳": "CCL4", "carbon_tetrachloride": "CCL4",
    "氯乙烷": "C2H5CL", "chloroethane": "C2H5CL", "ethyl_chloride": "C2H5CL",
    "1,2-二氯乙烷": "CH2CLCH2CL", "1_2_dichloroethane": "CH2CLCH2CL",
    "三氯乙烯": "C2HCL3", "trichloroethylene": "C2HCL3",
    "四氯乙烯": "C2CL4", "tetrachloroethylene": "C2CL4", "perchloroethylene": "C2CL4",
    "氯苯": "CLBENZ", "chlorobenzene": "CLBENZ",
    "1,1,1-三氯乙烷": "CH3CCL3", "1_1_1_trichloroethane": "CH3CCL3",
    "1,1,2-三氯乙烷": "CHCL2CH2CL", "1_1_2_trichloroethane": "CHCL2CH2CL",
    "1,1-二氯乙烯": "CH2CCl2", "1_1_dichloroethylene": "CH2CCl2",
    "1,2-二氯丙烷": "CH3CHClCH2Cl", "1_2_dichloropropane": "CH3CHClCH2Cl",
    "二溴一氯甲烷": "CHBr2Cl", "dibromochloromethane": "CHBr2Cl",
    "溴仿": "CHBr3", "bromoform": "CHBr3",
    "溴甲烷": "CH3Br", "bromomethane": "CH3Br", "methyl_bromide": "CH3Br",
    "三氯氟甲烷": "CCl3F", "trichlorofluoromethane": "CCl3F", "CFC-11": "CCl3F",
    "三氯三氟乙烷": "C2Cl3F3", "trichlorotrifluoroethane": "C2Cl3F3", "CFC-113": "C2Cl3F3",
    "二氯四氟乙烷": "C2Cl2F4", "dichlorotetrafluoroethane": "C2Cl2F4", "CFC-114": "C2Cl2F4",
    "氯乙烯": "C2H3Cl", "vinyl_chloride": "C2H3Cl", "vinyl_choloride": "C2H3Cl",
    "二溴化乙烯": "C2H4Br2", "ethylene_dibromide": "C2H4Br2", "1_2_dibromoethane": "C2H4Br2",
    "四氯乙烷": "C2H2Cl4", "tetrachloroethane": "C2H2Cl4",
    "顺-1,2-二氯乙烯": "C2H2Cl2", "cis_1_2_dichloroethylene": "C2H2Cl2",
    "反-1,3-二氯丙烯": "C3H4Cl2", "trans_1_3_dichloropropene": "C3H4Cl2",
    "顺-1,3-二氯丙烯": "C3H4Cl2", "cis_1_3_dichloropropene": "C3H4Cl2",
    "甲基叔丁基醚": "MTBE", "methyl_tert_butyl_ether": "MTBE", "MTBE": "MTBE",
    "甲基丙烯酸甲酯": "MMA", "methyl_methacrylate": "MMA", "MMA": "MMA",
    "肉桂醛": "CIN", "cinnamaldehyde": "CIN",
    "苄基氯": "BNZCL", "benzyl_chloride": "BNZCL",
    "二硫化碳": "CS2", "carbon_disulfide": "CS2",
    "六氯丁二烯": "C4Cl6", "hexachlorobutadiene": "C4Cl6",
    "四氢呋喃": "THF", "tetrahydrofuran": "THF",
    "乙酸乙酯": "CH3COOC2H5", "ethyl_acetate": "CH3COOC2H5",
    "乙酸乙烯酯": "CH2CHOCOOCH3", "vinyl_acetate": "CH2CHOCOOCH3",

    # ========== 无机物 ==========
    "一氧化碳": "CO", "carbon_monoxide": "CO",
    "二氧化硫": "SO2", "sulfur_dioxide": "SO2",
}

# RACM2团簇物种反向映射 (用于输出解释)
RACM2_CLUSTER_DESCRIPTION = {
    "CH4": "甲烷",
    "ETH": "乙烷",
    "HC3": "C3烷烃类 (丙烷等)",
    "HC5": "C5烷烃类 (戊烷等)",
    "HC8": "C8烷烃类 (辛烷等)",
    "ETE": "乙烯",
    "OLT": "末端烯烃 (丙烯等)",
    "OLI": "内部烯烃 (2-丁烯等)",
    "DIEN": "二烯烃 (1,3-丁二烯)",
    "ISO": "异戊二烯",
    "API": "α-蒎烯类",
    "LIM": "柠檬烯类",
    "TERP": "萜烯类",
    "BENZ": "苯",
    "TOL": "甲苯类",
    "XYL": "二甲苯类",
    "CSL": "甲酚类",
    "PHEN": "苯酚",
    "HCHO": "甲醛",
    "ALD": "醛类 (乙醛等)",
    "KET": "酮类 (丙酮等)",
    "GLY": "乙二醛",
    "MGLY": "甲基乙二醛",
    "MACR": "甲基丙烯醛",
    "MVK": "甲基乙烯基酮",
    "ORA1": "甲酸",
    "ORA2": "乙酸",
    "OP1": "甲基过氧化氢",
    "OP2": "高级过氧化氢",
    "CO": "一氧化碳",
    "SO2": "二氧化硫",
    "O3": "臭氧",
    "NO": "一氧化氮",
    "NO2": "二氧化氮",
    "H2O2": "过氧化氢",
    "PAN": "过氧乙酰硝酸酯",
}


# ============================================================================
# RACM2物种 → 简化机理物种映射
# 用于当完整RACM2 ODE系统不可用时，将RACM2物种映射到简化机理
# ============================================================================
RACM2_TO_SIMPLIFIED_MAPPING = {
    # 烷烃类 → TOLUENE (作为代表)
    "CH4": "TOLUENE",  # 甲烷
    "ETH": "TOLUENE",  # 乙烷
    "HC3": "TOLUENE",  # C3烷烃
    "HC5": "TOLUENE",  # C5烷烃
    "HC8": "TOLUENE",  # C8烷烃

    # 烯烃类 → C2H4/C3H6
    "ETE": "C2H4",     # 乙烯
    "OLT": "C3H6",     # 末端烯烃
    "OLI": "C3H6",     # 内部烯烃
    "DIEN": "C2H4",    # 二烯烃
    "ISO": "C2H4",     # 异戊二烯

    # 萜烯类 → C2H4
    "API": "C2H4",
    "LIM": "C2H4",
    "TERP": "C2H4",

    # 芳香烃 → TOLUENE
    "BENZ": "TOLUENE",
    "TOL": "TOLUENE",
    "XYL": "TOLUENE",
    "CSL": "TOLUENE",
    "PHEN": "TOLUENE",

    # 含氧VOCs → HCHO/C2H4
    "HCHO": "HCHO",
    "ALD": "HCHO",
    "KET": "C2H4",
    "GLY": "HCHO",
    "MGLY": "HCHO",
    "MACR": "C2H4",
    "MVK": "C2H4",

    # 酸类/过氧化物 → HCHO
    "ORA1": "HCHO",
    "ORA2": "HCHO",
    "OP1": "HCHO",
    "OP2": "HCHO",

    # 其他
    "CO": "CO",
    "SO2": "C2H4",  # SO2没有直接对应，映射到C2H4作为代表
}


# ============================================================================
# 简化机理物种 → RACM2物种映射
# 用于当使用完整RACM2 ODE系统时，将简化物种名称翻译为RACM2名称
# ============================================================================
SIMPLIFIED_TO_RACM2_MAPPING = {
    # ========== 烷烃类 → RACM2团簇 ==========
    "CH4": "CH4",      # 甲烷
    "C2H6": "ETH",     # 乙烷
    "C3H8": "HC3",     # 丙烷
    "NC4H10": "HC3",   # 正丁烷
    "IC4H10": "HC3",   # 异丁烷
    "n-C4H10": "HC3",  # 正丁烷 (统一字段映射格式)
    "i-C4H10": "HC3",  # 异丁烷 (统一字段映射格式)
    "NC5H12": "HC5",   # 正戊烷
    "IC5H12": "HC5",   # 异戊烷
    "n-C5H12": "HC5",  # 正戊烷 (统一字段映射格式)
    "i-C5H12": "HC5",  # 异戊烷 (统一字段映射格式)
    "NC6H14": "HC5",   # 正己烷
    "n-C6H14": "HC5",  # 正己烷 (统一字段映射格式)
    "NC7H16": "HC8",   # 正庚烷
    "n-C7H16": "HC8",  # 正庚烷 (统一字段映射格式)
    "NC8H18": "HC8",   # 正辛烷
    "n-C8H18": "HC8",  # 正辛烷 (统一字段映射格式)
    "NC9H20": "HC8",   # 正壬烷
    "n-C9H20": "HC8",  # 正壬烷 (统一字段映射格式)
    "NC10H22": "HC8",  # 正癸烷
    "n-C10H22": "HC8", # 正癸烷 (统一字段映射格式)
    "NC11H24": "HC8",  # 正十一烷
    "n-C11H24": "HC8", # 正十一烷 (统一字段映射格式)
    "NC12H26": "HC8",  # 正十二烷
    "n-C12H26": "HC8", # 正十二烷 (统一字段映射格式)
    # 支链/环状烷烃 (统一字段映射格式)
    "CYCC5H10": "HC5", # 环戊烷
    "c-C5H10": "HC5",  # 环戊烷 (统一字段映射格式)
    "CYCC6H12": "HC5", # 环己烷
    "c-C6H12": "HC5",  # 环己烷 (统一字段映射格式)
    "CHEX": "HC5",     # 环己烷
    "MCYC5": "HC5",    # 甲基环戊烷
    "c-C5H9-CH3": "HC5", # 甲基环戊烷 (统一字段映射格式)
    "MCH": "HC8",      # 甲基环己烷
    "c-C6H11-CH3": "HC8", # 甲基环己烷 (统一字段映射格式)
    # 支链烷烃 (统一字段映射格式)
    "2,2-DMB": "HC5",  # 2,2-二甲基丁烷
    "2,3-DMB": "HC5",  # 2,3-二甲基丁烷
    "2-MP": "HC5",     # 2-甲基戊烷
    "3-MP": "HC5",     # 3-甲基戊烷
    "2,4-DMP": "HC5",  # 2,4-二甲基戊烷
    "2,3-DMP": "HC5",  # 2,3-二甲基戊烷
    "2-MH": "HC5",     # 2-甲基己烷
    "3-MH": "HC5",     # 3-甲基己烷
    "2-MHpt": "HC8",   # 2-甲基庚烷
    "3-MHpt": "HC8",   # 3-甲基庚烷
    "2,2,4-TMP": "HC8", # 2,2,4-三甲基戊烷
    "2,3,4-TMP": "HC8", # 2,3,4-三甲基戊烷

    # ========== 烯烃类 → RACM2团簇 ==========
    "C2H4": "ETE",     # 乙烯
    "C3H6": "OLT",     # 丙烯
    "C4H8": "OLT",     # 丁烯
    "C4H6": "DIEN",    # 1,3-丁二烯
    "C5H8": "ISO",     # 异戊二烯
    "BUT1ENE": "OLT",   # 1-丁烯
    "CBUT2ENE": "OLI",  # 顺-2-丁烯
    "TBUT2ENE": "OLI",  # 反-2-丁烯
    "MEPROPENE": "OLT", # 异丁烯
    "PENT1ENE": "OLT",  # 1-戊烯
    "C2PENE": "OLI",   # 顺-2-戊烯
    "T2PENE": "OLI",   # 反-2-戊烯
    "APINENE": "API",   # α-蒎烯
    "BPINENE": "API",   # β-蒎烯
    "LIMONENE": "LIM",  # 柠檬烯
    # 烯烃类 (统一字段映射格式)
    "1-C4H8": "OLT",   # 1-丁烯
    "i-C4H8": "OLT",   # 异丁烯
    "1-C5H10": "OLT",  # 1-戊烯
    "cis-2-C4H8": "OLI", # 顺-2-丁烯
    "trans-2-C4H8": "OLI", # 反-2-丁烯
    "cis-2-C5H10": "OLI", # 顺-2-戊烯
    "trans-2-C5H10": "OLI", # 反-2-戊烯
    "1-C6H12": "OLT",  # 1-己烯

    # ========== 芳香烃 → RACM2团簇 ==========
    "BENZENE": "BENZ", # 苯
    "C6H6": "BENZ",    # 苯 (统一字段映射格式)
    "TOLUENE": "TOL",  # 甲苯
    "C7H8": "TOL",     # 甲苯 (统一字段映射格式)
    # 乙苯 → XYL (二甲苯类团簇)
    "EBENZ": "XYL",    # 乙苯
    "C8H10": "XYL",    # 乙苯 (统一字段映射格式)
    # 二甲苯类 → XYL
    "OXYL": "XYL",     # 邻二甲苯
    "MXYL": "XYL",     # 间二甲苯
    "PXYL": "XYL",     # 对二甲苯
    "o-C8H10": "XYL",  # 邻-二甲苯 (统一字段映射格式)
    "m-C8H10": "XYL",  # 间-二甲苯 (统一字段映射格式)
    "p-C8H10": "XYL",  # 对-二甲苯 (统一字段映射格式)
    "m+p-C8H10": "XYL",  # 间/对-二甲苯 (统一字段映射格式)
    # 苯乙烯 → XYL (芳香烃类)
    "STYRENE": "XYL",  # 苯乙烯
    "C8H8": "XYL",     # 苯乙烯 (统一字段映射格式)
    # 三甲苯类 → XYL
    "TM123B": "XYL",   # 1,2,3-三甲苯
    "TM124B": "XYL",   # 1,2,4-三甲苯
    "TM135B": "XYL",   # 1,3,5-三甲苯
    "1,2,3-TMB": "XYL",  # 1,2,3-三甲基苯 (统一字段映射格式)
    "1,2,4-TMB": "XYL",  # 1,2,4-三甲基苯 (统一字段映射格式)
    "1,3,5-TMB": "XYL",  # 1,3,5-三甲基苯 (统一字段映射格式)
    # 乙基甲苯类 → XYL
    "OETHTOL": "XYL",  # 邻乙基甲苯
    "METHTOL": "XYL",  # 间乙基甲苯
    "PETHTOL": "XYL",  # 对乙基甲苯
    "o-ECT": "XYL",    # 邻-乙基甲苯 (统一字段映射格式)
    "m-ECT": "XYL",    # 间-乙基甲苯 (统一字段映射格式)
    "p-ECT": "XYL",    # 对-乙基甲苯 (统一字段映射格式)
    # 丙基苯类 → XYL
    "i-C9H12": "XYL",  # 异丙苯 (统一字段映射格式)
    "n-C9H12": "XYL",  # 正丙苯 (统一字段映射格式)
    "CRESOL": "CSL",   # 甲酚
    "PHENOL": "PHEN",  # 苯酚

    # ========== 含氧VOCs → RACM2团簇 ==========
    "HCHO": "HCHO",    # 甲醛
    "CH3CHO": "ALD",   # 乙醛
    "CH3COCH3": "KET", # 丙酮
    "MEK": "KET",      # 丁酮
    "MACR": "MACR",    # 甲基丙烯醛
    "MVK": "MVK",      # 甲基乙烯基酮
    "ACETONE": "KET",  # 丙酮
    "CH3COCH2CH3": "KET",  # 2-丁酮

    # ========== 卤代烃 → 直接使用化学式作为物种名 ==========
    # 卤代烃在RACM2中没有对应物种，保持原样（如果RACM2不支持会跳过）
    "CH3CL": "CH3CL",      # 氯甲烷
    "CH2CL2": "CH2CL2",    # 二氯甲烷
    "CHCL3": "CHCL3",      # 三氯甲烷
    "CCL4": "CCL4",        # 四氯化碳
    "C2H5CL": "C2H5CL",   # 氯乙烷
    "CH2CLCH2CL": "CH2CLCH2CL",  # 1,2-二氯乙烷
    "C2HCL3": "C2HCL3",   # 三氯乙烯
    "C2CL4": "C2CL4",     # 四氯乙烯
    "CLBENZ": "CLBENZ",    # 氯苯
    "CH3CCL3": "CH3CCL3",  # 1,1,1-三氯乙烷
    "CHCL2CH2CL": "CHCL2CH2CL",  # 1,1,2-三氯乙烷
    "CH2CCl2": "CH2CCl2",  # 1,1-二氯乙烯
    "C2H2Cl2": "C2H2Cl2",  # 二氯乙烯
    "CH3CHClCH2Cl": "CH3CHClCH2Cl",  # 1,2-二氯丙烷
    "C2H3Cl": "C2H3Cl",   # 氯乙烯
    "C2H4Br2": "C2H4Br2", # 二溴化乙烯
    "C2H2Cl4": "C2H2Cl4", # 四氯乙烷
    "C3H4Cl2": "C3H4Cl2", # 1,3-二氯丙烯
    "CHBr2Cl": "CHBr2Cl",  # 二溴一氯甲烷
    "CHBr3": "CHBr3",      # 溴仿
    "CH3Br": "CH3Br",      # 溴甲烷
    "CCl3F": "CCl3F",     # 三氯氟甲烷 (CFC-11)
    "C2Cl3F3": "C2Cl3F3", # 三氯三氟乙烷 (CFC-113)
    "C2Cl2F4": "C2Cl2F4", # 二氯四氟乙烷 (CFC-114)
    "C4Cl6": "C4Cl6",     # 六氯丁二烯
    "CS2": "CS2",         # 二硫化碳

    # ========== 其他有机物 ==========
    "MTBE": "HC5",       # 甲基叔丁基醚 → 映射到HC5
    "MMA": "KET",       # 甲基丙烯酸甲酯 → 映射到KET
    "THF": "HC5",       # 四氢呋喃 → 映射到HC5
    "BNZCL": "BENZ",    # 苄基氯 → 映射到BENZ
    "CIN": "MACR",      # 肉桂醛 → 映射到MACR
    "CH2CHOCOOCH3": "KET",  # 乙酸乙烯酯 → 映射到KET
    "CH3COOC2H5": "KET",  # 乙酸乙酯 → 映射到KET

    # ========== 其他无机物（保持不变） ==========
    "CO": "CO",
    "SO2": "SO2",
    "O3": "O3",
    "NO": "NO",
    "NO2": "NO2",
    "H2O2": "H2O2",
    "PAN": "PAN",
}


class VOCsMapper:
    """
    VOCs物种映射器
    
    将实测VOC物种名称转换为化学机理中的物种名称。
    支持MCM和RACM2两种机理。
    """
    
    def __init__(self, mechanism: str = "MCM"):
        """
        初始化映射器
        
        Args:
            mechanism: 目标机理 ("MCM" 或 "RACM2")
        """
        self.mechanism = mechanism.upper()
        
        if self.mechanism == "MCM":
            self.mapping = VOCS_TO_MCM_MAPPING
        elif self.mechanism == "RACM2":
            self.mapping = VOCS_TO_RACM2_MAPPING
        else:
            raise ValueError(f"Unsupported mechanism: {mechanism}")
        
        logger.info(
            "vocs_mapper_initialized",
            mechanism=self.mechanism,
            species_count=len(self.mapping)
        )
    
    def map_single(self, species_name: str) -> Optional[str]:
        """
        映射单个物种
        
        Args:
            species_name: 实测物种名称(中文)
        
        Returns:
            机理物种名称，未找到返回None
        """
        return self.mapping.get(species_name)
    
    def map_concentrations(
        self,
        observed_vocs: Dict[str, float],
        aggregate_clusters: bool = True
    ) -> Dict[str, float]:
        """
        映射VOCs浓度数据

        Args:
            observed_vocs: 实测VOCs浓度 {"乙烯": 2.5, "甲苯": 3.8, ...}
            aggregate_clusters: 是否聚合到团簇物种(RACM2)

        Returns:
            机理物种浓度 {"C2H4": 2.5, "TOLUENE": 3.8, ...}
        """
        mechanism_vocs = {}
        unmapped_species = []

        for species, concentration in observed_vocs.items():
            # 跳过非浓度字段
            if species in ["time", "TimePoint", "timestamp", "date", "station"]:
                continue

            # 跳过无效浓度
            if not isinstance(concentration, (int, float)) or concentration < 0:
                continue

            mech_species = self.mapping.get(species)

            if mech_species is not None:
                if aggregate_clusters:
                    # 累加到团簇物种
                    mechanism_vocs[mech_species] = (
                        mechanism_vocs.get(mech_species, 0) + concentration
                    )
                else:
                    mechanism_vocs[mech_species] = concentration
            else:
                unmapped_species.append(species)

        if unmapped_species:
            logger.debug(
                "vocs_unmapped_species",
                count=len(unmapped_species),
                species=unmapped_species[:10]  # 只记录前10个
            )

        # 【调试】记录映射结果
        if mechanism_vocs:
            logger.debug(
                "vocs_mapped_result",
                input_species=len(observed_vocs),
                output_species=len(mechanism_vocs),
                unmapped_count=len(unmapped_species),
                mapped_concentrations=mechanism_vocs,
                total_concentration=sum(mechanism_vocs.values())
            )

        return mechanism_vocs
    
    def map_timeseries(
        self,
        vocs_data: List[Dict],
        aggregate_clusters: bool = True
    ) -> List[Dict]:
        """
        映射VOCs时序数据
        
        Args:
            vocs_data: VOCs时序数据列表
            aggregate_clusters: 是否聚合团簇
        
        Returns:
            映射后的时序数据
        """
        mapped_data = []
        
        for record in vocs_data:
            if not isinstance(record, dict):
                continue
            
            mapped_record = {}
            
            # 保留时间字段
            for time_key in ["time", "TimePoint", "timestamp", "date"]:
                if time_key in record:
                    mapped_record[time_key] = record[time_key]
                    break
            
            # 映射VOCs浓度
            mapped_vocs = self.map_concentrations(record, aggregate_clusters)
            mapped_record.update(mapped_vocs)
            
            if len(mapped_record) > 1:  # 至少有时间+1个物种
                mapped_data.append(mapped_record)
        
        logger.info(
            "vocs_timeseries_mapped",
            input_records=len(vocs_data),
            output_records=len(mapped_data)
        )
        
        return mapped_data
    
    def get_species_category(self, species_name: str) -> str:
        """
        获取物种类别
        
        Args:
            species_name: 物种名称(中文)
        
        Returns:
            类别名称
        """
        categories = {
            "烷烃": ["甲烷", "乙烷", "丙烷", "正丁烷", "异丁烷", "正戊烷", "异戊烷",
                   "正己烷", "正庚烷", "正辛烷", "环己烷", "甲基环己烷"],
            "烯烃": ["乙烯", "丙烯", "1-丁烯", "顺-2-丁烯", "反-2-丁烯", "异戊二烯",
                   "1,3-丁二烯", "α-蒎烯", "β-蒎烯", "柠檬烯"],
            "芳香烃": ["苯", "甲苯", "乙苯", "邻二甲苯", "间二甲苯", "对二甲苯",
                    "苯乙烯", "1,2,4-三甲苯", "1,3,5-三甲苯"],
            "含氧VOCs": ["甲醛", "乙醛", "丙酮", "丁酮", "甲醇", "乙醇",
                       "丙烯醛", "甲基乙烯基酮"],
            "卤代烃": ["氯甲烷", "二氯甲烷", "三氯甲烷", "四氯化碳",
                     "三氯乙烯", "四氯乙烯"],
        }
        
        for category, species_list in categories.items():
            if species_name in species_list:
                return category
        
        return "其他"
    
    def get_mapping_statistics(
        self,
        observed_vocs: Dict[str, float]
    ) -> Dict[str, any]:
        """
        获取映射统计信息
        
        Args:
            observed_vocs: 实测VOCs浓度
        
        Returns:
            统计信息
        """
        total_species = 0
        mapped_species = 0
        unmapped_list = []
        category_counts = {}
        
        for species in observed_vocs.keys():
            if species in ["time", "TimePoint", "timestamp", "date", "station"]:
                continue
            
            total_species += 1
            
            if species in self.mapping:
                mapped_species += 1
                category = self.get_species_category(species)
                category_counts[category] = category_counts.get(category, 0) + 1
            else:
                unmapped_list.append(species)
        
        return {
            "total_species": total_species,
            "mapped_species": mapped_species,
            "unmapped_species": len(unmapped_list),
            "mapping_rate": mapped_species / total_species if total_species > 0 else 0,
            "unmapped_list": unmapped_list,
            "category_distribution": category_counts
        }

    def map_to_simplified_mechanism(
        self,
        racm2_vocs: Dict[str, float]
    ) -> Dict[str, float]:
        """
        将RACM2物种映射到简化机理物种

        用于当完整RACM2 ODE系统不可用时，将映射后的RACM2物种
        转换为简化机理可识别的物种（C2H4, C3H6, TOLUENE, HCHO, CO）。

        Args:
            racm2_vocs: RACM2物种浓度 {"HC5": 10, "KET": 5, "OLT": 3, ...}

        Returns:
            简化机理物种浓度 {"TOLUENE": 15, "C2H4": 8, "C3H6": 3, ...}
        """
        simplified_vocs = {}
        unmapped_species = []

        for species, concentration in racm2_vocs.items():
            # 跳过非VOCs物种
            if species in ["O3", "NO", "NO2", "H2O2", "PAN"]:
                continue

            # 使用RACM2_TO_SIMPLIFIED_MAPPING进行映射
            simplified_species = RACM2_TO_SIMPLIFIED_MAPPING.get(species)

            if simplified_species is not None:
                simplified_vocs[simplified_species] = (
                    simplified_vocs.get(simplified_species, 0) + concentration
                )
            else:
                unmapped_species.append(species)
                # 对于未映射的物种，默认映射到TOLUENE
                simplified_vocs["TOLUENE"] = (
                    simplified_vocs.get("TOLUENE", 0) + concentration
                )

        if unmapped_species:
            logger.debug(
                "racm2_to_simplified_unmapped",
                count=len(unmapped_species),
                species=unmapped_species[:5],
                default_mapping="TOLUENE"
            )

        # 【调试】记录映射结果
        if simplified_vocs:
            logger.info(
                "racm2_to_simplified_result",
                input_species=len(racm2_vocs),
                output_species=len(simplified_vocs),
                unmapped_count=len(unmapped_species),
                simplified_concentrations=simplified_vocs,
                total_concentration=sum(simplified_vocs.values())
            )

        return simplified_vocs

    def map_to_racm2_mechanism(
        self,
        simplified_vocs: Dict[str, float]
    ) -> Dict[str, float]:
        """
        将简化机理物种名称翻译为RACM2物种名称

        用于当使用完整RACM2 ODE系统时，将简化物种名称翻译为RACM2名称。
        例如: "C2H4" -> "ETE", "TOLUENE" -> "TOL"

        Args:
            simplified_vocs: 简化机理物种浓度 {"C2H4": 5, "TOLUENE": 10, "CO": 20, ...}

        Returns:
            RACM2物种浓度 {"ETE": 5, "TOL": 10, "CO": 20, ...}
        """
        racm2_vocs = {}
        unmapped_species = []

        for species, concentration in simplified_vocs.items():
            # 跳过非VOCs物种
            if species in ["O3", "NO", "NO2", "H2O2", "PAN"]:
                racm2_vocs[species] = concentration
                continue

            # 使用SIMPLIFIED_TO_RACM2_MAPPING进行翻译
            racm2_species = SIMPLIFIED_TO_RACM2_MAPPING.get(species)

            if racm2_species is not None:
                racm2_vocs[racm2_species] = (
                    racm2_vocs.get(racm2_species, 0) + concentration
                )
            else:
                unmapped_species.append(species)
                # 对于未映射的物种，尝试直接使用（可能是RACM2原生名称）
                if species in RACM2_SPECIES:
                    racm2_vocs[species] = (
                        racm2_vocs.get(species, 0) + concentration
                    )
                else:
                    # 默认映射到HC3（作为未知VOCs的代表）
                    racm2_vocs["HC3"] = (
                        racm2_vocs.get("HC3", 0) + concentration
                    )

        if unmapped_species:
            logger.debug(
                "simplified_to_racm2_unmapped",
                count=len(unmapped_species),
                species=unmapped_species[:5],
                default_mapping="HC3"
            )

        # 【调试】记录翻译结果
        if racm2_vocs:
            logger.info(
                "simplified_to_racm2_result",
                input_species=len(simplified_vocs),
                output_species=len(racm2_vocs),
                unmapped_count=len(unmapped_species),
                racm2_concentrations=racm2_vocs,
                total_concentration=sum(racm2_vocs.values())
            )

        return racm2_vocs
