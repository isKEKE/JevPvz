"""Static CoinType labels for PvZ 1.0.0.1051 dropped objects.

ID order follows the reconstructed ConstEnums.h:
https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h
The memory offset used to obtain the type ID still requires gameplay validation.
"""

ITEM_NAMES: tuple[str, ...] = (
    "none", "silver_coin", "gold_coin", "diamond", "sun", "small_sun", "large_sun",
    "level_seed_packet", "trophy", "shovel", "almanac", "car_key", "vase",
    "watering_can", "taco", "note", "usable_seed_packet", "plant_gift_box",
    "reward_money_bag", "reward_gift_box", "diamond_bag_reward", "silver_sunflower_trophy",
    "gold_sunflower_trophy", "chocolate", "chocolate_reward", "minigame_gift_box",
    "puzzle_gift_box", "survival_gift_box",
)

ITEM_LABELS_ZH: tuple[str, ...] = (
    "无", "银币", "金币", "钻石", "阳光", "小阳光", "大阳光", "关卡种子包", "奖杯", "铲子", "植物图鉴",
    "车钥匙", "花瓶", "水壶", "玉米卷", "便条", "可使用种子包", "植物礼盒", "奖励钱袋", "奖励礼盒",
    "钻石袋奖励", "银向日葵奖杯", "金向日葵奖杯", "巧克力", "巧克力奖励", "小游戏礼盒", "解谜模式礼盒", "生存模式礼盒",
)


def item_name(type_code: object) -> str | None:
    if type(type_code) is int and 0 <= type_code < len(ITEM_NAMES):
        return ITEM_NAMES[type_code]
    return None
