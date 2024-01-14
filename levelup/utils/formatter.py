import logging
import math
import random
from datetime import datetime, timedelta
from io import StringIO
from typing import List, Tuple, Union

import discord
from aiocache import cached
from aiohttp import ClientSession
from redbot.core import commands
from redbot.core.i18n import Translator
from redbot.core.utils.chat_formatting import box, humanize_number

DPY2 = True if discord.__version__ > "1.7.3" else False
_ = Translator("LevelUp", __file__)
log = logging.getLogger("red.vrt.levelup.formatter")


# Get a level that would be achieved from the amount of XP
def get_level(xp: int, base: int, exp: int) -> int:
    for level, xp_threshold in LEVELS.items():
        if xp >= xp_threshold:
            current_level = level

    return int(current_level)


# Get how much XP is needed to reach a level
def get_xp(level: int) -> int:
    return LEVELS[str(level)]


# Estimate how much time it would take to reach a certain level based on current algorithm
def time_to_level(
    level: int,
    base: int,
    exp: Union[int, float],
    cooldown: int,
    xp_range: list,
) -> int:
    xp_needed = get_xp(level)
    xp_obtained = 0
    time_to_reach_level = 0  # Seconds
    while True:
        xp = random.choice(range(xp_range[0], xp_range[1] + 1))
        xp_obtained += xp

        if random.random() < 0.5:
            # Wait up to an hour after cooldown for a little more realism
            wait = cooldown + random.randint(30, 3600)
        else:
            wait = cooldown + random.randint(5, 300)

        time_to_reach_level += wait
        if xp_obtained >= xp_needed:
            return time_to_reach_level


# Convert a hex color to an RGB tuple
def hex_to_rgb(color: str) -> tuple:
    if color.isdigit():
        rgb = int_to_rgb(int(color))
    else:
        color = color.strip("#")
        rgb = tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))
    return rgb


def get_level_color(member: discord.Member) -> Tuple[int, int, int]:
    c = member.colour
    if c.r is not None:
        colours = (c.r, c.g, c.b)
    else:
        colours = (255, 255, 255)
    return colours


def int_to_rgb(color: int) -> tuple:
    r = color & 255
    g = (color >> 8) & 255
    b = (color >> 16) & 255
    rgb = (r, g, b)
    return rgb


def get_bar(progress, total, perc=None, width: int = 20) -> str:
    fill = "▰"
    space = "▱"
    if perc is not None:
        ratio = perc / 100
    else:
        ratio = progress / total
    bar = fill * round(ratio * width) + space * round(width - (ratio * width))
    return f"{bar} {round(100 * ratio, 1)}%"


# Format time from total seconds and format into readable string
def time_formatter(time_in_seconds) -> str:
    # Some time differences get sent as a float so just handle it the dumb way
    time_in_seconds = int(time_in_seconds)
    minutes, seconds = divmod(time_in_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    if not any([seconds, minutes, hours, days, years]):
        tstring = _("None")
    elif not any([minutes, hours, days, years]):
        if seconds == 1:
            tstring = str(seconds) + _(" second")
        else:
            tstring = str(seconds) + _(" seconds")
    elif not any([hours, days, years]):
        if minutes == 1:
            tstring = str(minutes) + _(" minute")
        else:
            tstring = str(minutes) + _(" minutes")
    elif hours and not days and not years:
        tstring = f"{hours}h {minutes}m"
    elif days and not years:
        tstring = f"{days}d {hours}h {minutes}m"
    else:
        tstring = f"{years}y {days}d {hours}h {minutes}m"
    return tstring


def get_twemoji(emoji: str):
    # Thanks Fixator!
    emoji_unicode = []
    for char in emoji:
        char = hex(ord(char))[2:]
        emoji_unicode.append(char)
    if "200d" not in emoji_unicode:
        emoji_unicode = list(filter(lambda c: c != "fe0f", emoji_unicode))
    emoji_unicode = "-".join(emoji_unicode)
    return f"https://twemoji.maxcdn.com/v/latest/72x72/{emoji_unicode}.png"


def get_next_reset(weekday: int, hour: int):
    now = datetime.utcnow()
    reset = now + timedelta((weekday - now.weekday()) % 7)
    return int(reset.replace(hour=hour, minute=0, second=0).timestamp())


def get_attachments(ctx) -> List[discord.Attachment]:
    """Get all attachments from context"""
    content = []
    if ctx.message.attachments:
        atchmts = [a for a in ctx.message.attachments]
        content.extend(atchmts)
    if hasattr(ctx.message, "reference"):
        try:
            atchmts = [a for a in ctx.message.reference.resolved.attachments]
            content.extend(atchmts)
        except AttributeError:
            pass
    return content


def get_leaderboard(
    ctx: commands.Context,
    settings: dict,
    stat: str,
    lbtype: str,
    is_global: bool,
) -> Union[List[discord.Embed], str]:
    if lbtype == "weekly":
        lb = settings["weekly"]["users"]
        title = _("Global Weekly ") if is_global else _("Weekly ")
    else:
        lb = settings["users"]
        title = _("Global LevelUp ") if is_global else _("LevelUp ")

        if "xp" in stat.lower():
            lb = {uid: data.copy() for uid, data in settings["users"].items()}
            if prestige_req := settings.get("prestige"):
                # If this isnt pulled its global lb
                for uid, data in lb.items():
                    if prestige := data["prestige"]:
                        data["xp"] += prestige * get_xp(prestige_req)

    if "v" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["voice"], reverse=True)
        title += _("Voice Leaderboard")
        key = "voice"
        col = "🎙️"
        statname = _("Voicetime")
        total = time_formatter(sum(v["voice"] for v in lb.values()))
    elif "m" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["messages"], reverse=True)
        title += _("Message Leaderboard")
        key = "messages"
        col = "💬"
        statname = _("Messages")
        total = humanize_number(round(sum(v["messages"] for v in lb.values())))
    elif "s" in stat.lower():
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["stars"], reverse=True)
        title += _("Star Leaderboard")
        key = "stars"
        col = "⭐"
        statname = _("Stars")
        total = humanize_number(round(sum(v["stars"] for v in lb.values())))
    else:  # Exp
        sorted_users = sorted(lb.items(), key=lambda x: x[1]["xp"], reverse=True)
        title += _("Exp Leaderboard")
        key = "xp"
        col = "💡"
        statname = _("Exp")
        total = humanize_number(round(sum(v["xp"] for v in lb.values())))

    if lbtype == "weekly":
        w = settings["weekly"]
        desc = _("Total ") + f"{statname}: `{total}`{col}\n"
        if last_reset := w.get("last_reset"):
            # If not global
            desc += _("Last Reset: ") + f"<t:{last_reset}:d>\n"
            if w["autoreset"]:
                tl = get_next_reset(w["reset_day"], w["reset_hour"])
                desc += _("Next Reset: ") + f"<t:{tl}:d> (<t:{tl}:R>)\n"
    else:
        desc = _("Total") + f" {statname}: `{total}`{col}\n"

    for i in sorted_users.copy():
        if not i[1][key]:
            sorted_users.remove(i)

    if not sorted_users:
        if lbtype == "weekly":
            txt = (
                _("There is no data for the weekly ")
                + statname.lower()
                + _(" leaderboard yet")
            )
        else:
            txt = (
                _("There is no data for the ")
                + statname.lower()
                + _(" leaderboard yet")
            )
        return txt

    you = ""
    for i in sorted_users:
        if i[0] == str(ctx.author.id):
            you = _("You: ") + f"{sorted_users.index(i) + 1}/{len(sorted_users)}\n"

    pages = math.ceil(len(sorted_users) / 10)
    start = 0
    stop = 10
    embeds = []
    for p in range(pages):
        if stop > len(sorted_users):
            stop = len(sorted_users)

        buf = StringIO()
        for i in range(start, stop, 1):
            uid = sorted_users[i][0]
            user_obj = ctx.guild.get_member(int(uid)) or ctx.bot.get_user(int(uid))
            user = user_obj.name if user_obj else uid
            data = sorted_users[i][1]

            place = i + 1
            if key == "voice":
                stat = time_formatter(data[key])
            else:
                v = data[key]
                if v > 999999999:
                    stat = f"{round(v / 1000000000, 1)}B"
                elif v > 999999:
                    stat = f"{round(v / 1000000, 1)}M"
                elif v > 9999:
                    stat = f"{round(v / 1000, 1)}K"
                else:
                    stat = str(round(v))

                if key == "xp" and lbtype != "weekly":
                    if lvl := data.get("level"):
                        stat += f" 🎖{lvl}"

            buf.write(f"{place}. {user} ({stat})\n")

        embed = discord.Embed(
            title=title,
            description=desc + box(buf.getvalue(), lang="python"),
            color=discord.Color.random(),
        )
        if DPY2:
            icon = ctx.guild.icon
        else:
            icon = ctx.guild.icon_url

        if you:
            embed.set_footer(
                text=_("Pages ") + f"{p + 1}/{pages} | {you}", icon_url=icon
            )
        else:
            embed.set_footer(text=_("Pages ") + f"{p + 1}/{pages}", icon_url=icon)

        embeds.append(embed)
        start += 10
        stop += 10
    return embeds


@cached(ttl=3600)
async def get_content_from_url(url: str):
    try:
        async with ClientSession() as session:
            async with session.get(url) as resp:
                file = await resp.content.read()
                return file
    except Exception as e:
        log.error(f"Could not get file content from url: {e}", exc_info=True)
        return None


async def get_user_position(conf: dict, user_id: str) -> dict:
    base = conf["base"]
    exp = conf["exp"]
    prestige_req = conf["prestige"]
    leaderboard = {}
    total_xp = 0
    user_xp = 0
    for user, data in conf["users"].items():
        xp = int(data["xp"])
        prestige = int(data["prestige"])
        if prestige:
            add_xp = get_xp(prestige_req)
            xp = int(xp + (prestige * add_xp))
        leaderboard[user] = xp
        total_xp += xp
        if user == user_id:
            user_xp = xp
    sorted_users = sorted(leaderboard.items(), key=lambda x: x[1], reverse=True)
    for i in sorted_users:
        if i[0] == user_id:
            if total_xp:
                percent = round((user_xp / total_xp) * 100, 2)
            else:
                percent = 100
            pos = sorted_users.index(i) + 1
            pos_data = {"p": pos, "pr": percent}
            return pos_data


LEVELS = {
    "0": 0,
    "1": 75,
    "2": 250,
    "3": 525,
    "4": 900,
    "5": 1375,
    "6": 1950,
    "7": 2625,
    "8": 3400,
    "9": 4275,
    "10": 5250,
    "11": 6325,
    "12": 7500,
    "13": 8775,
    "14": 10150,
    "15": 11625,
    "16": 13200,
    "17": 14875,
    "18": 16650,
    "19": 18525,
    "20": 20500,
    "21": 22575,
    "22": 24750,
    "23": 27025,
    "24": 29400,
    "25": 31875,
    "26": 34450,
    "27": 37125,
    "28": 39900,
    "29": 42775,
    "30": 45750,
    "31": 48825,
    "32": 52000,
    "33": 55275,
    "34": 58650,
    "35": 62125,
    "36": 65700,
    "37": 69375,
    "38": 73150,
    "39": 77025,
    "40": 81000,
    "41": 85075,
    "42": 89250,
    "43": 93525,
    "44": 97900,
    "45": 102375,
    "46": 106950,
    "47": 111625,
    "48": 116400,
    "49": 121275,
    "50": 126250,
    "51": 131325,
    "52": 136500,
    "53": 141775,
    "54": 147150,
    "55": 152625,
    "56": 158200,
    "57": 163875,
    "58": 169650,
    "59": 175525,
    "60": 181500,
    "61": 187575,
    "62": 193750,
    "63": 200025,
    "64": 206400,
    "65": 212875,
    "66": 219450,
    "67": 226125,
    "68": 232900,
    "69": 239775,
    "70": 246750,
    "71": 253825,
    "72": 261000,
    "73": 268275,
    "74": 275650,
    "75": 283125,
    "76": 290700,
    "77": 298375,
    "78": 306150,
    "79": 314025,
    "80": 322000,
    "81": 330075,
    "82": 338250,
    "83": 346525,
    "84": 354900,
    "85": 363375,
    "86": 371950,
    "87": 380625,
    "88": 389400,
    "89": 398275,
    "90": 407250,
    "91": 416325,
    "92": 425500,
    "93": 434775,
    "94": 444150,
    "95": 453625,
    "96": 463200,
    "97": 472875,
    "98": 482650,
    "99": 492525,
    "100": 502500,
    "101": 512575,
    "102": 522750,
    "103": 533025,
    "104": 543400,
    "105": 553875,
    "106": 564450,
    "107": 575125,
    "108": 585900,
    "109": 596775,
    "110": 607750,
    "111": 618825,
    "112": 630000,
    "113": 641275,
    "114": 652650,
    "115": 664125,
    "116": 675700,
    "117": 687375,
    "118": 699150,
    "119": 711025,
    "120": 723000,
    "121": 735075,
    "122": 747250,
    "123": 759525,
    "124": 771900,
    "125": 784375,
    "126": 796950,
    "127": 809625,
    "128": 822400,
    "129": 835275,
    "130": 848250,
    "131": 861325,
    "132": 874500,
    "133": 887775,
    "134": 901150,
    "135": 914625,
    "136": 928200,
    "137": 941875,
    "138": 955650,
    "139": 969525,
    "140": 983500,
    "141": 997575,
    "142": 1011750,
    "143": 1026025,
    "144": 1040400,
    "145": 1054875,
    "146": 1069450,
    "147": 1084125,
    "148": 1098900,
    "149": 1113775,
    "150": 1128750,
    "151": 1143825,
    "152": 1159000,
    "153": 1174275,
    "154": 1189650,
    "155": 1205125,
    "156": 1220700,
    "157": 1236375,
    "158": 1252150,
    "159": 1268025,
    "160": 1284000,
    "161": 1300075,
    "162": 1316250,
    "163": 1332525,
    "164": 1348900,
    "165": 1365375,
    "166": 1381950,
    "167": 1398625,
    "168": 1415400,
    "169": 1432275,
    "170": 1449250,
    "171": 1466325,
    "172": 1483500,
    "173": 1500775,
    "174": 1518150,
    "175": 1535625,
    "176": 1553200,
    "177": 1570875,
    "178": 1588650,
    "179": 1606525,
    "180": 1624500,
    "181": 1642575,
    "182": 1660750,
    "183": 1679025,
    "184": 1697400,
    "185": 1715875,
    "186": 1734450,
    "187": 1753125,
    "188": 1771900,
    "189": 1790775,
    "190": 1809750,
    "191": 1828825,
    "192": 1848000,
    "193": 1867275,
    "194": 1886650,
    "195": 1906125,
    "196": 1925700,
    "197": 1945375,
    "198": 1965150,
    "199": 1985025,
    "200": 2005000,
    "201": 2025075,
    "202": 2045250,
    "203": 2065525,
    "204": 2085900,
    "205": 2106375,
    "206": 2126950,
    "207": 2147625,
    "208": 2168400,
    "209": 2189275,
    "210": 2210250,
    "211": 2231325,
    "212": 2252500,
    "213": 2273775,
    "214": 2295150,
    "215": 2316625,
    "216": 2338200,
    "217": 2359875,
    "218": 2381650,
    "219": 2403525,
    "220": 2425500,
    "221": 2447575,
    "222": 2469750,
    "223": 2492025,
    "224": 2514400,
    "225": 2536875,
    "226": 2559450,
    "227": 2582125,
    "228": 2604900,
    "229": 2627775,
    "230": 2650750,
    "231": 2673825,
    "232": 2697000,
    "233": 2720275,
    "234": 2743650,
    "235": 2767125,
    "236": 2790700,
    "237": 2814375,
    "238": 2838150,
    "239": 2862025,
    "240": 2886000,
    "241": 2910075,
    "242": 2934250,
    "243": 2958525,
    "244": 2982900,
    "245": 3007375,
    "246": 3031950,
    "247": 3056625,
    "248": 3081400,
    "249": 3106275,
    "250": 3131250,
    "251": 3156325,
    "252": 3181500,
    "253": 3206775,
    "254": 3232150,
    "255": 3257625,
    "256": 3283200,
    "257": 3308875,
    "258": 3334650,
    "259": 3360525,
    "260": 3386500,
    "261": 3412575,
    "262": 3438750,
    "263": 3465025,
    "264": 3491400,
    "265": 3517875,
    "266": 3544450,
    "267": 3571125,
    "268": 3597900,
    "269": 3624775,
    "270": 3651750,
    "271": 3678825,
    "272": 3706000,
    "273": 3733275,
    "274": 3760650,
    "275": 3788125,
    "276": 3815700,
    "277": 3843375,
    "278": 3871150,
    "279": 3899025,
    "280": 3927000,
    "281": 3955075,
    "282": 3983250,
    "283": 4011525,
    "284": 4039900,
    "285": 4068375,
    "286": 4096950,
    "287": 4125625,
    "288": 4154400,
    "289": 4183275,
    "290": 4212250,
    "291": 4241325,
    "292": 4270500,
    "293": 4299775,
    "294": 4329150,
    "295": 4358625,
    "296": 4388200,
    "297": 4417875,
    "298": 4447650,
    "299": 4477525,
    "300": 4507500,
    "301": 4537575,
    "302": 4567750,
    "303": 4598025,
    "304": 4628400,
    "305": 4658875,
    "306": 4689450,
    "307": 4720125,
    "308": 4750900,
    "309": 4781775,
    "310": 4812750,
    "311": 4843825,
    "312": 4875000,
    "313": 4906275,
    "314": 4937650,
    "315": 4969125,
    "316": 5000700,
    "317": 5032375,
    "318": 5064150,
    "319": 5096025,
    "320": 5128000,
    "321": 5160075,
    "322": 5192250,
    "323": 5224525,
    "324": 5256900,
    "325": 5289375,
    "326": 5321950,
    "327": 5354625,
    "328": 5387400,
    "329": 5420275,
    "330": 5453250,
    "331": 5486325,
    "332": 5519500,
    "333": 5552775,
    "334": 5586150,
    "335": 5619625,
    "336": 5653200,
    "337": 5686875,
    "338": 5720650,
    "339": 5754525,
    "340": 5788500,
    "341": 5822575,
    "342": 5856750,
    "343": 5891025,
    "344": 5925400,
    "345": 5959875,
    "346": 5994450,
    "347": 6029125,
    "348": 6063900,
    "349": 6098775,
    "350": 6133750,
    "351": 6168825,
    "352": 6204000,
    "353": 6239275,
    "354": 6274650,
    "355": 6310125,
    "356": 6345700,
    "357": 6381375,
    "358": 6417150,
    "359": 6453025,
    "360": 6489000,
    "361": 6525075,
    "362": 6561250,
    "363": 6597525,
    "364": 6633900,
    "365": 6670375,
    "366": 6706950,
    "367": 6743625,
    "368": 6780400,
    "369": 6817275,
    "370": 6854250,
    "371": 6891325,
    "372": 6928500,
    "373": 6965775,
    "374": 7003150,
    "375": 7040625,
    "376": 7078200,
    "377": 7115875,
    "378": 7153650,
    "379": 7191525,
    "380": 7229500,
    "381": 7267575,
    "382": 7305750,
    "383": 7344025,
    "384": 7382400,
    "385": 7420875,
    "386": 7459450,
    "387": 7498125,
    "388": 7536900,
    "389": 7575775,
    "390": 7614750,
    "391": 7653825,
    "392": 7693000,
    "393": 7732275,
    "394": 7771650,
    "395": 7811125,
    "396": 7850700,
    "397": 7890375,
    "398": 7930150,
    "399": 7970025,
    "400": 8010000,
    "401": 8050075,
    "402": 8090250,
    "403": 8130525,
    "404": 8170900,
    "405": 8211375,
    "406": 8251950,
    "407": 8292625,
    "408": 8333400,
    "409": 8374275,
    "410": 8415250,
    "411": 8456325,
    "412": 8497500,
    "413": 8538775,
    "414": 8580150,
    "415": 8621625,
    "416": 8663200,
    "417": 8704875,
    "418": 8746650,
    "419": 8788525,
    "420": 8830500,
    "421": 8872575,
    "422": 8914750,
    "423": 8957025,
    "424": 8999400,
    "425": 9041875,
    "426": 9084450,
    "427": 9127125,
    "428": 9169900,
    "429": 9212775,
    "430": 9255750,
    "431": 9298825,
    "432": 9342000,
    "433": 9385275,
    "434": 9428650,
    "435": 9472125,
    "436": 9515700,
    "437": 9559375,
    "438": 9603150,
    "439": 9647025,
    "440": 9691000,
    "441": 9735075,
    "442": 9779250,
    "443": 9823525,
    "444": 9867900,
    "445": 9912375,
    "446": 9956950,
    "447": 10001625,
    "448": 10046400,
    "449": 10091275,
    "450": 10136250,
    "451": 10181325,
    "452": 10226500,
    "453": 10271775,
    "454": 10317150,
    "455": 10362625,
    "456": 10408200,
    "457": 10453875,
    "458": 10499650,
    "459": 10545525,
    "460": 10591500,
    "461": 10637575,
    "462": 10683750,
    "463": 10730025,
    "464": 10776400,
    "465": 10822875,
    "466": 10869450,
    "467": 10916125,
    "468": 10962900,
    "469": 11009775,
    "470": 11056750,
    "471": 11103825,
    "472": 11151000,
    "473": 11198275,
    "474": 11245650,
    "475": 11293125,
    "476": 11340700,
    "477": 11388375,
    "478": 11436150,
    "479": 11484025,
    "480": 11532000,
    "481": 11580075,
    "482": 11628250,
    "483": 11676525,
    "484": 11724900,
    "485": 11773375,
    "486": 11821950,
    "487": 11870625,
    "488": 11919400,
    "489": 11968275,
    "490": 12017250,
    "491": 12066325,
    "492": 12115500,
    "493": 12164775,
    "494": 12214150,
    "495": 12263625,
    "496": 12313200,
    "497": 12362875,
    "498": 12412650,
    "499": 12462525,
    "500": 12512500,
    "501": 12562575,
    "502": 12612750,
    "503": 12663025,
    "504": 12713400,
    "505": 12763875,
    "506": 12814450,
    "507": 12865125,
    "508": 12915900,
    "509": 12966775,
    "510": 13017750,
    "511": 13068825,
    "512": 13120000,
    "513": 13171275,
    "514": 13222650,
    "515": 13274125,
    "516": 13325700,
    "517": 13377375,
    "518": 13429150,
    "519": 13481025,
    "520": 13533000,
    "521": 13585075,
    "522": 13637250,
    "523": 13689525,
    "524": 13741900,
    "525": 13794375,
    "526": 13846950,
    "527": 13899625,
    "528": 13952400,
    "529": 14005275,
    "530": 14058250,
    "531": 14111325,
    "532": 14164500,
    "533": 14217775,
    "534": 14271150,
    "535": 14324625,
    "536": 14378200,
    "537": 14431875,
    "538": 14485650,
    "539": 14539525,
    "540": 14593500,
    "541": 14647575,
    "542": 14701750,
    "543": 14756025,
    "544": 14810400,
    "545": 14864875,
    "546": 14919450,
    "547": 14974125,
    "548": 15028900,
    "549": 15083775,
    "550": 15138750,
    "551": 15193825,
    "552": 15249000,
    "553": 15304275,
    "554": 15359650,
    "555": 15415125,
    "556": 15470700,
    "557": 15526375,
    "558": 15582150,
    "559": 15638025,
    "560": 15694000,
    "561": 15750075,
    "562": 15806250,
    "563": 15862525,
    "564": 15918900,
    "565": 15975375,
    "566": 16031950,
    "567": 16088625,
    "568": 16145400,
    "569": 16202275,
    "570": 16259250,
    "571": 16316325,
    "572": 16373500,
    "573": 16430775,
    "574": 16488150,
    "575": 16545625,
    "576": 16603200,
    "577": 16660875,
    "578": 16718650,
    "579": 16776525,
    "580": 16834500,
    "581": 16892575,
    "582": 16950750,
    "583": 17009025,
    "584": 17067400,
    "585": 17125875,
    "586": 17184450,
    "587": 17243125,
    "588": 17301900,
    "589": 17360775,
    "590": 17419750,
    "591": 17478825,
    "592": 17538000,
    "593": 17597275,
    "594": 17656650,
    "595": 17716125,
    "596": 17775700,
    "597": 17835375,
    "598": 17895150,
    "599": 17955025,
    "600": 18015000,
    "601": 18075075,
    "602": 18135250,
    "603": 18195525,
    "604": 18255900,
    "605": 18316375,
    "606": 18376950,
    "607": 18437625,
    "608": 18498400,
    "609": 18559275,
    "610": 18620250,
    "611": 18681325,
    "612": 18742500,
    "613": 18803775,
    "614": 18865150,
    "615": 18926625,
    "616": 18988200,
    "617": 19049875,
    "618": 19111650,
    "619": 19173525,
    "620": 19235500,
    "621": 19297575,
    "622": 19359750,
    "623": 19422025,
    "624": 19484400,
    "625": 19546875,
    "626": 19609450,
    "627": 19672125,
    "628": 19734900,
    "629": 19797775,
    "630": 19860750,
    "631": 19923825,
    "632": 19987000,
    "633": 20050275,
    "634": 20113650,
    "635": 20177125,
    "636": 20240700,
    "637": 20304375,
    "638": 20368150,
    "639": 20432025,
    "640": 20496000,
    "641": 20560075,
    "642": 20624250,
    "643": 20688525,
    "644": 20752900,
    "645": 20817375,
    "646": 20881950,
    "647": 20946625,
    "648": 21011400,
    "649": 21076275,
    "650": 21141250,
    "651": 21206325,
    "652": 21271500,
    "653": 21336775,
    "654": 21402150,
    "655": 21467625,
    "656": 21533200,
    "657": 21598875,
    "658": 21664650,
    "659": 21730525,
    "660": 21796500,
    "661": 21862575,
    "662": 21928750,
    "663": 21995025,
    "664": 22061400,
    "665": 22127875,
    "666": 22194450,
    "667": 22261125,
    "668": 22327900,
    "669": 22394775,
    "670": 22461750,
    "671": 22528825,
    "672": 22596000,
    "673": 22663275,
    "674": 22730650,
    "675": 22798125,
    "676": 22865700,
    "677": 22933375,
    "678": 23001150,
    "679": 23069025,
    "680": 23137000,
    "681": 23205075,
    "682": 23273250,
    "683": 23341525,
    "684": 23409900,
    "685": 23478375,
    "686": 23546950,
    "687": 23615625,
    "688": 23684400,
    "689": 23753275,
    "690": 23822250,
    "691": 23891325,
    "692": 23960500,
    "693": 24029775,
    "694": 24099150,
    "695": 24168625,
    "696": 24238200,
    "697": 24307875,
    "698": 24377650,
    "699": 24447525,
    "700": 24517500,
    "701": 24587575,
    "702": 24657750,
    "703": 24728025,
    "704": 24798400,
    "705": 24868875,
    "706": 24939450,
    "707": 25010125,
    "708": 25080900,
    "709": 25151775,
    "710": 25222750,
    "711": 25293825,
    "712": 25365000,
    "713": 25436275,
    "714": 25507650,
    "715": 25579125,
    "716": 25650700,
    "717": 25722375,
    "718": 25794150,
    "719": 25866025,
    "720": 25938000,
    "721": 26010075,
    "722": 26082250,
    "723": 26154525,
    "724": 26226900,
    "725": 26299375,
    "726": 26371950,
    "727": 26444625,
    "728": 26517400,
    "729": 26590275,
    "730": 26663250,
    "731": 26736325,
    "732": 26809500,
    "733": 26882775,
    "734": 26956150,
    "735": 27029625,
    "736": 27103200,
    "737": 27176875,
    "738": 27250650,
    "739": 27324525,
    "740": 27398500,
    "741": 27472575,
    "742": 27546750,
    "743": 27621025,
    "744": 27695400,
    "745": 27769875,
    "746": 27844450,
    "747": 27919125,
    "748": 27993900,
    "749": 28068775,
    "750": 28143750,
    "751": 28218825,
    "752": 28294000,
    "753": 28369275,
    "754": 28444650,
    "755": 28520125,
    "756": 28595700,
    "757": 28671375,
    "758": 28747150,
    "759": 28823025,
    "760": 28899000,
    "761": 28975075,
    "762": 29051250,
    "763": 29127525,
    "764": 29203900,
    "765": 29280375,
    "766": 29356950,
    "767": 29433625,
    "768": 29510400,
    "769": 29587275,
    "770": 29664250,
    "771": 29741325,
    "772": 29818500,
    "773": 29895775,
    "774": 29973150,
    "775": 30050625,
    "776": 30128200,
    "777": 30205875,
    "778": 30283650,
    "779": 30361525,
    "780": 30439500,
    "781": 30517575,
    "782": 30595750,
    "783": 30674025,
    "784": 30752400,
    "785": 30830875,
    "786": 30909450,
    "787": 30988125,
    "788": 31066900,
    "789": 31145775,
    "790": 31224750,
    "791": 31303825,
    "792": 31383000,
    "793": 31462275,
    "794": 31541650,
    "795": 31621125,
    "796": 31700700,
    "797": 31780375,
    "798": 31860150,
    "799": 31940025,
    "800": 32020000,
    "801": 32100075,
    "802": 32180250,
    "803": 32260525,
    "804": 32340900,
    "805": 32421375,
    "806": 32501950,
    "807": 32582625,
    "808": 32663400,
    "809": 32744275,
    "810": 32825250,
    "811": 32906325,
    "812": 32987500,
    "813": 33068775,
    "814": 33150150,
    "815": 33231625,
    "816": 33313200,
    "817": 33394875,
    "818": 33476650,
    "819": 33558525,
    "820": 33640500,
    "821": 33722575,
    "822": 33804750,
    "823": 33887025,
    "824": 33969400,
    "825": 34051875,
    "826": 34134450,
    "827": 34217125,
    "828": 34299900,
    "829": 34382775,
    "830": 34465750,
    "831": 34548825,
    "832": 34632000,
    "833": 34715275,
    "834": 34798650,
    "835": 34882125,
    "836": 34965700,
    "837": 35049375,
    "838": 35133150,
    "839": 35217025,
    "840": 35301000,
    "841": 35385075,
    "842": 35469250,
    "843": 35553525,
    "844": 35637900,
    "845": 35722375,
    "846": 35806950,
    "847": 35891625,
    "848": 35976400,
    "849": 36061275,
    "850": 36146250,
    "851": 36231325,
    "852": 36316500,
    "853": 36401775,
    "854": 36487150,
    "855": 36572625,
    "856": 36658200,
    "857": 36743875,
    "858": 36829650,
    "859": 36915525,
    "860": 37001500,
    "861": 37087575,
    "862": 37173750,
    "863": 37260025,
    "864": 37346400,
    "865": 37432875,
    "866": 37519450,
    "867": 37606125,
    "868": 37692900,
    "869": 37779775,
    "870": 37866750,
    "871": 37953825,
    "872": 38041000,
    "873": 38128275,
    "874": 38215650,
    "875": 38303125,
    "876": 38390700,
    "877": 38478375,
    "878": 38566150,
    "879": 38654025,
    "880": 38742000,
    "881": 38830075,
    "882": 38918250,
    "883": 39006525,
    "884": 39094900,
    "885": 39183375,
    "886": 39271950,
    "887": 39360625,
    "888": 39449400,
    "889": 39538275,
    "890": 39627250,
    "891": 39716325,
    "892": 39805500,
    "893": 39894775,
    "894": 39984150,
    "895": 40073625,
    "896": 40163200,
    "897": 40252875,
    "898": 40342650,
    "899": 40432525,
    "900": 40522500,
    "901": 40612575,
    "902": 40702750,
    "903": 40793025,
    "904": 40883400,
    "905": 40973875,
    "906": 41064450,
    "907": 41155125,
    "908": 41245900,
    "909": 41336775,
    "910": 41427750,
    "911": 41518825,
    "912": 41610000,
    "913": 41701275,
    "914": 41792650,
    "915": 41884125,
    "916": 41975700,
    "917": 42067375,
    "918": 42159150,
    "919": 42251025,
    "920": 42343000,
    "921": 42435075,
    "922": 42527250,
    "923": 42619525,
    "924": 42711900,
    "925": 42804375,
    "926": 42896950,
    "927": 42989625,
    "928": 43082400,
    "929": 43175275,
    "930": 43268250,
    "931": 43361325,
    "932": 43454500,
    "933": 43547775,
    "934": 43641150,
    "935": 43734625,
    "936": 43828200,
    "937": 43921875,
    "938": 44015650,
    "939": 44109525,
    "940": 44203500,
    "941": 44297575,
    "942": 44391750,
    "943": 44486025,
    "944": 44580400,
    "945": 44674875,
    "946": 44769450,
    "947": 44864125,
    "948": 44958900,
    "949": 45053775,
    "950": 45148750,
    "951": 45243825,
    "952": 45339000,
    "953": 45434275,
    "954": 45529650,
    "955": 45625125,
    "956": 45720700,
    "957": 45816375,
    "958": 45912150,
    "959": 46008025,
    "960": 46104000,
    "961": 46200075,
    "962": 46296250,
    "963": 46392525,
    "964": 46488900,
    "965": 46585375,
    "966": 46681950,
    "967": 46778625,
    "968": 46875400,
    "969": 46972275,
    "970": 47069250,
    "971": 47166325,
    "972": 47263500,
    "973": 47360775,
    "974": 47458150,
    "975": 47555625,
    "976": 47653200,
    "977": 47750875,
    "978": 47848650,
    "979": 47946525,
    "980": 48044500,
    "981": 48142575,
    "982": 48240750,
    "983": 48339025,
    "984": 48437400,
    "985": 48535875,
    "986": 48634450,
    "987": 48733125,
    "988": 48831900,
    "989": 48930775,
    "990": 49029750,
    "991": 49128825,
    "992": 49228000,
    "993": 49327275,
    "994": 49426650,
    "995": 49526125,
    "996": 49625700,
    "997": 49725375,
    "998": 49825150,
    "999": 49925025,
}
