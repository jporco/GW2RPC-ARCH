from .api import api

PROFESSIONS = {
    "1": "Guardian",
    "2": "Warrior",
    "3": "Engineer",
    "4": "Ranger",
    "5": "Thief",
    "6": "Elementalist",
    "7": "Mesmer",
    "8": "Necromancer",
    "9": "Revenant",
    "10": "Jade Bot"
}

RACES = {"0": "Asura", "1": "Charr", "2": "Human", "3": "Norn", "4": "Sylvari", "5": "Jade Bot"}

ELITESPECS = {
    "5": "Druid",
    "7": "Daredevil",
    "18": "Berserker",
    "27": "Dragonhunter",
    "34": "Reaper",
    "40": "Chronomancer",
    "43": "Scrapper",
    "48": "Tempest",
    "52": "Herald",
    "55": "Soulbeast",
    "56": "Weaver",
    "57": "Holosmith",
    "58": "Deadeye",
    "59": "Mirage",
    "60": "Scourge",
    "61": "Spellbreaker",
    "62": "Firebrand",
    "63": "Renegade",
    "64": "Harbinger",
    "65": "Willbender",
    "66": "Virtuoso",
    "67": "Catalyst",
    "68": "Bladesworn",
    "69": "Vindicator",
    "70": "Mechanist",
    "71": "Specter",
    "72": "Untamed",
    "73": "Troubadour",
    "74": "Paragon",
    "75": "Amalgam",
    "76": "Ritualist",
    "77": "Antiquary",
    "78": "Galeshot",
    "79": "Conduit",
    "80": "Evoker",
    "81": "Luminary"    
}


class Character:
    def __init__(self, mumble_data, registry, query_guild=True):
        self.__mumble_data = mumble_data
        self.name = mumble_data.get("name", "Unknown")
        # races may be missing from registry; fall back to local mapping (string keys)
        self.races = registry.get("races") or RACES
        self.professions = registry.get("professions") or PROFESSIONS
        self.elite_specs = registry.get("elitespecs") or ELITESPECS

        try:
            race_id = str(mumble_data.get("race", "0"))
            self.race = self.races.get(race_id, "")
        except Exception:
            self.race = ""
        self.__api_info = None

        if query_guild and api._authenticated:
            self.__api_info = api.get_character(self.name)

        self.profession = self.get_elite_spec()
        if self.profession:
            self.profession_icon = "prof_{}".format(
                self.profession.lower().replace(" ", ""))
        else:
            self.profession = ""
            self.profession_icon = "gw2rpclogo"
        self.guild_tag = self._get_guild_tag()

    def get_elite_spec(self):
        spec_id = str(self.__mumble_data.get("spec", ""))
        profession_id = str(self.__mumble_data.get("profession", ""))
        
        if spec_id not in self.elite_specs.keys():
            # Meaning that its a core class, fall back
            try:
                return self.professions.get(profession_id)
            except Exception:
                return None
        else:
            return self.elite_specs.get(spec_id)

    def _get_guild_tag(self):
        tag = ""
        if self.__api_info:
            gid = self.__api_info.get("guild")
            if gid:
                try:
                    res = api.get_guild(gid)
                    tag = " [{}]".format(res["tag"])
                except:
                    pass
        return tag
