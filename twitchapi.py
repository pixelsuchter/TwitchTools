import json
from pprint import pprint
from typing import Union, List

import twitch
import twitchAPI

with open("credentials.json", "r") as credential_file:
    credentials = json.load(credential_file)


class Twitch_api:
    def __init__(self):
        scopes = [twitchAPI.AuthScope.USER_EDIT, twitchAPI.AuthScope.MODERATION_READ, twitchAPI.AuthScope.CHANNEL_READ_REDEMPTIONS, twitchAPI.AuthScope.CHAT_READ]

        self.twitch_legacy = twitch.TwitchClient(client_id=credentials["client id"], oauth_token=credentials["oauth token"])
        self.twitch_helix = twitchAPI.Twitch(app_id=credentials["client id"], app_secret=credentials["app secret"], target_app_auth_scope=[twitchAPI.AuthScope.USER_EDIT])
        self.twitch_helix.authenticate_app(scopes)

    def names_to_id(self, names: Union[List, str]):
        response = self.twitch_legacy.users.translate_usernames_to_ids(names)
        ids = [user["id"] for user in response]
        return ids

    def get_followed_channel_names(self, user_id, limit=100):
        response = self.twitch_helix.get_users_follows(from_id=user_id, first=limit)
        pprint(response)
        names = [follow["to_login"] for follow in response["data"]]
        return names

    def get_all_followed_channel_names(self, user_id):
        response = self.twitch_helix.get_users_follows(from_id=user_id, first=100)
        total_length = response["total"]
        names = {follow["to_login"]: follow["followed_at"] for follow in response["data"]}
        offset = response["pagination"]
        while len(names.keys()) < total_length:
            response = self.twitch_helix.get_users_follows(from_id=user_id, first=min(100, total_length-len(names)), after=offset["cursor"])
            names.update({follow["to_login"]: follow["followed_at"] for follow in response["data"]})
            offset = response["pagination"]
        print(len(names), " of ", total_length)
        return names
