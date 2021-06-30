import json
from pprint import pprint
from typing import Union, List

import twitch
import twitchAPI
from twitchAPI import UserAuthenticator
from threading import Lock



class Twitch_api:
    def __init__(self):
        self.api_lock = Lock()
        scopes = [twitchAPI.AuthScope.USER_EDIT, twitchAPI.AuthScope.MODERATION_READ, twitchAPI.AuthScope.CHANNEL_READ_REDEMPTIONS, twitchAPI.AuthScope.CHAT_READ,
                  twitchAPI.AuthScope.USER_READ_BLOCKED_USERS]

        with open("credentials.json", "r") as credentials_file:
            credentials = json.load(credentials_file)

        self.twitch_helix = twitchAPI.Twitch(app_id=credentials["client id"], app_secret=credentials["app secret"], target_app_auth_scope=scopes)
        self.twitch_helix.authenticate_app(scopes)

        token_status = twitchAPI.oauth.validate_token(credentials["oauth token"])
        if "login" not in token_status.keys():
            auth = UserAuthenticator(self.twitch_helix, scopes, force_verify=False)
            credentials["oauth token"], credentials["refresh token"] = auth.authenticate()
            with open("credentials.json", "w") as credentials_file:
                json.dump(credentials, credentials_file, indent="  ")
            token_status = twitchAPI.oauth.validate_token(credentials["oauth token"])
        self.own_id = token_status["user_id"]

        self.twitch_helix.set_user_authentication(credentials["oauth token"], scopes, credentials["refresh token"])

        self.twitch_legacy = twitch.TwitchClient(client_id=credentials["client id"], oauth_token=credentials["oauth token"])

    def names_to_id(self, names: Union[List, str]):
        with self.api_lock:
            response = self.twitch_legacy.users.translate_usernames_to_ids(names)
        ids = [user["id"] for user in response]
        return ids

    def get_all_followed_channel_names(self, user_id, progress_callback):
        with self.api_lock:
            response = self.twitch_helix.get_users_follows(from_id=user_id, first=100)
        progress_callback.emit({follow["to_login"]: follow["followed_at"] for follow in response["data"]})
        offset = response["pagination"]
        i = 0
        while response["pagination"]:
            with self.api_lock:
                response = self.twitch_helix.get_users_follows(from_id=user_id, first=100, after=offset["cursor"])
                i += 1
            progress_callback.emit({follow["to_login"]: follow["followed_at"] for follow in response["data"]})
            offset = response["pagination"]


    def get_user_info(self, user_id, progress_callback):
        with self.api_lock:
            userinfo = self.twitch_legacy.users.get_by_id(user_id)
        progress_callback.emit(userinfo)


    def get_all_blocked_users(self, progress_callback):
        try:
            response = self.twitch_helix.get_user_block_list(broadcaster_id=self.own_id, first=100)
            progress_callback.emit({follow["user_login"]: follow["user_id"] for follow in response["data"]})
            page = response["pagination"]
            while response["pagination"]:
                with self.api_lock:
                    response = self.twitch_helix.get_user_block_list(broadcaster_id=self.own_id, first=100, after=page["cursor"])
                progress_callback.emit({follow["user_login"]: follow["user_id"] for follow in response["data"]})
                page = response["pagination"]
        except Exception as e:
            print(e)
