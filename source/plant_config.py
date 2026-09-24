"""厂区参数加载：代码与参数分离。
优先级：环境变量 FAB1_CONFIG 指定的文件 > source/config/plant.json（本机真实参数，不入库）> source/config/plant.example.json（公开示例）。
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_DIR = os.path.join(HERE, "config")


def config_path():
    p = os.environ.get("FAB1_CONFIG")
    if p:
        return p
    real = os.path.join(CFG_DIR, "plant.json")
    return real if os.path.exists(real) else os.path.join(CFG_DIR, "plant.example.json")


def load():
    with open(config_path(), encoding="utf-8") as f:
        return json.load(f)
