"""Zombie type names and mechanism descriptions for PvZ 1.0.0.1051.

ID order follows ZombieType in the reconstructed ConstEnums.h:
https://github.com/Patoke/re-plants-vs-zombies/blob/main/ConstEnums.h
Ability descriptions are concise English summaries of the in-game Almanac, referenced by the EA Readme:
https://akamai.cdn.ea.com/eadownloads/u/f/manuals/GAME-PVZ/en_US_readme.html
"""

from typing import NamedTuple


class ZombieInfo(NamedTuple):
    name: str
    description_en: str


ZOMBIES: tuple[ZombieInfo, ...] = (
    ZombieInfo("normal_zombie", "A basic zombie that walks toward the house and bites plants."),
    ZombieInfo("flag_zombie", "A flag-carrying zombie that leads a wave; otherwise it uses basic zombie behavior."),
    ZombieInfo("conehead_zombie", "A basic zombie whose traffic cone provides extra damage protection."),
    ZombieInfo("pole_vaulting_zombie", "Vaults over the first plant it reaches, then continues on foot."),
    ZombieInfo("buckethead_zombie", "A basic zombie protected by a durable metal bucket."),
    ZombieInfo("newspaper_zombie", "Uses a newspaper as a shield and rushes faster after it is destroyed."),
    ZombieInfo("screen_door_zombie", "Carries a screen door that blocks many projectiles; fume attacks pierce it."),
    ZombieInfo("football_zombie", "A fast, durable zombie wearing football equipment."),
    ZombieInfo("dancing_zombie", "Dances forward and summons backup dancers around itself."),
    ZombieInfo("backup_dancer", "A supporting dancer that moves with the Dancing Zombie and attacks plants."),
    ZombieInfo("zombie_with_life_preserver", "A pool zombie wearing a life preserver; use observed position and armor fields for its current threat."),
    ZombieInfo("snorkel_zombie", "Swims below the pool surface and rises to attack plants in its lane."),
    ZombieInfo("zomboni", "Drives across a row, crushing plants and leaving an icy path behind."),
    ZombieInfo("zombie_bobsled_team", "Travels as a bobsled group on an icy path."),
    ZombieInfo("dolphin_rider_zombie", "Uses a dolphin to leap over the first aquatic plant it reaches."),
    ZombieInfo("jack_in_the_box_zombie", "Carries an explosive box that can detonate as it walks."),
    ZombieInfo("balloon_zombie", "Floats over most ground defenses and can be attacked by anti-air plants or blown away."),
    ZombieInfo("digger_zombie", "Digs under the lawn, emerges near the house, and attacks plants from the rear."),
    ZombieInfo("pogo_zombie", "Bounces over plants with a pogo stick until its jump is stopped."),
    ZombieInfo("yeti_zombie", "A rare, durable zombie that may retreat if it is not defeated promptly."),
    ZombieInfo("bungee_zombie", "Drops from above to steal a plant; nearby Umbrella Leaves can block its attack."),
    ZombieInfo("ladder_zombie", "Carries a ladder to climb over a plant and leave a crossing for other zombies."),
    ZombieInfo("catapult_zombie", "Throws basketballs at plants from a distance while advancing slowly."),
    ZombieInfo("gargantuar", "A very durable giant that smashes plants and throws an Imp when badly damaged."),
    ZombieInfo("imp", "A small zombie that is often thrown behind defenses by a giant."),
    ZombieInfo("dr_zomboss", "A boss with large health and multiple attacks; use current phase and position rather than assuming one attack."),
    ZombieInfo("peashooter_zombie", "A challenge-mode zombie that fires peas toward plants."),
    ZombieInfo("wall_nut_zombie", "A challenge-mode zombie with a Wall-nut-like defensive body."),
    ZombieInfo("jalapeno_zombie", "A challenge-mode zombie whose attack can burn plants across its row."),
    ZombieInfo("gatling_pea_zombie", "A challenge-mode zombie that fires a rapid volley of peas toward plants."),
    ZombieInfo("squash_zombie", "A challenge-mode zombie that jumps onto a plant and crushes it."),
    ZombieInfo("tall_nut_zombie", "A challenge-mode zombie with a Tall-nut-like durable defensive body."),
    ZombieInfo("giga_gargantuar", "A stronger Gargantuar variant that smashes plants and throws an Imp when damaged."),
    ZombieInfo("custom_zombie", "Custom zombie type; no special ability is assumed beyond the current State observations."),
)

ZOMBIE_NAMES: tuple[str, ...] = tuple(zombie.name for zombie in ZOMBIES)

ZOMBIE_LABELS_ZH: tuple[str, ...] = (
    "普通僵尸", "旗帜僵尸", "路障僵尸", "撑杆跳僵尸", "铁桶僵尸", "读报僵尸", "铁门僵尸", "橄榄球僵尸",
    "舞王僵尸", "伴舞僵尸", "救生圈僵尸", "潜水僵尸", "冰车僵尸", "雪橇僵尸", "海豚骑士僵尸", "玩偶匣僵尸",
    "气球僵尸", "矿工僵尸", "跳跳僵尸", "雪人僵尸", "蹦极僵尸", "扶梯僵尸", "投石车僵尸", "巨人僵尸",
    "小鬼僵尸", "僵王博士", "豌豆射手僵尸", "坚果僵尸", "火爆辣椒僵尸", "机枪射手僵尸", "窝瓜僵尸", "高坚果僵尸",
    "红眼巨人僵尸", "自定义形象僵尸",
)


def zombie_name(type_code: object) -> str | None:
    if type(type_code) is int and 0 <= type_code < len(ZOMBIE_NAMES):
        return ZOMBIE_NAMES[type_code]
    return None


def zombie_info(type_code: object) -> ZombieInfo | None:
    if type(type_code) is int and 0 <= type_code < len(ZOMBIES):
        return ZOMBIES[type_code]
    return None


def zombie_label_zh(type_code: object) -> str | None:
    if type(type_code) is int and 0 <= type_code < len(ZOMBIE_LABELS_ZH):
        return ZOMBIE_LABELS_ZH[type_code]
    return None
