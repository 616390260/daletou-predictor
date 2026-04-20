"""
预测模型集合
"""
from .base import BaseModel, Ticket
from .bayesian_model import BayesianModel
from .ensemble_model import EnsembleModel
from .frequency_model import FrequencyModel
from .genetic_model import GeneticModel
from .lstm_model import LSTMModel
from .markov_model import MarkovModel
from .random_model import RandomModel


def get_model(name: str, **kwargs) -> BaseModel:
    """
    按名字获取模型实例

    @param name 模型标识
    @param kwargs 透传给模型构造器（如 ensemble 需要 target_issue）
    @returns 模型实例
    """
    mapping = {
        "random": RandomModel,
        "frequency": FrequencyModel,
        "bayesian": BayesianModel,
        "markov": MarkovModel,
        "lstm": LSTMModel,
        "genetic": GeneticModel,
        "ensemble": EnsembleModel,
    }
    if name not in mapping:
        raise ValueError(f"未知模型: {name}")
    return mapping[name](**kwargs)


__all__ = [
    "BaseModel",
    "Ticket",
    "RandomModel",
    "FrequencyModel",
    "BayesianModel",
    "MarkovModel",
    "LSTMModel",
    "GeneticModel",
    "EnsembleModel",
    "get_model",
]
