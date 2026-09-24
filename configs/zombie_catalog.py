"""Zombie type labels for PvZ 1.0.0.1051.

ID order follows ZombieType in the reconstructed ConstEnums.h:
https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h
"""

ZOMBIE_NAMES: tuple[str, ...] = (
    "普通僵尸", "旗帜僵尸", "路障僵尸", "撑杆跳僵尸",
    "铁桶僵尸", "读报僵尸", "铁门僵尸", "橄榄球僵尸",
    "舞王僵尸", "伴舞僵尸", "救生圈僵尸", "潜水僵尸",
    "冰车僵尸", "雪橇僵尸", "海豚骑士僵尸", "玩偶匣僵尸",
    "气球僵尸", "矿工僵尸", "跳跳僵尸", "雪人僵尸",
    "蹦极僵尸", "扶梯僵尸", "投石车僵尸", "巨人僵尸",
    "小鬼僵尸", "僵王博士", "豌豆射手僵尸", "坚果僵尸",
    "火爆辣椒僵尸", "机枪射手僵尸", "窝瓜僵尸", "高坚果僵尸",
    "红眼巨人僵尸", "自定义形象僵尸",
)


def zombie_name(type_code: object) -> str | None:
    if type(type_code) is int and 0 <= type_code < len(ZOMBIE_NAMES):
        return ZOMBIE_NAMES[type_code]
    return None
