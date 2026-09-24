"""PvZ 1.0.0.1051 seed names and static sun costs.

These are catalog values, not values read from the running game process.
Source: https://github.com/ruslan831/PlantsVsZombies-decompilation/blob/master/Lawn/Plant.cpp
"""

from typing import NamedTuple


class PlantInfo(NamedTuple):
    name: str
    cost: int | None


PLANTS: tuple[PlantInfo, ...] = (
    PlantInfo("豌豆射手", 100), PlantInfo("向日葵", 50),
    PlantInfo("樱桃炸弹", 150), PlantInfo("坚果", 50),
    PlantInfo("土豆地雷", 25), PlantInfo("寒冰射手", 175),
    PlantInfo("大嘴花", 150), PlantInfo("双发射手", 200),
    PlantInfo("小喷菇", 0), PlantInfo("阳光菇", 25),
    PlantInfo("大喷菇", 75), PlantInfo("墓碑吞噬者", 75),
    PlantInfo("魅惑菇", 75), PlantInfo("胆小菇", 25),
    PlantInfo("寒冰菇", 75), PlantInfo("毁灭菇", 125),
    PlantInfo("睡莲", 25), PlantInfo("窝瓜", 50),
    PlantInfo("三线射手", 325), PlantInfo("缠绕海草", 25),
    PlantInfo("火爆辣椒", 125), PlantInfo("地刺", 100),
    PlantInfo("火炬树桩", 175), PlantInfo("高坚果", 125),
    PlantInfo("海蘑菇", 0), PlantInfo("路灯花", 25),
    PlantInfo("仙人掌", 125), PlantInfo("三叶草", 100),
    PlantInfo("裂荚射手", 125), PlantInfo("杨桃", 125),
    PlantInfo("南瓜头", 125), PlantInfo("磁力菇", 100),
    PlantInfo("卷心菜投手", 100), PlantInfo("花盆", 25),
    PlantInfo("玉米投手", 100), PlantInfo("咖啡豆", 75),
    PlantInfo("大蒜", 50), PlantInfo("叶子保护伞", 100),
    PlantInfo("金盏花", 50), PlantInfo("西瓜投手", 300),
    PlantInfo("机枪射手", 250), PlantInfo("双子向日葵", 150),
    PlantInfo("忧郁菇", 150), PlantInfo("香蒲", 225),
    PlantInfo("冰西瓜", 200), PlantInfo("吸金磁", 50),
    PlantInfo("地刺王", 125), PlantInfo("玉米加农炮", 500),
    PlantInfo("模仿者", None),
)


def plant_info(type_code: object) -> PlantInfo | None:
    if type(type_code) is int and 0 <= type_code < len(PLANTS):
        return PLANTS[type_code]
    return None
