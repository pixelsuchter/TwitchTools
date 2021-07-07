import json
import os
import time
from pprint import pprint
from typing import Union, List

import twitch
import twitchAPI
from twitchAPI import UserAuthenticator
from threading import Lock
import twitchchat
from functools import partial


class Twitch_api:
    def __init__(self):
        self.credentials = {"client id": "", "app secret": "", "oauth token": "", "refresh token": "", "bot nickname": "", "bot command prefix": "!", "bot channels": [""]}
        self.load_credentials()

        self.api_lock = Lock()
        scopes = [twitchAPI.AuthScope.USER_EDIT, twitchAPI.AuthScope.MODERATION_READ, twitchAPI.AuthScope.CHANNEL_MODERATE, twitchAPI.AuthScope.CHANNEL_READ_REDEMPTIONS,
                  twitchAPI.AuthScope.CHAT_READ, twitchAPI.AuthScope.USER_READ_BLOCKED_USERS]

        self.twitch_helix = twitchAPI.Twitch(app_id=self.credentials["client id"], app_secret=self.credentials["app secret"], target_app_auth_scope=scopes)
        self.twitch_helix.authenticate_app(scopes)

        token_status = twitchAPI.oauth.validate_token(self.credentials["oauth token"])
        if "login" not in token_status.keys():
            auth = UserAuthenticator(self.twitch_helix, scopes, force_verify=False)
            self.credentials["oauth token"], self.credentials["refresh token"] = auth.authenticate()
            with open("credentials.json", "w") as credentials_file:
                json.dump(self.credentials, credentials_file, indent="  ")
            token_status = twitchAPI.oauth.validate_token(self.credentials["oauth token"])
        self.own_id = token_status["user_id"]

        self.twitch_helix.set_user_authentication(self.credentials["oauth token"], scopes, self.credentials["refresh token"])

        self.twitch_legacy = twitch.TwitchClient(client_id=self.credentials["client id"], oauth_token=self.credentials["oauth token"])

        self.bot = twitchchat.Bot(token=f"oauth:{self.credentials['oauth token']}", client_id=self.own_id, nickname=self.credentials["bot nickname"],
                                  command_prefix=self.credentials["bot command prefix"], channels_to_join=self.credentials["bot channels"])

        self.pubsub = twitchAPI.pubsub.PubSub(self.twitch_helix)


    def load_credentials(self):
        # Default credentials
        self.credentials = {"client id": "", "app secret": "", "oauth token": "", "refresh token": "", "bot nickname": "", "bot command prefix": "!", "bot channels": [""]}

        try:
            with open("credentials.json", "r") as credentials_file:
                _credentials = json.load(credentials_file)
                assert _credentials.keys() == self.credentials.keys()
                self.credentials = _credentials
        except (OSError, AssertionError):
            with open("credentials.json", "w") as credentials_file:
                print("Credentials file corrupt, generated new")
                self.credentials.update(_credentials)
                json.dump(self.credentials, credentials_file, indent="  ")

    # <editor-fold desc="TwitchAPI Section">
    def names_to_id(self, names: Union[List, str]):
        with self.api_lock:
            response = self.twitch_legacy.users.translate_usernames_to_ids(names)
        ids = [user["id"] for user in response]
        return ids

    def id_to_name(self, user_id):
        with self.api_lock:
            response = self.twitch_helix.get_users(user_ids=[user_id])
        if response["data"]:
            return response["data"][0]["login"]
        else:
            return ""

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
            with self.api_lock:
                response = self.twitch_helix.get_user_block_list(broadcaster_id=self.own_id, first=100)
            progress_callback.emit({response_element["user_login"]: response_element["user_id"] for response_element in response["data"]})
            page = response["pagination"]
            while page:
                with self.api_lock:
                    response = self.twitch_helix.get_user_block_list(broadcaster_id=self.own_id, first=100, after=page["cursor"])
                progress_callback.emit({response_element["user_login"]: response_element["user_id"] for response_element in response["data"]})
                page = response["pagination"]
        except Exception as e:
            print(e)

    def get_banned_users(self, progress_callback):
        try:
            with self.api_lock:
                response = self.twitch_helix.get_banned_users(broadcaster_id=self.own_id, first=100)
                print(response)
            progress_callback.emit([[response_element["user_login"], response_element["user_id"], response_element["expires_at"]] for response_element in response["data"]])
            page = response["pagination"]
            while page:
                with self.api_lock:
                    response = self.twitch_helix.get_banned_users(broadcaster_id=self.own_id, first=100, after=page["cursor"])
                    print(response)
                progress_callback.emit([[response_element["user_login"], response_element["user_id"], response_element["expires_at"]] for response_element in response["data"]])
                page = response["pagination"]
                time.sleep(1)
        except Exception as e:
            print(e)

    # </editor-fold>

    # <editor-fold desc="Pubsub Section">
    def init_pubsub(self, progress_callback):
        mod_actions_callback = partial(self.pubsub_mod_actions_callback, progress_callback)
        channel_ids = self.names_to_id(self.credentials["bot channels"])
        for channel in channel_ids:
            self.pubsub.listen_chat_moderator_actions(self.own_id, channel, mod_actions_callback)

        self.pubsub.start()


    def pubsub_mod_actions_callback(self, mod_action_signal, *args):
        mod_action_signal.emit(args)
    # </editor-fold>
