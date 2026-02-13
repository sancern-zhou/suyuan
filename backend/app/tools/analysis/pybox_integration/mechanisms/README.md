# Chemical Mechanism Files

本目录存放化学机理文件，用于PyBox箱模型模拟。

## 支持的机理格式

### MCM格式 (.eqn.txt)

从MCM网站(http://mcm.york.ac.uk/MCM/)导出的反应方程文件。

示例格式:
```
{1.} O3 + NO = NO2 + O2 : 1.8D-12*EXP(-1370/TEMP) ;
{2.} NO2 + hv = NO + O : J(4) ;
{3.} O + O2 + M = O3 + M : 5.6D-34*(TEMP/300)@-2.6 ;
```

### FACSIMILE格式 (.fac)

FACSIMILE模型使用的机理格式，参见参考项目:
`D:\溯源\参考\OBM-deliver_20200901\ekma_v0\ekma.fac`

## 如何获取机理文件

### 1. 从MCM网站导出

1. 访问 http://mcm.york.ac.uk/MCM/
2. 选择需要的VOC物种(如α-蒎烯)
3. 导出机理文件(.eqn格式)
4. 重命名为 `MCM_<物种名>.eqn.txt`

### 2. 使用内置简化机理

当前版本使用内置的简化O3-NOx-VOC机理，包含:
- 12种核心物种
- 10个主要反应

## 文件列表

| 文件名 | 描述 |
|--------|------|
| `MCM_APINENE.eqn.txt` | α-蒎烯完整机理(需下载) |
| `simplified_o3_nox_voc.py` | 内置简化机理(已集成) |

## 注意事项

1. 完整MCM机理可能包含数千个反应，计算较慢
2. 建议首先使用简化机理进行快速测试
3. 机理文件需要与对应的物种映射表配合使用
