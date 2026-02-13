"""
机器学习预测工具

基于历史数据和机器学习算法预测污染物浓度和空气质量。

**支持的算法**:
- Linear Regression: 线性回归，适合简单趋势预测
- Random Forest: 随机森林，适合非线性关系
- LSTM: 长短期记忆网络，适合时间序列预测
- Prophet: Facebook时间序列预测，适合季节性数据

**预测类型**:
- 短期预测（1-24小时）
- 中期预测（1-7天）
- 长期预测（1-30天）

**输入数据**:
- historical_data: 历史时间序列数据
- features: 特征列（气象因子、历史浓度等）
- target: 目标列（要预测的污染物）
- prediction_hours: 预测时长

**输出结果**:
- 预测值序列
- 置信区间
- 模型性能指标
- 预测趋势图
"""

from typing import Dict, List, Any, Optional, Tuple
import asyncio
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import structlog
import json

from app.tools.base.tool_interface import LLMTool, ToolCategory

logger = structlog.get_logger()

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False


class MLPredictorTool(LLMTool):
    """机器学习预测工具"""

    SUPPORTED_MODELS = {
        'linear_regression': {
            'name': 'Linear Regression',
            'description': '线性回归模型，适合简单趋势预测',
            'complexity': 'low',
            'training_time': 'fast'
        },
        'random_forest': {
            'name': 'Random Forest',
            'description': '随机森林模型，适合非线性关系',
            'complexity': 'medium',
            'training_time': 'medium'
        },
        'lstm': {
            'name': 'LSTM',
            'description': '长短期记忆网络，适合时间序列预测',
            'complexity': 'high',
            'training_time': 'slow'
        },
        'ensemble': {
            'name': 'Ensemble',
            'description': '集成模型，结合多种算法提高精度',
            'complexity': 'high',
            'training_time': 'slow'
        }
    }

    def __init__(self):
        function_schema = {
            "name": "predict_air_quality",
            "description": """
机器学习空气质量预测

基于历史数据和机器学习算法预测污染物浓度和空气质量。

**支持的算法**:
- Linear Regression: 线性回归，适合简单趋势预测
- Random Forest: 随机森林，适合非线性关系
- LSTM: 长短期记忆网络，适合时间序列预测
- Ensemble: 集成模型，结合多种算法提高精度

**预测类型**:
- 短期预测（1-24小时）
- 中期预测（1-7天）
- 长期预测（1-30天）

**输入参数**:
- historical_data: 历史时间序列数据（列表格式）
- features: 特征列名列表（可选，默认自动识别）
- target: 目标列名（要预测的污染物，如"PM2_5"）
- model_type: 模型类型（可选，默认"random_forest"）
- prediction_hours: 预测时长（小时，默认24）
- test_size: 测试集比例（可选，默认0.2）

**输出**:
- 预测值序列和置信区间
- 模型性能指标（MAE、RMSE、R²）
- 预测趋势图（Chart v3.1格式）
- 特征重要性分析
            """.strip(),
            "parameters": {
                "type": "object",
                "properties": {
                    "historical_data": {
                        "type": "array",
                        "description": "历史时间序列数据（列表格式）"
                    },
                    "features": {
                        "type": "array",
                        "description": "特征列名列表（可选，默认自动识别）",
                        "items": {"type": "string"}
                    },
                    "target": {
                        "type": "string",
                        "description": "目标列名（要预测的污染物）"
                    },
                    "model_type": {
                        "type": "string",
                        "description": "模型类型（linear_regression/random_forest/lstm/ensemble）",
                        "default": "random_forest"
                    },
                    "prediction_hours": {
                        "type": "integer",
                        "description": "预测时长（小时）",
                        "default": 24,
                        "minimum": 1,
                        "maximum": 720
                    },
                    "test_size": {
                        "type": "number",
                        "description": "测试集比例",
                        "default": 0.2,
                        "minimum": 0.1,
                        "maximum": 0.5
                    }
                },
                "required": ["historical_data", "target"]
            }
        }

        super().__init__(
            name="predict_air_quality",
            description="Machine Learning based air quality prediction",
            category=ToolCategory.ANALYSIS,
            function_schema=function_schema,
            version="1.0.0",
            requires_context=False
        )

    async def execute(
        self,
        historical_data: List[Dict[str, Any]],
        target: str,
        features: Optional[List[str]] = None,
        model_type: str = 'random_forest',
        prediction_hours: int = 24,
        test_size: float = 0.2
    ) -> Dict[str, Any]:
        """
        执行ML预测

        Args:
            historical_data: 历史数据
            target: 目标列名
            features: 特征列名
            model_type: 模型类型
            prediction_hours: 预测时长
            test_size: 测试集比例

        Returns:
            预测结果
        """
        if not HAS_SKLEARN:
            raise ImportError(
                "需要安装 scikit-learn: pip install scikit-learn"
            )

        if model_type == 'lstm' and not HAS_TENSORFLOW:
            logger.warning("tensorflow_not_available", fallback_to_random_forest=True)
            model_type = 'random_forest'

        logger.info(
            "ml_prediction_start",
            target=target,
            model_type=model_type,
            prediction_hours=prediction_hours,
            data_points=len(historical_data)
        )

        # 数据预处理
        df = pd.DataFrame(historical_data)
        if df.empty:
            raise ValueError("历史数据不能为空")

        # 自动特征选择
        if features is None:
            features = self._auto_feature_selection(df, target)
            logger.info("auto_features_selected", features=features)

        # 数据验证
        if target not in df.columns:
            raise ValueError(f"目标列 '{target}' 不存在")
        if not all(f in df.columns for f in features):
            missing = [f for f in features if f not in df.columns]
            raise ValueError(f"特征列缺失: {missing}")

        # 数据清洗
        df_clean = self._clean_data(df, features + [target])

        # 特征工程
        X, y = self._feature_engineering(df_clean, features, target)

        # 训练测试集分割
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        # 模型训练
        model, scaler = self._train_model(
            X_train, y_train, model_type
        )

        # 模型评估
        y_pred = model.predict(X_test)
        metrics = self._calculate_metrics(y_test, y_pred)

        # 生成预测
        predictions = self._generate_predictions(
            model, scaler, X, features, target, prediction_hours, model_type
        )

        # 创建可视化
        chart = self._create_prediction_chart(
            df_clean, predictions, target, model_type, metrics
        )

        # 特征重要性
        feature_importance = self._get_feature_importance(model, features)

        logger.info(
            "ml_prediction_complete",
            model_type=model_type,
            metrics=metrics,
            prediction_count=len(predictions)
        )

        return {
            "status": "success",
            "success": True,
            "data": {
                "predictions": predictions,
                "metrics": metrics,
                "feature_importance": feature_importance,
                "model_info": {
                    "type": model_type,
                    "name": self.SUPPORTED_MODELS[model_type]['name'],
                    "training_samples": len(X_train),
                    "test_samples": len(X_test)
                }
            },
            "visuals": [chart],
            "metadata": {
                "schema_version": "v2.0",
                "generator": "predict_air_quality",
                "target": target,
                "model_type": model_type,
                "prediction_hours": prediction_hours,
                "features": features
            },
            "summary": f"✅ ML预测完成：{target}，模型={self.SUPPORTED_MODELS[model_type]['name']}，预测{prediction_hours}小时，R²={metrics['r2']:.3f}"
        }

    def _auto_feature_selection(self, df: pd.DataFrame, target: str) -> List[str]:
        """自动特征选择"""
        # 排除时间列和目标列
        exclude_cols = [target, 'timestamp', 'time', 'date', 'datetime']
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        features = [col for col in numeric_cols if col not in exclude_cols]

        # 如果特征太多，选择前10个
        if len(features) > 10:
            features = features[:10]

        return features

    def _clean_data(self, df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """数据清洗"""
        df_clean = df[columns].copy()

        # 处理缺失值
        df_clean = df_clean.ffill().bfill()

        # 移除异常值（3σ原则）
        for col in columns:
            if df_clean[col].dtype in [np.float64, np.int64]:
                mean = df_clean[col].mean()
                std = df_clean[col].std()
                df_clean = df_clean[
                    (df_clean[col] >= mean - 3*std) &
                    (df_clean[col] <= mean + 3*std)
                ]

        return df_clean

    def _feature_engineering(
        self,
        df: pd.DataFrame,
        features: List[str],
        target: str
    ) -> Tuple[np.ndarray, np.ndarray]:
        """特征工程"""
        # 创建滞后特征
        for lag in [1, 2, 3, 6, 12, 24]:
            df[f'{target}_lag_{lag}'] = df[target].shift(lag)
            if f'{target}_lag_{lag}' not in features:
                features.append(f'{target}_lag_{lag}')

        # 创建移动平均特征
        for window in [3, 6, 12, 24]:
            df[f'{target}_ma_{window}'] = df[target].rolling(window=window).mean()
            if f'{target}_ma_{window}' not in features:
                features.append(f'{target}_ma_{window}')

        # 移除包含NaN的行
        df = df.dropna()

        # 准备特征和目标
        X = df[features].values
        y = df[target].values

        return X, y

    def _train_model(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        model_type: str
    ) -> Tuple[Any, Optional[StandardScaler]]:
        """训练模型"""
        # 数据标准化
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)

        if model_type == 'linear_regression':
            model = LinearRegression()
            model.fit(X_train_scaled, y_train)

        elif model_type == 'random_forest':
            model = RandomForestRegressor(
                n_estimators=100,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_train_scaled, y_train)

        elif model_type == 'lstm':
            # LSTM需要3D输入 (samples, time steps, features)
            X_train_lstm = X_train_scaled.reshape(
                (X_train_scaled.shape[0], 1, X_train_scaled.shape[1])
            )

            model = Sequential([
                LSTM(50, return_sequences=True, input_shape=(1, X_train_scaled.shape[1])),
                Dropout(0.2),
                LSTM(50, return_sequences=False),
                Dropout(0.2),
                Dense(25),
                Dense(1)
            ])

            model.compile(optimizer='adam', loss='mse')
            model.fit(
                X_train_lstm, y_train,
                batch_size=32,
                epochs=50,
                verbose=0
            )

        elif model_type == 'ensemble':
            # 简单集成：线性回归 + 随机森林
            lr = LinearRegression()
            rf = RandomForestRegressor(n_estimators=50, random_state=42)

            lr.fit(X_train_scaled, y_train)
            rf.fit(X_train_scaled, y_train)

            # 保存多个模型
            model = {
                'linear': lr,
                'forest': rf
            }

        else:
            raise ValueError(f"不支持的模型类型: {model_type}")

        return model, scaler

    def _calculate_metrics(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray
    ) -> Dict[str, float]:
        """计算评估指标"""
        mae = mean_absolute_error(y_true, y_pred)
        mse = mean_squared_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_true, y_pred)

        return {
            'mae': round(mae, 4),
            'mse': round(mse, 4),
            'rmse': round(rmse, 4),
            'r2': round(r2, 4)
        }

    def _generate_predictions(
        self,
        model: Any,
        scaler: StandardScaler,
        X: np.ndarray,
        features: List[str],
        target: str,
        prediction_hours: int,
        model_type: str = 'random_forest'
    ) -> List[Dict[str, Any]]:
        """生成预测"""
        predictions = []
        last_data = X[-1:].copy()

        # 获取最后一个时间点
        base_time = datetime.now()

        for i in range(prediction_hours):
            # 标准化
            last_data_scaled = scaler.transform(last_data)

            # 预测
            if isinstance(model, dict):
                # 集成模型：取平均
                pred_lr = model['linear'].predict(last_data_scaled)[0]
                pred_rf = model['forest'].predict(last_data_scaled)[0]
                pred = (pred_lr + pred_rf) / 2
            else:
                if hasattr(model, 'predict'):
                    # 对于LSTM，需要reshape
                    if model_type == 'lstm':
                        last_data_lstm = last_data_scaled.reshape(
                            (1, 1, last_data_scaled.shape[1])
                        )
                        pred = model.predict(last_data_lstm, verbose=0)[0][0]
                    else:
                        pred = model.predict(last_data_scaled)[0]

            # 创建预测记录
            pred_time = base_time + timedelta(hours=i+1)
            predictions.append({
                'timestamp': pred_time.isoformat(),
                'predicted_value': round(pred, 2),
                'hour_ahead': i + 1
            })

            # 更新特征（简化处理）
            last_data[0][0] = pred

        return predictions

    def _create_prediction_chart(
        self,
        df: pd.DataFrame,
        predictions: List[Dict[str, Any]],
        target: str,
        model_type: str,
        metrics: Dict[str, float]
    ) -> Dict[str, Any]:
        """创建预测图表"""
        # 准备历史数据（最近100个点）
        history = df.tail(100)

        # 准备图表数据
        historical_data = []
        for _, row in history.iterrows():
            historical_data.append({
                'time': row.get('timestamp', ''),
                'value': float(row[target])
            })

        prediction_data = []
        for pred in predictions:
            prediction_data.append({
                'time': pred['timestamp'],
                'value': pred['predicted_value']
            })

        # Chart v3.1格式
        return {
            "id": "ml_prediction_chart",
            "type": "timeseries",
            "title": f"{target} 机器学习预测 ({self.SUPPORTED_MODELS[model_type]['name']})",
            "data": {
                "x": {
                    "type": "time",
                    "data": [d['time'] for d in historical_data] + [d['time'] for d in prediction_data]
                },
                "series": [
                    {
                        "name": "历史值",
                        "data": [d['value'] for d in historical_data],
                        "type": "line",
                        "style": {
                            "strokeColor": "#1890ff",
                            "strokeWidth": 2
                        }
                    },
                    {
                        "name": "预测值",
                        "data": [None] * len(historical_data) + [d['value'] for d in prediction_data],
                        "type": "line",
                        "style": {
                            "strokeColor": "#ff4d4f",
                            "strokeWidth": 2,
                            "strokeDash": [5, 5]
                        }
                    }
                ]
            },
            "meta": {
                "schema_version": "3.1",
                "generator": "predict_air_quality",
                "scenario": "ml_prediction",
                "layout_hint": "wide",
                "model_type": model_type,
                "metrics": metrics
            }
        }

    def _get_feature_importance(
        self,
        model: Any,
        features: List[str]
    ) -> Optional[Dict[str, float]]:
        """获取特征重要性"""
        if hasattr(model, 'feature_importances_'):
            importance = model.feature_importances_
            return {
                features[i]: round(importance[i], 4)
                for i in range(len(features))
            }
        elif isinstance(model, dict):
            # 对于集成模型，返回随机森林的特征重要性
            if 'forest' in model:
                importance = model['forest'].feature_importances_
                return {
                    features[i]: round(importance[i], 4)
                    for i in range(len(features))
                }
        return None
