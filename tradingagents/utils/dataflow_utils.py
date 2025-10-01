"""
数据流通用工具函数

从 tradingagents/dataflows/utils.py 迁移而来
"""
import os
import json
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Annotated

# 导入日志模块
from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')


SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    """
    保存 DataFrame 到 CSV 文件
    
    Args:
        data: 要保存的 DataFrame
        tag: 标签（用于日志）
        save_path: 保存路径，如果为 None 则不保存
    """
    if save_path:
        data.to_csv(save_path)
        logger.info(f"{tag} saved to {save_path}")


def get_current_date():
    """
    获取当前日期（YYYY-MM-DD 格式）
    
    Returns:
        str: 当前日期字符串
    """
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator):
    """
    类装饰器：为类的所有方法应用指定的装饰器
    
    Args:
        decorator: 要应用的装饰器函数
        
    Returns:
        function: 类装饰器函数
        
    Example:
        >>> @decorate_all_methods(my_decorator)
        >>> class MyClass:
        >>>     def method1(self):
        >>>         pass
    """
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date_input):
    """
    获取下一个工作日（跳过周末）
    
    Args:
        date_input: 日期对象或日期字符串（YYYY-MM-DD）
        
    Returns:
        datetime: 下一个工作日的日期对象
        
    Example:
        >>> get_next_weekday("2025-10-04")  # 周六
        datetime(2025, 10, 6)  # 返回周一
    """
    if not isinstance(date_input, datetime):
        date_input = datetime.strptime(date_input, "%Y-%m-%d")

    if date_input.weekday() >= 5:  # 周六(5)或周日(6)
        days_to_add = 7 - date_input.weekday()
        next_weekday = date_input + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date_input

