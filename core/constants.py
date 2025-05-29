from discord import app_commands

SEASON_CHOICES = [
    app_commands.Choice(name="atom01", value="atom01"),
    app_commands.Choice(name="binary01", value="binary01"),
    app_commands.Choice(name="cream01", value="cream01"),
    app_commands.Choice(name="divine01", value="divine01"),
    app_commands.Choice(name="ever01", value="ever01"),
    app_commands.Choice(name="atom02", value="atom02"),
    app_commands.Choice(name="customs", value="gndsg01")
]

RARITY_MAPPING = {
    1: "Common",
    2: "Uncommon",
    3: "Rare",
    4: "Very Rare",
    5: "Super Rare",
    6: "Ultra Rare",
    7: "Uncommon"
}

MEMBER_PRIORITY = {
    "SeoYeon": 1, "Yeonajji": 1.1,
    "HyeRin": 2, "Aekkeangie":  2.1,
    "JiWoo": 3, "Rocketdan": 3.1,
    "ChaeYeon": 4, "Chaengbokdan": 4.1,
    "YooYeon": 5, "Yooenmi": 5.1,
    "SooMin": 6, "Daramdan": 6.1,
    "NaKyoung":7, "Nyangkidan": 7.1,
    "YuBin": 8, "Bambamdan": 8.1,
    "Kaede": 9, "Kaedan": 9.1,
    "DaHyun": 10, "Sodadan": 10.1,
    "Kotone": 11, "Coladan": 11.1,
    "YeonJi": 12, "Quackquackdan": 12.1,
    "Nien": 13, "Honeydan": 13.1,
    "SoHyun": 14, "Nabills": 14.1,
    "Xinyu": 15, "Shinandan": 15.1,
    "Mayu": 16, "Cutiedan": 16.1,
    "Lynn": 17, "Shamedan": 17.1,
    "JooBin": 18, "Jjumeokkongdan": 18.1,
    "HaYeon": 19, "Yukgakdan": 19.1,
    "ShiOn": 20, "Babondan": 20.1,
    "ChaeWon": 21, "Ddallangdan": 21.1,
    "Sullin": 22, "Snowflakes": 22.1,
    "SeoAh": 23, "Haessaldan": 23.1,
    "JiYeon": 24, "Danggeundan": 24.1,
}

CLASS_CHOICES = [
    app_commands.Choice(name="customs", value="Never"),
    app_commands.Choice(name="first", value="First"),
    app_commands.Choice(name="double", value="Double"),
    app_commands.Choice(name="special", value="Special"),
    app_commands.Choice(name="welcome", value="Welcome"),
    app_commands.Choice(name="zero", value="Zero"),
    app_commands.Choice(name="premier", value="Premier")
]

RARITY_CHOICES = [
    app_commands.Choice(name="Common", value=1),
    app_commands.Choice(name="Uncommon", value=2),
    app_commands.Choice(name="Rare", value=3),
    app_commands.Choice(name="Very Rare", value=4),
    app_commands.Choice(name="Super Rare", value=5),
    app_commands.Choice(name="Ultra Rare", value=6)
]

SORT_CHOICES = [
    app_commands.Choice(name="Member", value="member"),
    app_commands.Choice(name="Season", value="season"),
    app_commands.Choice(name="Class", value="class"),
    app_commands.Choice(name="Series", value="series"),
    app_commands.Choice(name="Rarity", value="rarity"),
    app_commands.Choice(name="Copies", value="copies"),
]

RARITY_COMO_REWARDS = {
    1: 10,
    2: 50,
    3: 150,
    4: 350,
    5: 750,
    6: 2000,
}

BANNER_CHOICES = [
    app_commands.Choice(name="atom01", value="Atom01"),
    app_commands.Choice(name="binary01", value="Binary01"),
    app_commands.Choice(name="cream01", value="Cream01"),
    app_commands.Choice(name="divine01", value="Divine01"),
    app_commands.Choice(name="ever01", value="Ever01"),
    app_commands.Choice(name="atom02", value="Atom02"),
    app_commands.Choice(name="rateup", value="rateup")
]

RARITY_STR_MAPPING = {
    1: "n ",
    2: "n ",
    3: " Rare ",
    4: " Very Rare ",
    5: " Super Rare ",
    6: "n Ultra Rare ",
    7: "n ",
}