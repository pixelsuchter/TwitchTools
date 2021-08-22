import json
import os
import time
from pprint import pprint
from typing import Union, List, Iterable

import twitch
import twitchAPI
from twitchAPI import UserAuthenticator
from threading import Lock
import twitchchat
from functools import partial


class NoBotTokenException(Exception):
    pass


class Twitch_api:
    def __init__(self, run_flag):
        self.run_flag = run_flag
        self.credentials = {}
        self.load_credentials()

        self.api_lock = Lock()
        scopes = [twitchAPI.AuthScope.USER_EDIT, twitchAPI.AuthScope.MODERATION_READ, twitchAPI.AuthScope.CHANNEL_MODERATE, twitchAPI.AuthScope.CHANNEL_READ_REDEMPTIONS,
                  twitchAPI.AuthScope.CHAT_READ, twitchAPI.AuthScope.USER_READ_BLOCKED_USERS, twitchAPI.AuthScope.USER_MANAGE_BLOCKED_USERS]

        self.twitch_helix = twitchAPI.Twitch(app_id=self.credentials["client id"], app_secret=self.credentials["app secret"], target_app_auth_scope=scopes)
        self.twitch_helix.authenticate_app(scopes)

        token_status = twitchAPI.oauth.validate_token(self.credentials["oauth token"])
        try:
            _scopes = token_status["scopes"]

            for scope in scopes:
                if scope not in _scopes:
                    raise KeyError
        except KeyError:
            auth = UserAuthenticator(self.twitch_helix, scopes, force_verify=False)
            self.credentials["oauth token"], self.credentials["refresh token"] = auth.authenticate()
            with open("credentials.json", "w") as credentials_file:
                json.dump(self.credentials, credentials_file, indent="  ")
            token_status = twitchAPI.oauth.validate_token(self.credentials["oauth token"])

        self.own_id = token_status["user_id"]
        self.login = token_status["login"]
        print(self.login)

        self.twitch_helix.set_user_authentication(self.credentials["oauth token"], scopes, self.credentials["refresh token"])

        self.twitch_legacy = twitch.TwitchClient(client_id=self.credentials["client id"], oauth_token=self.credentials["oauth token"])

        bot_token = self.credentials['bot token'] if self.credentials['use seperate token for bot'] else self.credentials['oauth token']
        timeout = twitchchat.non_mod_timeout if self.credentials['use seperate token for bot'] else twitchchat.mod_timeout
        if not bot_token:
            raise NoBotTokenException
        else:
            self.bot = twitchchat.Bot(token=bot_token,
                                      client_id=self.own_id, nickname=self.credentials["bot nickname"],
                                      command_prefix=self.credentials["bot command prefix"],
                                      channels_to_join=self.credentials["bot channels"],
                                      message_timeout=timeout)

        self.pubsub = twitchAPI.pubsub.PubSub(self.twitch_helix)

    def load_credentials(self):
        # Default credentials
        with open("credentials.json", "r") as credentials_file:
            _credentials = json.load(credentials_file)
            self.credentials = _credentials


    # <editor-fold desc="TwitchAPI Section">
    def names_to_id(self, names: Union[List, str]):
        with self.api_lock:
            response = self.twitch_legacy.users.translate_usernames_to_ids(names)
        ids = [user["id"] for user in response]
        return ids

    def names_to_ids(self, user_names: List, progress_callback=None) -> dict:
        """
        :param user_names: List of Strings containing usernames
        :param progress_callback: callback to update Status Label
        :return: Dict of name:id pairs

        Converts a list of Usernames into their respective User ID's
        and returns them a dictionary mapping the two
        """
        total_num_of_ids = len(user_names)
        id_list = {}
        num_of_potential_names_done = 0
        if len(user_names) < 100 and self.run_flag[0]:
            with self.api_lock:
                num_of_potential_names_done += len(user_names)
                response = self.twitch_helix.get_users(logins=user_names)
                id_list.update({user["login"]: user["id"] for user in response["data"]})
                if progress_callback:
                    progress_callback.emit(f"Converting names to ID's {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(id_list)} Valid users")
        else:
            _user_names = user_names
            while len(_user_names) >= 100 and self.run_flag[0]:
                _user_names_part = _user_names[:100]
                with self.api_lock:
                    num_of_potential_names_done += len(_user_names_part)
                    response = self.twitch_helix.get_users(logins=_user_names_part)
                id_list.update({user["login"]: user["id"] for user in response["data"]})
                _user_names = _user_names[100:]
                if progress_callback:
                    progress_callback.emit(f"Converting names to ID's {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(id_list)} Valid users")
        if progress_callback:
            progress_callback.emit(f"Done")
        return id_list

    def id_to_name(self, user_id: str):
        with self.api_lock:
            response = self.twitch_helix.get_users(user_ids=[user_id])
        if response["data"]:
            return response["data"][0]["login"]
        else:
            return ""

    def ids_to_names(self, user_ids: List, progress_callback=None):
        total_num_of_ids = len(user_ids)
        namelist = {}
        num_of_potential_names_done = 0
        if len(user_ids) < 100 and self.run_flag[0]:
            with self.api_lock:
                num_of_potential_names_done += len(user_ids)
                response = self.twitch_helix.get_users(user_ids=user_ids)
                namelist.update({user["id"]: user["login"] for user in response["data"]})
                if progress_callback:
                    progress_callback.emit(f"Converting ID's to names {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(namelist)} Valid users")
        else:
            _user_ids = user_ids
            while len(_user_ids) >= 100 and self.run_flag[0]:
                _user_ids_part = _user_ids[:100]
                with self.api_lock:
                    num_of_potential_names_done += len(_user_ids_part)
                    response = self.twitch_helix.get_users(user_ids=_user_ids_part)
                namelist.update({user["id"]: user["login"] for user in response["data"]})
                _user_ids = _user_ids[100:]
                if progress_callback:
                    progress_callback.emit(f"Converting ID's to names {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(namelist)} Valid users")
        if progress_callback:
            progress_callback.emit(f"Done")
        return namelist

    def get_valid_users(self, user_names: List, progress_callback=None):
        total_num_of_ids = len(user_names)
        namelist = []
        num_of_potential_names_done = 0
        if len(user_names) < 100 and self.run_flag[0]:
            with self.api_lock:
                num_of_potential_names_done += len(user_names)
                response = self.twitch_helix.get_users(logins=user_names)
                namelist.extend([user["login"] for user in response["data"]])
                if progress_callback:
                    progress_callback.emit(f"Checking for valid users {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(namelist)} Valid users")
        else:
            _user_names = user_names
            while len(_user_names) >= 100 and self.run_flag[0]:
                _user_names_part = _user_names[:100]
                with self.api_lock:
                    try:
                        num_of_potential_names_done += len(_user_names_part)
                        response = self.twitch_helix.get_users(logins=_user_names_part)
                        namelist.extend([user["login"] for user in response["data"]])
                    except twitchAPI.TwitchAPIException:
                        print(_user_names_part)
                _user_names = _user_names[100:]
                if progress_callback:
                    progress_callback.emit(f"Checking for valid users {num_of_potential_names_done} out of (potentially) {total_num_of_ids}. {len(namelist)} Valid users")
        if progress_callback:
            progress_callback.emit(f"Done")
        return namelist

    def unblock_users(self, user_ids: List, progress_callback):
        user_list_length = len(user_ids)
        for num, user in enumerate(user_ids):
            if self.run_flag[0]:
                progress_callback.emit(f"Unblocked {num} out of {user_list_length}")
                with self.api_lock:
                    self.twitch_helix.unblock_user(target_user_id=user)
            else:
                break
        progress_callback.emit(f"Done")

    def block_users(self, user_ids: List, progress_callback):
        user_list_length = len(user_ids)
        for num, user in enumerate(user_ids):
            if self.run_flag[0]:
                progress_callback.emit(f"Blocked {num} out of {user_list_length}")
                with self.api_lock:
                    try:
                        self.twitch_helix.block_user(target_user_id=user)
                    except json.JSONDecodeError:  # api call actually throws exception on blocking, but still works
                        pass
            else:
                break
        progress_callback.emit(f"Done")

    def get_all_followed_channel_names(self, user_id, progress_callback):
        with self.api_lock:
            response = self.twitch_helix.get_users_follows(from_id=user_id, first=100)
        progress_callback.emit({follow["to_login"]: follow["followed_at"] for follow in response["data"]})
        offset = response["pagination"]
        i = 0
        while response["pagination"] and self.run_flag[0]:
            with self.api_lock:
                response = self.twitch_helix.get_users_follows(from_id=user_id, first=100, after=offset["cursor"])
                i += 1
            progress_callback.emit({follow["to_login"]: follow["followed_at"] for follow in response["data"]})
            offset = response["pagination"]

    def get_all_channel_followers_names(self, user_id, progress_callback):
        with self.api_lock:
            response = self.twitch_helix.get_users_follows(to_id=user_id, first=100)
        progress_callback.emit({follow["from_login"]: follow["followed_at"] for follow in response["data"]})
        offset = response["pagination"]
        i = 0
        while response["pagination"] and self.run_flag[0]:
            with self.api_lock:
                response = self.twitch_helix.get_users_follows(to_id=user_id, first=100, after=offset["cursor"])
                i += 1
            progress_callback.emit({follow["from_login"]: follow["followed_at"] for follow in response["data"]})
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
            while page and self.run_flag[0]:
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
            progress_callback.emit([[response_element["user_login"], response_element["user_id"], response_element["expires_at"]] for response_element in response["data"]])
            page = response["pagination"]
            while page and self.run_flag[0]:
                with self.api_lock:
                    response = self.twitch_helix.get_banned_users(broadcaster_id=self.own_id, first=100, after=page["cursor"])
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
