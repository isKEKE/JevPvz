"""PvZ 1.0.0.1051 seed names and static sun costs.

These are catalog values, not values read from the running game process.
Source: https://github.com/ruslan831/PlantsVsZombies-decompilation/blob/master/Lawn/Plant.cpp
Ability descriptions are concise English summaries of the in-game Almanac, referenced by the EA Readme:
https://akamai.cdn.ea.com/eadownloads/u/f/manuals/GAME-PVZ/en_US_readme.html
"""

from typing import NamedTuple

# Closed English strategic-role set used by the strategy feature layer:
#   resource  — produces sun (or coins) for the economy
#   attacker  — deals damage
#   defender  — absorbs or blocks zombie damage
#   control   — slows, stuns, redirects, moves, or otherwise changes the board/enemy state
#   instant   — a one-shot effect that is consumed when it triggers
PLANT_ENGAGEMENTS = frozenset({"ranged", "melee", "none"})

PLANT_ROLES: tuple[str, ...] = ("resource", "attacker", "defender", "control", "instant")


class PlantInfo(NamedTuple):
    name: str
    cost: int | None
    description_en: str
    role: str
    engagement: str = "none"
    """How the plant reaches zombies: ``ranged`` (shoots or lobs down the lawn),
    ``melee`` (must be adjacent to, or walked over by, zombies) or ``none`` (never
    attacks: economy, defenders, utilities, and one-shot instants whose area is
    stated in ``description_en``). ``role == "resource"`` marks economy plants."""


PLANTS: tuple[PlantInfo, ...] = (
    PlantInfo("peashooter", 100, "Fires peas in a straight line at zombies.", "attacker", "ranged"),
    PlantInfo("sunflower", 50, "Produces sun periodically to fund more plants.", "resource", "none"),
    PlantInfo("cherry_bomb", 150, "Explodes over a 3-by-3 area and damages nearby zombies.", "instant", "none"),
    PlantInfo("wall_nut", 50, "Blocks zombies with a durable defensive shell.", "defender", "none"),
    PlantInfo("potato_mine", 25, "Arms after a delay, then explodes when a zombie steps on it.", "instant", "none"),
    PlantInfo("snow_pea", 175, "Fires peas that damage and slow the zombie they hit.", "attacker", "ranged"),
    PlantInfo("chomper", 150, "Swallows one nearby zombie, then pauses while digesting.", "attacker", "melee"),
    PlantInfo("repeater", 200, "Fires two peas in succession down its lane.", "attacker", "ranged"),
    PlantInfo("puff_shroom", 0, "A free night mushroom that fires short-range spores.", "attacker", "ranged"),
    PlantInfo("sun_shroom", 25, "A night mushroom that starts with small sun and later produces larger sun.", "resource", "none"),
    PlantInfo("fume_shroom", 75, "Fires a fume cloud that pierces screen-door armor.", "attacker", "ranged"),
    PlantInfo("grave_buster", 75, "Consumes a grave in its cell to remove the obstacle.", "instant", "none"),
    PlantInfo("hypno_shroom", 75, "Turns a zombie that eats it around to fight for you.", "control", "none"),
    PlantInfo("scaredy_shroom", 25, "Fires long-range spores but hides when zombies get close.", "attacker", "ranged"),
    PlantInfo("ice_shroom", 75, "Freezes zombies across the lawn for a short time.", "instant", "none"),
    PlantInfo("doom_shroom", 125, "Creates a powerful area explosion and leaves a crater.", "instant", "none"),
    PlantInfo("lily_pad", 25, "Provides a floating base for plants placed on water.", "control", "none"),
    PlantInfo("squash", 50, "Jumps onto a nearby zombie and crushes it.", "instant", "melee"),
    PlantInfo("threepeater", 325, "Fires peas down its lane and the lanes directly above and below.", "attacker", "ranged"),
    PlantInfo("tangle_kelp", 25, "Pulls one aquatic zombie underwater when it reaches the plant.", "instant", "melee"),
    PlantInfo("jalapeno", 125, "Burns every zombie in its row.", "instant", "none"),
    PlantInfo("spikeweed", 100, "Damages zombies that walk over it and pops vehicle tires.", "attacker", "melee"),
    PlantInfo("torchwood", 175, "Ignites peas that pass through it, increasing their damage.", "attacker", "none"),
    PlantInfo("tall_nut", 125, "A high, durable barrier that stops vaulting zombies.", "defender", "none"),
    PlantInfo("sea_shroom", 0, "A free aquatic night mushroom that fires short-range spores.", "attacker", "ranged"),
    PlantInfo("plantern", 25, "Illuminates nearby fog and reveals obscured parts of the lawn.", "control", "none"),
    PlantInfo("cactus", 125, "Fires spikes at ground zombies and raises them to hit balloon zombies.", "attacker", "ranged"),
    PlantInfo("blover", 100, "Blows away fog and removes balloon zombies from the lawn.", "instant", "none"),
    PlantInfo("split_pea", 125, "Fires peas forward and backward to cover both sides.", "attacker", "ranged"),
    PlantInfo("starfruit", 125, "Shoots stars in five directions around the plant.", "attacker", "ranged"),
    PlantInfo("pumpkin", 125, "Protects a plant inside its shell from zombie bites.", "defender", "none"),
    PlantInfo("magnet_shroom", 100, "Pulls metal equipment away from nearby zombies.", "control", "none"),
    PlantInfo("cabbage_pult", 100, "Lobs cabbages over obstacles at zombies in its lane.", "attacker", "ranged"),
    PlantInfo("flower_pot", 25, "Provides a planting base for plants on the roof.", "control", "none"),
    PlantInfo("kernel_pult", 100, "Lobs kernels and occasionally butter that briefly stuns a zombie.", "attacker", "ranged"),
    PlantInfo("coffee_bean", 75, "Wakes a sleeping mushroom so it can act during the day.", "instant", "none"),
    PlantInfo("garlic", 50, "Redirects a biting zombie into an adjacent lane.", "control", "none"),
    PlantInfo("umbrella_leaf", 100, "Protects nearby plants from bungee drops and catapult shots.", "defender", "none"),
    PlantInfo("marigold", 50, "Produces coins over time.", "resource", "none"),
    PlantInfo("melon_pult", 300, "Lobs melons that deal splash damage to nearby zombies.", "attacker", "ranged"),
    PlantInfo("gatling_pea", 250, "An upgrade for Repeater that fires four peas per volley.", "attacker", "ranged"),
    PlantInfo("twin_sunflower", 150, "An upgrade for Sunflower that produces twice as much sun.", "resource", "none"),
    PlantInfo("gloom_shroom", 150, "An upgrade for Fume-shroom that attacks nearby zombies in all directions.", "attacker", "melee"),
    PlantInfo("cattail", 225, "An aquatic plant that fires homing spikes at ground and air targets.", "attacker", "ranged"),
    PlantInfo("winter_melon", 200, "Lobs melons that splash damage and slow groups of zombies.", "attacker", "ranged"),
    PlantInfo("gold_magnet", 50, "An upgrade for Magnet-shroom that collects nearby coins and diamonds.", "resource", "none"),
    PlantInfo("spikerock", 125, "An upgrade for Spikeweed that damages zombies and withstands vehicle tires.", "attacker", "melee"),
    PlantInfo("cob_cannon", 500, "Combines two Kernel-pults to launch a powerful cob at a chosen area.", "attacker", "ranged"),
    PlantInfo("imitater", None, "Copies a selected plant and transforms into it after a short delay.", "instant", "none"),
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


def production_currency(type_name: str) -> str | None:
    if type_name in {"sunflower", "sun_shroom", "twin_sunflower"}: return "sun"
    if type_name == "marigold": return "coin"
    return None
