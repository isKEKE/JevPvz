"""Static CoinType labels for PvZ 1.0.0.1051 dropped objects.

ID order follows the reconstructed ConstEnums.h:
https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h
The memory offset used to obtain the type ID still requires gameplay validation.
"""

ITEM_NAMES: tuple[str, ...] = (
    "无", "银币", "金币", "钻石", "阳光", "小阳光", "大阳光",
    "关卡种子包", "奖杯", "铲子", "植物图鉴", "车钥匙", "花瓶",
    "水壶", "玉米卷", "便条", "可使用种子包", "植物礼盒",
    "奖励钱袋", "奖励礼盒", "钻石袋奖励", "银向日葵奖杯",
    "金向日葵奖杯", "巧克力", "巧克力奖励", "小游戏礼盒",
    "解谜模式礼盒", "生存模式礼盒",
)


def item_name(type_code: object) -> str | None:
    if type(type_code) is int and 0 <= type_code < len(ITEM_NAMES):
        return ITEM_NAMES[type_code]
    return None
