"""PvZ 1.0.0.1051 seed names and static sun costs.

These are catalog values, not values read from the running game process.
Source: https://github.com/ruslan831/PlantsVsZombies-decompilation/blob/master/Lawn/Plant.cpp
"""

from typing import NamedTuple


class PlantInfo(NamedTuple):
    name: str
    cost: int | None


PLANTS: tuple[PlantInfo, ...] = (
    PlantInfo("peashooter", 100), PlantInfo("sunflower", 50),
    PlantInfo("cherry_bomb", 150), PlantInfo("wall_nut", 50),
    PlantInfo("potato_mine", 25), PlantInfo("snow_pea", 175),
    PlantInfo("chomper", 150), PlantInfo("repeater", 200),
    PlantInfo("puff_shroom", 0), PlantInfo("sun_shroom", 25),
    PlantInfo("fume_shroom", 75), PlantInfo("grave_buster", 75),
    PlantInfo("hypno_shroom", 75), PlantInfo("scaredy_shroom", 25),
    PlantInfo("ice_shroom", 75), PlantInfo("doom_shroom", 125),
    PlantInfo("lily_pad", 25), PlantInfo("squash", 50),
    PlantInfo("threepeater", 325), PlantInfo("tangle_kelp", 25),
    PlantInfo("jalapeno", 125), PlantInfo("spikeweed", 100),
    PlantInfo("torchwood", 175), PlantInfo("tall_nut", 125),
    PlantInfo("sea_shroom", 0), PlantInfo("plantern", 25),
    PlantInfo("cactus", 125), PlantInfo("blover", 100),
    PlantInfo("split_pea", 125), PlantInfo("starfruit", 125),
    PlantInfo("pumpkin", 125), PlantInfo("magnet_shroom", 100),
    PlantInfo("cabbage_pult", 100), PlantInfo("flower_pot", 25),
    PlantInfo("kernel_pult", 100), PlantInfo("coffee_bean", 75),
    PlantInfo("garlic", 50), PlantInfo("umbrella_leaf", 100),
    PlantInfo("marigold", 50), PlantInfo("melon_pult", 300),
    PlantInfo("gatling_pea", 250), PlantInfo("twin_sunflower", 150),
    PlantInfo("gloom_shroom", 150), PlantInfo("cattail", 225),
    PlantInfo("winter_melon", 200), PlantInfo("gold_magnet", 50),
    PlantInfo("spikerock", 125), PlantInfo("cob_cannon", 500),
    PlantInfo("imitater", None),
)

PLANT_LABELS_ZH: tuple[str, ...] = (
    "豌豆射手", "向日葵", "樱桃炸弹", "坚果", "土豆地雷", "寒冰射手", "大嘴花", "双发射手",
    "小喷菇", "阳光菇", "大喷菇", "墓碑吞噬者", "魅惑菇", "胆小菇", "寒冰菇", "毁灭菇",
    "睡莲", "窝瓜", "三线射手", "缠绕海草", "火爆辣椒", "地刺", "火炬树桩", "高坚果",
    "海蘑菇", "路灯花", "仙人掌", "三叶草", "裂荚射手", "杨桃", "南瓜头", "磁力菇",
    "卷心菜投手", "花盆", "玉米投手", "咖啡豆", "大蒜", "叶子保护伞", "金盏花", "西瓜投手",
    "机枪射手", "双子向日葵", "忧郁菇", "香蒲", "冰西瓜", "吸金磁", "地刺王", "玉米加农炮", "模仿者",
)


def plant_info(type_code: object) -> PlantInfo | None:
    if type(type_code) is int and 0 <= type_code < len(PLANTS):
        return PLANTS[type_code]
    return None
