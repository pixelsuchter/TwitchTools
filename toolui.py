import asyncio
import csv
import datetime
import json
import os.path
import pickle
import sys
import time
import traceback
import re
from functools import partial
from json import JSONEncoder
from typing import Dict, List, Union, Tuple

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Slot, QRunnable, Signal, QObject, QThreadPool
from PySide6.QtGui import Qt, QIcon
from PySide6.QtWidgets import *

import twitchapi
import twitchio

modactions_seperate_file_to_individual_actions_regex = re.compile(r".*\n\n.*\n\n.*\n.*|.*\n\n.*\n.*")
modactions_get_mod_in_timeout_string_regex = re.compile(r"Timed out by (.*)for (.*) (second|seconds)")
modactions_get_mod_in_permitted_term_string_regex = re.compile(r"Added as Permitted Term by (\w+)( via AutoMod)?")
modactions_get_mod_in_blocked_term_string_regex = re.compile(r"Added as Blocked Term by (\w+)( via AutoMod)?")


# <editor-fold desc="Filter Class">
class Filter:
    FILTER_TYPES = ("Full match", "Match partially", "Regular Expression")
    FILTER_TARGETS = ("Message", "Author")
    FILTER_PENALITYS = ("Delete Message", "Timeout 1m", "Timeout 10m", "Ban")

    def __init__(self, filter_string: str, filter_type: str, target: str, penality: str):
        self.filter_str = filter_string.strip()
        self.filter_type = filter_type
        self.compiled_regex = re.compile(filter_string)
        self.target = target
        self.penality = penality

    def filter(self, message: twitchio.Message) -> Union[Tuple[str, str], None]:
        string_to_filter = message.content.strip() if self.target == "Message" else message.author.name
        if self.filter_type == "Full match":
            return (string_to_filter.strip(), self.penality) if string_to_filter.strip() == self.filter_str else None

        elif self.filter_type == "Match partially":
            return (self.filter_str, self.penality) if self.filter_str in string_to_filter else None

        elif self.filter_type == "Regular Expression":
            match = self.compiled_regex.search(string_to_filter)
            return (match.group(0), self.penality) if match else None

        else:
            print(f"Unknown filter type {self.filter_type}")
        return None
# </editor-fold>

# <editor-fold desc="Multithread worker">
class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    progress
        int indicating % progress

    """
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(object)


class Worker(QRunnable):
    """
    Worker thread

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param callback: The function callback to run on this worker thread. Supplied args and
                     kwargs will be passed through to the runner.
    :type callback: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    """

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()

        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

        # Add the callback to our kwargs
        self.kwargs['progress_callback'] = self.signals.progress

    @Slot()
    def run(self):
        """
        Initialise the runner function with passed args, kwargs.
        """

        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(*self.args, **self.kwargs)
        except asyncio.CancelledError:  # gets thrown on exit
            pass
        except:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done


# </editor-fold>


class TwitchToolUi(QtWidgets.QWidget):
    def __init__(self, settings):
        super(TwitchToolUi, self).__init__()
        self.run_api = [True]
        self.run_bot = [True]
        self.old_settings = settings.copy()
        self.settings = settings
        self.chat_widgets: Dict[str, QTableWidget] = {}
        self.filter_list: List[Filter] = []

        self.status_list = ["Idle"]

        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        self.tool_tab_widget = QtWidgets.QTabWidget()
        self.following_tab = QtWidgets.QTabWidget()
        self.user_info_tab = QtWidgets.QTabWidget()
        self.blocklist_info_tab = QtWidgets.QTabWidget()
        self.banlist_info_tab = QtWidgets.QTabWidget()
        self.mod_actions_tab = QtWidgets.QTabWidget()
        self.chat_tab = QtWidgets.QTabWidget()
        self.settings_tab = QtWidgets.QTabWidget()

        self.tool_tab_widget.addTab(self.following_tab, "Following")
        self.tool_tab_widget.addTab(self.user_info_tab, "User Info")
        self.tool_tab_widget.addTab(self.blocklist_info_tab, "Blocklist Info")
        self.tool_tab_widget.addTab(self.banlist_info_tab, "Banlist Info")
        self.tool_tab_widget.addTab(self.mod_actions_tab, "Moderator Actions")
        self.tool_tab_widget.addTab(self.chat_tab, "Chatrooms")
        self.tool_tab_widget.addTab(self.settings_tab, "Settings")

        self.tool_tab_widget.currentChanged.connect(self.tab_clicked)

        self.status_label = QLabel()
        self.status_label.setText("")
        self.progess_label = QLabel()

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_label)
        status_row.addWidget(self.progess_label)

        layout = QVBoxLayout()
        layout.addWidget(self.tool_tab_widget)
        layout.addLayout(status_row)
        self.setLayout(layout)

        self.api = twitchapi.Twitch_api(self.run_api)
        self.bot_worker = Worker(self.api.bot.run, run_flag=self.run_bot)
        self.bot_worker.signals.progress.connect(self.handle_chat_message)
        self.threadpool.start(self.bot_worker)
        self.pubsub_worker = Worker(self.api.init_pubsub)
        self.pubsub_worker.signals.progress.connect(self.pubsub_mod_action_handler)
        self.threadpool.start(self.pubsub_worker)

        self.init_follow_grabber(self.following_tab)
        self.init_user_info(self.user_info_tab)
        self.init_blocklist_info(self.blocklist_info_tab)
        self.init_banlist_info(self.banlist_info_tab)
        self.init_mod_actions_tab(self.mod_actions_tab)
        self.init_chat_tab(self.chat_tab)
        self.init_settings_tab(self.settings_tab)

        self.load_filters()

    def tab_clicked(self):
        if self.tool_tab_widget.currentWidget() is self.settings_tab:
            # Update settings
            self.settings["Window Size"] = [self.size().width(), self.size().height()]
            self.settings["Maximized"] = self.isMaximized()

            # Update labels
            self.settings_window_width_LineEdit.setText(str(self.settings["Window Size"][0]))
            self.settings_window_height_LineEdit.setText(str(self.settings["Window Size"][1]))

    def handle_chat_message(self, message: twitchio.Message):
        try:
            chnl = message.channel.name
            user = message.author.name
            if chnl in self.chat_widgets.keys():
                self.chat_widgets[chnl].insertRow(0)
                self.chat_widgets[chnl].setItem(0, 0, QTableWidgetItem(user))
                self.chat_widgets[chnl].setItem(0, 1, QTableWidgetItem(message.content))
                self.chat_widgets[chnl].removeRow(500)

                for fltr in self.filter_list:
                    result = fltr.filter(message)
                    if result:
                        print(f"filter triggered: {fltr.filter_type}\nMessage Author: {message.author.name}\nMessage Content: {message.content.strip()}\nTriggering Part:{result[0]}\nPenality: {result[1]}")
        except AttributeError:
            pass

    def set_progress_label(self, text):
        self.progess_label.setText(text)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not (self.settings == self.old_settings):
            with open("settings.json", "w") as settings_file:
                json.dump(self.settings, settings_file, indent="  ")
                print("Settings saved")
        self.run_api[0] = False
        self.run_bot[0] = False
        self.api.pubsub.stop()

    # <editor-fold desc="Status bar">
    def add_status(self, status: str):
        self.status_list.append(status)
        self.update_status()

    def update_status(self):
        self.status_label.setText(self.status_list[-1])

    def remove_status(self, status: str):
        self.status_list.remove(status)
        self.update_status()

    # </editor-fold>

    # <editor-fold desc="Follow Grabber">
    # Follow Grabber
    def init_follow_grabber(self, parent):
        # Create widgets
        self.follow_grabber_username_LineEdit = QLineEdit("")
        self.follow_grabber_getFollowing_Button = QPushButton("Get Following")
        self.follow_grabber_getFollowers_Button = QPushButton("Get Followers")
        self.follow_grabber_follow_Table = QTableWidget()
        self.follow_grabber_follow_Table.setColumnCount(2)
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(0, QTableWidgetItem("Name"))
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(1, QTableWidgetItem("Time of follow"))
        self.follow_grabber_follow_Table.resizeColumnsToContents()
        self.follow_grabber_followList_SortingBox = QComboBox()
        self.follow_grabber_followList_SortingBox.addItems(
            ["Name A-Z", "Name Z-A", "Follow time New-Old", "Follow time Old-New"])

        # Create layout and add widgets
        buttonrow = QHBoxLayout()
        buttonrow.addWidget(self.follow_grabber_username_LineEdit)
        buttonrow.addWidget(self.follow_grabber_getFollowing_Button)
        buttonrow.addWidget(self.follow_grabber_getFollowers_Button)


        layout = QVBoxLayout()
        layout.addLayout(buttonrow)
        layout.addWidget(self.follow_grabber_followList_SortingBox)
        layout.addWidget(self.follow_grabber_follow_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.follow_grabber_getFollowing_Button.clicked.connect(partial(self.follow_grabber_get_following_button_action, "Following"))
        self.follow_grabber_getFollowers_Button.clicked.connect(partial(self.follow_grabber_get_following_button_action, "Followers"))
        self.follow_grabber_followList_SortingBox.currentTextChanged.connect(
            self.follow_grabber_follow_list_sorting_box_action)
        self.follow_grabber_follow_Table.doubleClicked.connect(self.follow_grabber_follow_table_action)

    def follow_grabber_follow_table_action(self, model_index: QtCore.QModelIndex):
        name = self.follow_grabber_follow_Table.item(model_index.row(), 0).text()
        self.user_info_username_LineEdit.setText(name)
        self.user_info_get_info_button_action()
        self.tool_tab_widget.setCurrentWidget(self.user_info_tab)

    def follow_grabber_follow_list_sorting_box_action(self):
        if self.follow_grabber_followList_SortingBox.currentText() == "Name A-Z":
            self.follow_grabber_follow_Table.sortByColumn(0, Qt.AscendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Name Z-A":
            self.follow_grabber_follow_Table.sortByColumn(0, Qt.DescendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Follow time New-Old":
            self.follow_grabber_follow_Table.sortByColumn(1, Qt.DescendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Follow time Old-New":
            self.follow_grabber_follow_Table.sortByColumn(1, Qt.AscendingOrder)
        else:
            self.add_status("Error in follow grabber")

    # <editor-fold desc="Follow grabber button action">
    def follow_grabber_get_following_button_action(self, follow_direction):
        self.follow_grabber_getFollowing_Button.setEnabled(False)
        self.add_status("Getting followers, please wait")
        self.follow_grabber_follow_Table.clearContents()
        self.follow_grabber_follow_Table.setRowCount(0)
        name = self.follow_grabber_username_LineEdit.text()
        if name:
            user_id = self.api.names_to_id(name)
            if user_id:
                user_id = user_id[0]
                if follow_direction == "Following":
                    worker = Worker(self.api.get_all_followed_channel_names, user_id)
                    worker.signals.progress.connect(self.follow_grabber_get_follows_button_thread_return)
                    worker.signals.result.connect(self.follow_grabber_get_follows_button_thread_done)
                    self.threadpool.start(worker)
                elif follow_direction == "Followers":
                    worker = Worker(self.api.get_all_channel_followers_names, user_id)
                    worker.signals.progress.connect(self.follow_grabber_get_follows_button_thread_return)
                    worker.signals.result.connect(self.follow_grabber_get_follows_button_thread_done)
                    self.threadpool.start(worker)
                else:
                    self.follow_grabber_get_follows_button_thread_done()
            else:
                self.follow_grabber_get_follows_button_thread_done()
        else:
            self.follow_grabber_get_follows_button_thread_done()

    def follow_grabber_get_follows_button_thread_return(self, follows):
        row_count = self.follow_grabber_follow_Table.rowCount()
        self.follow_grabber_follow_Table.setRowCount(row_count + len(follows))
        for row, line in enumerate(follows.items()):
            for col, entry in enumerate(line):
                self.follow_grabber_follow_Table.setItem(row + row_count, col, QTableWidgetItem(QIcon(), str(entry)))

    def follow_grabber_get_follows_button_thread_done(self):
        self.follow_grabber_follow_Table.sortByColumn(1, Qt.DescendingOrder)
        follow_dict: Dict[str, List[str]] = {}
        for i in range(self.follow_grabber_follow_Table.rowCount()):
            follow_time = self.follow_grabber_follow_Table.item(i, 1).text()
            if follow_time in follow_dict.keys():
                follow_dict[follow_time].append(self.follow_grabber_follow_Table.item(i, 0).text())
            else:
                follow_dict[follow_time] = [self.follow_grabber_follow_Table.item(i, 0).text()]
        print(follow_dict)
        potential_bots = []
        for follow_per_second in follow_dict.values():
            if len(follow_per_second) >= 3:
                potential_bots.extend(follow_per_second)
        print(potential_bots)
        for i in range(self.follow_grabber_follow_Table.rowCount()):
            name = self.follow_grabber_follow_Table.item(i, 0).text()
            if name in potential_bots:
                self.follow_grabber_follow_Table.item(i, 0).setBackground(QtGui.QColor(100, 0, 0))
                self.follow_grabber_follow_Table.item(i, 1).setBackground(QtGui.QColor(100, 0, 0))

        self.follow_grabber_follow_list_sorting_box_action()  # Update sorting
        self.follow_grabber_follow_Table.resizeColumnsToContents()
        self.remove_status("Getting followers, please wait")
        self.follow_grabber_getFollowing_Button.setEnabled(True)

    # </editor-fold>

    # </editor-fold>

    # <editor-fold desc="User Info">
    # User info
    def init_user_info(self, parent):
        # Create Widgets
        self.user_info_username_LineEdit = QLineEdit("")
        self.user_info_getInfo_Button = QPushButton("Get User Info")
        self.user_info_info_Table = QTableWidget()
        self.user_info_info_Table.setColumnCount(2)
        self.user_info_info_Table.setHorizontalHeaderItem(0, QTableWidgetItem(" "))
        self.user_info_info_Table.setHorizontalHeaderItem(1, QTableWidgetItem(" "))

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.user_info_username_LineEdit)
        layout.addWidget(self.user_info_getInfo_Button)
        layout.addWidget(self.user_info_info_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.user_info_getInfo_Button.clicked.connect(self.user_info_get_info_button_action)

    def user_info_get_info_button_action(self):
        self.add_status("Getting user information, please wait")
        self.user_info_info_Table.clearContents()
        name = self.user_info_username_LineEdit.text()
        if name:
            result = self.api.names_to_id(name)
            if result:
                user_id = result[0]
                if user_id:
                    worker = Worker(self.api.get_user_info, user_id)
                    worker.signals.progress.connect(self.user_info_get_info_button_progress)
                    worker.signals.result.connect(self.user_info_get_info_button_done)
                    self.threadpool.start(worker)
                else:
                    self.user_info_get_info_button_progress(None)
            else:
                self.user_info_get_info_button_progress(None)
        else:
            self.user_info_get_info_button_done()

    def user_info_get_info_button_progress(self, user_info):
        if user_info:
            self.user_info_info_Table.setRowCount(len(user_info["data"][0].items()))
            for row, line in enumerate(user_info["data"][0].items()):
                for col, entry in enumerate(line):
                    self.user_info_info_Table.setItem(row, col, QTableWidgetItem(str(entry)))
            self.user_info_info_Table.resizeColumnsToContents()
        else:
            self.user_info_info_Table.setRowCount(1)
            self.user_info_info_Table.setItem(0, 0, QTableWidgetItem("User"))
            self.user_info_info_Table.setItem(0, 1, QTableWidgetItem("Invalid"))

    def user_info_get_info_button_done(self):
        self.remove_status("Getting user information, please wait")

    # </editor-fold>

    # <editor-fold desc="Blocklist Info">
    def init_blocklist_info(self, parent):
        # Create Widgets
        self.blocklist_get_blocklist_Button = QPushButton("Get Blocklist")
        self.blocklist_clean_blocklist_Button = QPushButton("Clean Blocklist")
        self.blocklist_import_blocklist_Button = QPushButton("Import Blocklist")
        self.blocklist_api_Table = QTableWidget()
        self.blocklist_api_Table.setColumnCount(2)
        self.blocklist_api_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User Name"))
        self.blocklist_api_Table.setHorizontalHeaderItem(1, QTableWidgetItem("User ID"))
        self.blocklist_import_Table = QTableWidget()
        self.blocklist_import_Table.setColumnCount(2)
        self.blocklist_import_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User Name"))
        self.blocklist_import_Table.setHorizontalHeaderItem(1, QTableWidgetItem("User ID"))
        self.blocklist_block_imported_list_Button = QPushButton("Block imported List")

        # Create layout and add widgets
        button_row_layout = QHBoxLayout()
        button_row_layout.addWidget(self.blocklist_get_blocklist_Button)
        button_row_layout.addWidget(self.blocklist_clean_blocklist_Button)
        button_row_layout.addWidget(self.blocklist_import_blocklist_Button)
        button_row_layout.addWidget(self.blocklist_block_imported_list_Button)

        table_layout = QHBoxLayout()
        table_layout.addWidget(self.blocklist_api_Table)
        table_layout.addWidget(self.blocklist_import_Table)

        layout = QVBoxLayout()
        layout.addLayout(button_row_layout)
        layout.addLayout(table_layout)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.blocklist_get_blocklist_Button.clicked.connect(self.blocklist_get_blocklist_Button_action)
        self.blocklist_clean_blocklist_Button.clicked.connect(self.blocklist_clean_blocklist_button_callback)
        self.blocklist_import_blocklist_Button.clicked.connect(self.blocklist_import_blocklist_Button_callback)
        self.blocklist_block_imported_list_Button.clicked.connect(self.blocklist_block_imported_list_Button_callback)

    def blocklist_block_imported_list_Button_callback(self):
        self.blocklist_block_imported_list_Button.setEnabled(False)
        result = QMessageBox.question(self, "Blocklist", "Update Blocklist?", QMessageBox.Yes, QMessageBox.No)
        if result == QMessageBox.Yes:
            self.blocklist_get_blocklist_Button_action()
        worker = Worker(self.blocklist_block_imported_list_Button_synced)
        self.threadpool.start(worker)

    def blocklist_block_imported_list_Button_synced(self, progress_callback):
        while "Grabbing blocklist, please wait" in self.status_list:
            time.sleep(0.1)
        already_blocked_ids = set()  # set used for performance reasons
        for i in range(self.blocklist_api_Table.rowCount()):
            item = self.blocklist_api_Table.item(i, 1)
            if item:
                user_id = item.text()
                if user_id:
                    already_blocked_ids.add(user_id)
        ids_to_block = []
        for i in range(self.blocklist_import_Table.rowCount()):
            item = self.blocklist_import_Table.item(i, 1)
            if item:
                user_id = item.text()
                if user_id and user_id not in already_blocked_ids:  # filter out duplicate blocks
                    ids_to_block.append(user_id)
        worker = Worker(self.api.block_users, ids_to_block)
        worker.signals.progress.connect(self.set_progress_label)
        self.threadpool.start(worker)
        self.blocklist_block_imported_list_Button.setEnabled(True)

    def blocklist_import_blocklist_Button_callback(self):
        _table = self.blocklist_import_Table
        files_to_read = QFileDialog.getOpenFileNames(caption="Select files to import", dir="", filter="Commanderroot CSV Files (*.csv);;Text files (*.txt)")
        for file_path in files_to_read[0]:
            if files_to_read[1] == "Commanderroot CSV Files (*.csv)":
                with open(file_path, "r", encoding="utf-8") as file:
                    csv_data = csv.reader(file.readlines())
                    for data in csv_data:
                        if data[0] != "userName":
                            _table.insertRow(0)
                            _table.setItem(0, 0, QTableWidgetItem(str(data[0])))
                            _table.setItem(0, 1, QTableWidgetItem(str(data[1])))
            elif files_to_read[1] == "Text files (*.txt)":
                with open(file_path, "r") as file:
                    lines = file.readlines()
                    old_rowcount = _table.rowCount()
                    _table.setRowCount(old_rowcount + len(lines))
                    idx = 0
                    for name in lines:
                        if name.strip().lower():
                            _table.setItem(old_rowcount + idx, 0, QTableWidgetItem(name.strip().lower()))
                            idx += 1
                names_no_id = []
                for idx in range(_table.rowCount()):
                    name_item, id_item = _table.item(idx, 0), _table.item(idx, 1)
                    if name_item:
                        if id_item:
                            print(name_item.text(), id_item.text())
                        else:
                            names_no_id.append(name_item.text())
                worker = Worker(self.api.names_to_ids, names_no_id)
                worker.signals.progress.connect(self.set_progress_label)
                worker.signals.result.connect(self.blocklist_import_blocklist_covert_to_ids_callback)
                self.threadpool.start(worker)

    def blocklist_import_blocklist_covert_to_ids_callback(self, names_by_id):
        self.blocklist_import_Table.clear()
        self.blocklist_import_Table.setRowCount(len(names_by_id))
        for idx, (_name, _id) in enumerate(names_by_id.items()):
            self.blocklist_import_Table.setItem(idx, 0, QTableWidgetItem(_name))
            self.blocklist_import_Table.setItem(idx, 1, QTableWidgetItem(_id))
        self.blocklist_import_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User Name"))
        self.blocklist_import_Table.setHorizontalHeaderItem(1, QTableWidgetItem("User ID"))

    def blocklist_get_blocklist_Button_action(self):
        self.blocklist_get_blocklist_Button.setEnabled(False)
        self.blocklist_clean_blocklist_Button.setEnabled(False)
        self.add_status("Grabbing blocklist, please wait")
        self.blocklist_api_Table.clearContents()
        self.blocklist_api_Table.setRowCount(0)
        worker = Worker(self.api.get_all_blocked_users)
        worker.signals.progress.connect(self.blocklist_get_blocklist_Button_progress)
        worker.signals.result.connect(self.blocklist_get_blocklist_Button_done)
        self.threadpool.start(worker)

    def blocklist_get_blocklist_Button_progress(self, blocklist):
        row_count = self.blocklist_api_Table.rowCount()
        self.blocklist_api_Table.setRowCount(row_count + len(blocklist))
        for row, line in enumerate(blocklist.items()):
            for col, entry in enumerate(line):
                self.blocklist_api_Table.setItem(row + row_count, col, QTableWidgetItem(QIcon(), str(entry)))

    def blocklist_get_blocklist_Button_done(self):
        self.remove_status("Grabbing blocklist, please wait")
        self.blocklist_get_blocklist_Button.setEnabled(True)
        self.blocklist_clean_blocklist_Button.setEnabled(True)

    def blocklist_clean_blocklist_button_callback(self):
        self.add_status("Cleaning Blocklist")
        self.blocklist_clean_blocklist_Button.setEnabled(False)
        self.blocklist_get_blocklist_Button.setEnabled(False)
        blocklist = []
        for i in range(self.blocklist_api_Table.rowCount()):
            item = self.blocklist_api_Table.item(i, 1)
            if item:
                user_id = item.text()
                if user_id:
                    blocklist.append(user_id)
        worker = Worker(self.api.ids_to_names, blocklist)
        worker.signals.progress.connect(self.set_progress_label)
        worker.signals.result.connect(self.blocklist_clean_blocklist_button_usernames_grabbed)
        self.threadpool.start(worker)

    def blocklist_clean_blocklist_button_usernames_grabbed(self, names_by_id):
        blocklist = []
        for i in range(self.blocklist_api_Table.rowCount()):
            item = self.blocklist_api_Table.item(i, 1)
            if item:
                user_id = item.text()
                if user_id:
                    blocklist.append(user_id)
        user_ids = names_by_id.keys()
        self.blocklist_api_Table.clearContents()
        self.blocklist_api_Table.setRowCount(len(names_by_id))
        for row, item in enumerate(names_by_id.items()):
            self.blocklist_api_Table.setItem(row, 0, QTableWidgetItem(item[1]))
            self.blocklist_api_Table.setItem(row, 1, QTableWidgetItem(item[0]))
        users_to_unblock = [_id for _id in blocklist if _id not in user_ids]
        worker = Worker(self.api.unblock_users, users_to_unblock)
        worker.signals.progress.connect(self.set_progress_label)
        worker.signals.result.connect(self.blocklist_clean_blocklist_button_done)
        self.threadpool.start(worker)

    def blocklist_clean_blocklist_button_done(self):
        self.remove_status("Cleaning Blocklist")
        self.blocklist_clean_blocklist_Button.setEnabled(True)
        self.blocklist_get_blocklist_Button.setEnabled(True)

    # </editor-fold>

    # <editor-fold desc="Banlist tab">
    def init_banlist_info(self, parent):
        # Create Widgets
        self.banlist_get_banlist_Button = QPushButton("Get Banlist")
        self.banlist_export_namelist_Button = QPushButton("Export Bans as Namelist")
        self.banlist_import_namelist_Button = QPushButton("Import Names from Namelist")
        self.banlist_ban_imported_names_Button = QPushButton("Ban imported Names")
        self.banlist_info_Table = QTableWidget()
        self.banlist_info_Table.setColumnCount(3)
        self.banlist_info_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User Name"))
        self.banlist_info_Table.setHorizontalHeaderItem(1, QTableWidgetItem("User ID"))
        self.banlist_info_Table.setHorizontalHeaderItem(2, QTableWidgetItem("Expires At"))
        self.banlist_import_ListWidget = QListWidget()
        self.banlist_clean_banlist_Button = QPushButton("Clean Banlist")
        self.banlist_clean_importedlist_Button = QPushButton("Clean Imported Banlist")
        self.banlist_export_imported_banlist_Button = QPushButton("Export Imported Banlist")
        self.filter_affiliate_checkbox = QCheckBox("Remove Affiliates")
        self.filter_affiliate_checkbox.setChecked(True)
        self.filter_partner_checkbox = QCheckBox("Remove Partners")
        self.filter_partner_checkbox.setChecked(True)

        # Create layout and add widgets
        api_side_button_row_top = QHBoxLayout()
        api_side_button_row_top.addWidget(self.banlist_get_banlist_Button)
        api_side_button_row_top.addWidget(self.banlist_export_namelist_Button)
        api_side_button_row_top.addWidget(self.banlist_clean_banlist_Button)

        import_side_button_row_top = QHBoxLayout()
        import_side_button_row_top.addWidget(self.banlist_import_namelist_Button)
        import_side_button_row_top.addWidget(self.banlist_ban_imported_names_Button)
        import_side_button_row_top.addWidget(self.banlist_clean_importedlist_Button)
        import_side_button_row_top.addWidget(self.banlist_export_imported_banlist_Button)

        api_side_button_row_bottom = QHBoxLayout()

        import_side_button_row_bottom = QHBoxLayout()
        import_side_button_row_bottom.addWidget(self.filter_affiliate_checkbox)
        import_side_button_row_bottom.addWidget(self.filter_partner_checkbox)


        table_row = QHBoxLayout()
        table_row.addWidget(self.banlist_info_Table)
        table_row.addWidget(self.banlist_import_ListWidget)

        button_rows = QGridLayout()
        button_rows.addLayout(api_side_button_row_top, 0, 0)
        button_rows.addLayout(import_side_button_row_top, 0, 1)
        button_rows.addLayout(api_side_button_row_bottom, 1, 0)
        button_rows.addLayout(import_side_button_row_bottom, 1, 1)

        layout = QVBoxLayout()
        layout.addLayout(button_rows)
        layout.addLayout(table_row)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.banlist_get_banlist_Button.clicked.connect(self.banlist_get_banlist_Button_action)
        self.banlist_export_namelist_Button.clicked.connect(self.banlist_export_namelist_callback)
        self.banlist_import_namelist_Button.clicked.connect(self.banlist_import_namelist_callback)
        self.banlist_ban_imported_names_Button.clicked.connect(self.banlist_ban_imported_names_callback)
        self.banlist_clean_banlist_Button.clicked.connect(self.banlist_clean_banlist_Button_callback)
        self.banlist_clean_importedlist_Button.clicked.connect(self.banlist_clean_imported_banlist_callback)
        self.banlist_export_imported_banlist_Button.clicked.connect(self.banlist_export_imported_banlist_callback)

    def banlist_export_imported_banlist_callback(self):
        file_to_write = QFileDialog.getSaveFileName(caption="Select file to export to", dir="")
        if file_to_write[0]:
            with open(file_to_write[0], "w") as f:
                for i in range(self.banlist_import_ListWidget.count()):
                    f.write(f"{self.banlist_import_ListWidget.item(i).text()}\n")

    def banlist_clean_imported_banlist_callback(self):
        self.add_status("Cleaning imported Banlist")
        self.banlist_clean_importedlist_Button.setEnabled(False)
        banlist = []
        for i in range(self.banlist_import_ListWidget.count()):
            item = self.banlist_import_ListWidget.item(i)
            if item:
                user_name = item.text()
                if user_name and "+" not in user_name:
                    banlist.append(user_name)

        _filter = [self.api.FILTER_STAFF]
        if self.filter_partner_checkbox.isChecked():
            _filter.append(self.api.FILTER_PARTNER)
        if self.filter_affiliate_checkbox.isChecked():
            _filter.append(self.api.FILTER_AFFILIATE)
        worker = Worker(self.api.get_valid_users, banlist, name_filter=_filter)
        worker.signals.progress.connect(self.set_progress_label)
        worker.signals.result.connect(self.banlist_clean_imported_banlist_names_validated)
        self.threadpool.start(worker)

    def banlist_clean_imported_banlist_names_validated(self, namelist):
        self.banlist_import_ListWidget.clear()
        nameset = set(namelist)
        for name in sorted(nameset):
            self.banlist_import_ListWidget.addItem(name)
        self.banlist_clean_importedlist_Button.setEnabled(True)
        self.banlist_import_ListWidget.sortItems(Qt.AscendingOrder)
        self.remove_status("Cleaning imported Banlist")

    def banlist_clean_banlist_Button_callback(self):
        self.add_status("Cleaning Banlist")
        self.banlist_clean_banlist_Button.setEnabled(False)
        banlist = []
        for i in range(self.banlist_info_Table.rowCount()):
            item = self.banlist_info_Table.item(i, 1)
            if item:
                user_id = item.text()
                if user_id:
                    banlist.append(user_id)
        worker = Worker(self.api.ids_to_names, banlist)
        worker.signals.progress.connect(self.set_progress_label)
        worker.signals.result.connect(self.banlist_clean_banlist_Button_usernames_grabbed)
        self.threadpool.start(worker)

    def banlist_clean_banlist_Button_usernames_grabbed(self, names_by_id):
        banlist = []
        for i in range(self.banlist_info_Table.rowCount()):
            item = self.banlist_info_Table.item(i, 0)
            if item:
                user_name = item.text()
                if user_name:
                    banlist.append(user_name)
        user_names = names_by_id.values()
        self.banlist_info_Table.clearContents()
        self.banlist_info_Table.setRowCount(len(names_by_id))
        for row, item in enumerate(names_by_id.items()):
            self.banlist_info_Table.setItem(row, 0, QTableWidgetItem(item[1]))
            self.banlist_info_Table.setItem(row, 1, QTableWidgetItem(item[0]))
        users_to_unban = [name for name in banlist if name not in user_names]
        worker = Worker(self.api.bot.unban_namelist, self.api.login, users_to_unban)
        worker.signals.progress.connect(self.set_progress_label)
        worker.signals.result.connect(self.banlist_clean_blocklist_button_done)
        self.threadpool.start(worker)

    def banlist_clean_blocklist_button_done(self):
        self.remove_status("Cleaning Banlist")
        self.banlist_clean_banlist_Button.setEnabled(True)

    def banlist_ban_imported_names_callback(self):
        banned_names = []
        row_count = self.banlist_info_Table.rowCount()
        for i in range(row_count):
            _item = self.banlist_info_Table.item(i, 0)
            _name = _item.text()
            if _name:
                banned_names.append(_name)
        banned_names.sort()
        namelist = []
        row_count = self.banlist_import_ListWidget.count()
        for i in range(row_count):
            _item = self.banlist_import_ListWidget.item(i)
            _name = _item.text()
            if _name and _name not in banned_names:
                namelist.append(_name)
        namelist.sort()
        worker = Worker(self.api.bot.ban_namelist, self.api.login, namelist)
        worker.signals.progress.connect(self.set_progress_label)
        self.threadpool.start(worker)

    def banlist_import_namelist_callback(self):
        files_to_read = QFileDialog.getOpenFileNames(caption="Select files to import", dir="", filter="Text files (*.txt)")
        for file_path in files_to_read[0]:
            with open(file_path, "r", encoding="utf-8") as file:
                for line in file.readlines():
                    name = line.strip()
                    if name:
                        self.banlist_import_ListWidget.addItem(name)

    def banlist_export_namelist_callback(self):
        file = QFileDialog.getSaveFileName(caption="Select file to export to", dir="")[0]
        if file:
            name_list = []
            rowcount = self.banlist_info_Table.rowCount()
            for i in range(rowcount):
                name = self.banlist_info_Table.item(i, 0)
                name_list.append(name.text())
            name_list.sort()
            with open(file, "w") as name_file:
                for name in name_list:
                    name_file.write(f"{name}\n")

    def banlist_get_banlist_Button_action(self):
        self.banlist_get_banlist_Button.setEnabled(False)
        self.add_status("Grabbing banlist, please wait")
        self.banlist_info_Table.clearContents()
        self.banlist_info_Table.setRowCount(0)
        worker = Worker(self.api.get_banned_users)
        worker.signals.progress.connect(self.banlist_get_banlist_Button_progress)
        worker.signals.result.connect(self.banlist_get_banlist_Button_done)
        self.threadpool.start(worker)

    def banlist_get_banlist_Button_progress(self, banlist):
        row_count = self.banlist_info_Table.rowCount()
        self.banlist_info_Table.setRowCount(row_count + len(banlist))
        for row, line in enumerate(banlist):
            for col, entry in enumerate(line):
                self.banlist_info_Table.setItem(row + row_count, col, QTableWidgetItem(QIcon(), str(entry)))

    def banlist_get_banlist_Button_done(self):
        self.banlist_info_Table.sortByColumn(0, Qt.AscendingOrder)
        self.remove_status("Grabbing banlist, please wait")
        self.banlist_get_banlist_Button.setEnabled(True)

    # </editor-fold>

    # <editor-fold desc="Mod actions tab">
    def init_mod_actions_tab(self, parent):
        # Create Widgets
        self.modactions_export_all_Button = QPushButton("Export All")
        self.modactions_export_bans_Button = QPushButton("Export Bans")
        self.modactions_auto_export_all_checkbox = QCheckBox("Auto Export All")
        self.modactions_auto_export_bans_checkbox = QCheckBox("Auto Export Bans")
        self.modactions_ids_to_names_Button = QPushButton("Convert ID's to names")
        self.modactions_import_button = QPushButton("Import from file")
        self.mod_actions_Table = QTableWidget()
        self.mod_actions_Table.setColumnCount(6)
        self.mod_actions_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User"))
        self.mod_actions_Table.setHorizontalHeaderItem(1, QTableWidgetItem("UserID"))
        self.mod_actions_Table.setHorizontalHeaderItem(2, QTableWidgetItem("Action"))
        self.mod_actions_Table.setHorizontalHeaderItem(3, QTableWidgetItem("Moderator"))
        self.mod_actions_Table.setHorizontalHeaderItem(4, QTableWidgetItem("Timestamp"))
        self.mod_actions_Table.setHorizontalHeaderItem(5, QTableWidgetItem("Info"))

        # Create layout and add widgets
        button_row_layout = QHBoxLayout()
        button_row_layout.addWidget(self.modactions_export_all_Button)
        button_row_layout.addWidget(self.modactions_export_bans_Button)
        button_row_layout.addWidget(self.modactions_auto_export_all_checkbox)
        button_row_layout.addWidget(self.modactions_auto_export_bans_checkbox)
        button_row_layout.addWidget(self.modactions_ids_to_names_Button)
        button_row_layout.addWidget(self.modactions_import_button)

        layout = QVBoxLayout()
        layout.addLayout(button_row_layout)
        layout.addWidget(self.mod_actions_Table)

        # Set dialog layout
        parent.setLayout(layout)

        self.modactions_export_all_Button.clicked.connect(self.export_all_modactions)
        self.modactions_export_bans_Button.clicked.connect(self.export_bans)
        self.modactions_auto_export_bans_checkbox.stateChanged.connect(self.checkbox_event)
        self.modactions_ids_to_names_Button.clicked.connect(self.modactions_ids_to_names_callback)
        self.modactions_import_button.clicked.connect(self.modactions_import_callback)

    def modactions_import_callback(self):
        files_to_read = QFileDialog.getOpenFileNames(caption="Select files to import", dir="", filter="Text files (*.txt)")
        for file_path in files_to_read[0]:
            with open(file_path, "r", encoding="utf-8") as file:
                file_string = file.read()
            action_list = modactions_seperate_file_to_individual_actions_regex.findall(file_string)
            for action in action_list:
                action_parts = [action_part.strip() for action_part in action.split("\n") if action_part]
                if "Banned by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("ban"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Timed out by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = modactions_get_mod_in_timeout_string_regex.search(action_parts[1]).group(1)
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("timeout"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Raid Started by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Started Raid"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif action_parts[0] == "Followers-Only Chat":
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    _status = action_parts[1].split(" ", 1)[0]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Follower only Chat"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                    self.mod_actions_Table.setItem(0, 5, QTableWidgetItem(_status))
                elif "Added as a VIP by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Added as VIP"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Added as a Moderator by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Added as a Moderator"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Hosting Started by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Hosting Started"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Hosting Ended by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Hosting Ended"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Message Deleted by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Message deleted"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                    self.mod_actions_Table.setItem(0, 5, QTableWidgetItem(action_parts[2]))
                elif "Removed Timeout by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Removed Timeout"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Added as Permitted Term by" in action_parts[1]:
                    _moderator = modactions_get_mod_in_permitted_term_string_regex.search(action_parts[1]).group(1)
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Added Permitted Term"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                    self.mod_actions_Table.setItem(0, 5, QTableWidgetItem(action_parts[0]))
                elif "Unban request denied by" in action_parts[1]:
                    _name = action_parts[0]
                    _moderator = action_parts[1].rsplit(" ", 1)[1]
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 0, QTableWidgetItem(_name))
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Denied Unban request"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                elif "Added as Blocked Term by" in action_parts[1]:
                    _moderator = modactions_get_mod_in_blocked_term_string_regex.search(action_parts[1]).group(1)
                    self.mod_actions_Table.insertRow(0)
                    self.mod_actions_Table.setItem(0, 2, QTableWidgetItem("Added Blocked Term"))
                    self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(_moderator))
                    self.mod_actions_Table.setItem(0, 5, QTableWidgetItem(action_parts[0]))
                else:
                    print(action_parts)
        self.mod_actions_Table.resizeColumnsToContents()

    def modactions_ids_to_names_callback(self):
        rowcount = self.mod_actions_Table.rowCount()
        ids = []
        for i in range(rowcount):
            _item = self.mod_actions_Table.item(i, 1)
            if _item:
                _text = _item.text()
                if _text:
                    ids.append(_text)
        if ids:
            name_dict = self.api.ids_to_names(ids)
            for i in range(self.mod_actions_Table.rowCount()):
                _item = self.mod_actions_Table.item(i, 1)
                if _item:
                    _text = _item.text()
                    if _text and _text in name_dict.keys():
                        self.mod_actions_Table.setItem(i, 0, QTableWidgetItem(name_dict[_text]))
            self.mod_actions_Table.resizeColumnsToContents()

    def pubsub_mod_action_handler(self, response):
        uuid, action = response
        data = action["data"]
        self.mod_actions_Table.insertRow(0)
        if data["moderation_action"] in ("ban", "unban"):
            self.mod_actions_Table.setItem(0, 1, QTableWidgetItem(str(data["target_user_id"])))
        else:
            self.mod_actions_Table.setItem(0, 1, QTableWidgetItem(""))
        self.mod_actions_Table.setItem(0, 2, QTableWidgetItem(data["moderation_action"]))
        self.mod_actions_Table.setItem(0, 3, QTableWidgetItem(data["created_by"]))
        self.mod_actions_Table.setItem(0, 4, QTableWidgetItem(str(data["created_at"])))
        if data["moderation_action"] == "ban":
            if len(data["args"]) > 1:
                self.mod_actions_Table.setItem(0, 5, QTableWidgetItem(str(data["args"][1])))
        self.mod_actions_Table.resizeColumnsToContents()

    def checkbox_event(self, *args, **kwargs):
        print("checked")
        print(args, kwargs)

    def export_all_modactions(self):
        self.modactions_ids_to_names_callback()
        row_count = self.mod_actions_Table.rowCount()
        column_count = self.mod_actions_Table.columnCount()
        lines = []
        for i in range(row_count):
            row = []
            for j in range(column_count):
                _item = self.mod_actions_Table.item(i, j)
                if _item:
                    row.append(_item.text())
                else:
                    row.append("")
            lines.append(row)
        csv_lines = [",".join(line) for line in lines]
        csv_string = "\n".join(csv_lines)

        output_filepath = f'{self.settings["Export Directory"]}Modactions_all_{datetime.date.today()}.csv'
        if not os.path.isdir(self.settings["Export Directory"]):
            os.mkdir(self.settings["Export Directory"])
        if os.path.isfile(output_filepath):
            with open(output_filepath, "r") as output_file:
                old_lines = [line.strip() for line in output_file.readlines()]
                for line in csv_lines.copy():
                    if line in old_lines:
                        csv_lines.remove(line)
            if csv_lines:
                with open(output_filepath, "a") as output_file:
                    output_file.write("\n".join(csv_lines))
                    output_file.write("\n")
        else:
            with open(output_filepath, "x") as output_file:
                output_file.write("User,userID,Action,Moderator,Timestamp,Reason\n")
                if csv_string:
                    output_file.write(csv_string)
                    output_file.write("\n")

    def export_bans(self):
        self.modactions_ids_to_names_callback()
        row_count = self.mod_actions_Table.rowCount()
        column_count = self.mod_actions_Table.columnCount()
        lines = []
        for i in range(row_count):
            row = []
            for j in range(column_count):
                _item = self.mod_actions_Table.item(i, j)
                if _item:
                    row.append(_item.text())
                else:
                    row.append("")
            lines.append(row)

        ban_events = {}
        unban_events = {}
        for line in lines:
            if line[1] == "ban":
                ban_events[line[0]] = line[1:]
            elif line[1] == "unban":
                unban_events[line[0]] = line[1:]

        for name, data in unban_events.items():
            if name in ban_events.keys():
                if data[2] > ban_events[name][2]:
                    ban_events.pop(name)

        filtered_lines = []
        for name, data in ban_events.items():
            filtered_lines.append([name, *data])
        filtered_lines.sort(key=lambda x: x[3])  # sort by time

        csv_lines = [",".join(line) for line in filtered_lines]
        csv_string = "\n".join(csv_lines)

        output_filepath = f'{self.settings["Export Directory"]}Modactions_bans_{datetime.date.today()}.csv'
        if not os.path.isdir(self.settings["Export Directory"]):
            os.mkdir(self.settings["Export Directory"])
        if os.path.isfile(output_filepath):
            with open(output_filepath, "r") as output_file:
                old_lines = [line.strip() for line in output_file.readlines()]
                for line in csv_lines.copy():
                    if line in old_lines:
                        csv_lines.remove(line)
            if csv_lines:
                with open(output_filepath, "a") as output_file:
                    output_file.write("\n".join(csv_lines))
                    output_file.write("\n")
        else:
            with open(output_filepath, "x") as output_file:
                output_file.write("User,userID,Action,Moderator,Timestamp,Reason\n")
                if csv_string:
                    output_file.write(csv_string)
                    output_file.write("\n")

    # </editor-fold>

    # <editor-fold desc="Chat tab">
    def init_chat_tab(self, parent):
        # Create Widgets
        for chnl in self.api.credentials["bot channels"]:
            # print(chnl)
            table = QTableWidget()
            table.setRowCount(500)
            table.setColumnCount(2)
            table.setHorizontalHeaderItem(0, QTableWidgetItem("Username"))
            table.setHorizontalHeaderItem(1, QTableWidgetItem("Message"))
            table.horizontalHeader().setStretchLastSection(True)
            self.chat_widgets[chnl] = table

        chat_tabs = QTabWidget()

        for chnl in self.chat_widgets:
            chat_tabs.addTab(self.chat_widgets[chnl], chnl)

        filter_widget = QWidget()
        filter_layout = QVBoxLayout()
        filter_buttonrow_layout = QHBoxLayout()

        self.filter_new_filter_button = QPushButton("Add Filter")
        self.save_filters_button = QPushButton("Save Filters")

        self.filter_table = QTableWidget()
        self.filter_table.setColumnCount(5)

        filter_buttonrow_layout.addWidget(self.filter_new_filter_button)
        filter_buttonrow_layout.addWidget(self.save_filters_button)
        filter_layout.addLayout(filter_buttonrow_layout)
        filter_layout.addWidget(self.filter_table)
        filter_widget.setLayout(filter_layout)
        chat_tabs.addTab(filter_widget, "filter")

        layout = QVBoxLayout()
        layout.addWidget(chat_tabs)
        parent.setLayout(layout)

        self.filter_new_filter_button.clicked.connect(self.add_filter)
        self.save_filters_button.clicked.connect(self.save_filters)

    def add_filter(self, filter_text: str = "", filter_type: str = Filter.FILTER_TYPES[0], filter_target: str = Filter.FILTER_TARGETS[0], filter_penality: str = Filter.FILTER_PENALITYS[0]):
        idx = self.filter_table.rowCount()
        filter_text_lineedit = QLineEdit()
        filter_text_lineedit.setText(filter_text)

        filter_type_combobox = QComboBox()
        filter_type_combobox.addItems(Filter.FILTER_TYPES)
        filter_type_combobox.setCurrentText(filter_type)
        filter_type_combobox.setEditable(False)

        filter_target_combobox = QComboBox()
        filter_target_combobox.addItems(Filter.FILTER_TARGETS)
        filter_target_combobox.setCurrentText(filter_target)
        filter_target_combobox.setEditable(False)

        filter_penalty_combobox = QComboBox()
        filter_penalty_combobox.addItems(Filter.FILTER_PENALITYS)
        filter_penalty_combobox.setCurrentText(filter_penality)
        filter_penalty_combobox.setEditable(False)

        del_btn = QPushButton("Delete filter")
        del_btn.clicked.connect(partial(self._filter_remove_callback, idx))
        self.filter_table.insertRow(idx)
        self.filter_table.setCellWidget(idx, 0, filter_text_lineedit)
        self.filter_table.setCellWidget(idx, 1, filter_type_combobox)
        self.filter_table.setCellWidget(idx, 2, filter_target_combobox)
        self.filter_table.setCellWidget(idx, 3, filter_penalty_combobox)
        self.filter_table.setCellWidget(idx, 4, del_btn)
        self.filter_table.resizeColumnsToContents()

    def _filter_remove_callback(self, row):
        self.filter_table.removeRow(row)
        for i in range(self.filter_table.rowCount()):
            self.filter_table.cellWidget(i, 4).clicked.disconnect()
            self.filter_table.cellWidget(i, 4).clicked.connect(partial(self._filter_remove_callback, i))

    def reload_filters(self):
        self.filter_list.clear()
        for i in range(self.filter_table.rowCount()):
            _line_edit: QLineEdit = self.filter_table.cellWidget(i, 0)
            if _line_edit:
                filter_text = _line_edit.text().strip()
                filter_mode_combobox: QComboBox = self.filter_table.cellWidget(i, 1)
                if filter_mode_combobox and filter_text:
                    selected_filter_mode = filter_mode_combobox.currentText()
                    target_combobox: QComboBox = self.filter_table.cellWidget(i, 2)
                    if target_combobox:
                        target = target_combobox.currentText()
                        penality_combobox: QComboBox = self.filter_table.cellWidget(i, 3)
                        if penality_combobox:
                            penality = penality_combobox.currentText()
                            f = Filter(filter_text, selected_filter_mode, target, penality)
                    self.filter_list.append(f)

    def save_filters(self):
        self.reload_filters()
        if not os.path.exists("data"):
            os.mkdir("data")
        with open("data/chat_filters.pickle", "wb") as file:
            pickle.dump(self.filter_list, file, )

    def load_filters(self):
        if not os.path.isfile("data/chat_filters.pickle"):
            print("No filter file")
        else:
            with open("data/chat_filters.pickle", "rb") as file:
                self.filter_list = pickle.load(file)
            for fltr in self.filter_list:
                fltr: Filter
                self.add_filter(filter_text=fltr.filter_str, filter_target=fltr.target, filter_type=fltr.filter_type, filter_penality=fltr.penality)

    # </editor-fold>

    # <editor-fold desc="Settings tab">
    def init_settings_tab(self, parent):
        # Create Widgets
        int_validator = QtGui.QIntValidator()
        self.settings_apply_button = QPushButton("Apply")
        self.settings_window_width_LineEdit = QLineEdit(str(self.settings["Window Size"][0]))
        self.settings_window_width_LineEdit.setValidator(int_validator)
        self.settings_window_height_LineEdit = QLineEdit(str(self.settings["Window Size"][1]))
        self.settings_window_height_LineEdit.setValidator(int_validator)
        self.settings_export_dir_lineEdit = QLineEdit(str(self.settings["Export Directory"]))
        self.credentials_channels_to_join_LineEdit = QLineEdit(", ".join(self.api.credentials["bot channels"]))

        # Create layout and add widgets
        layout = QFormLayout()
        layout.addRow(self.settings_apply_button)
        layout.addRow("Window width", self.settings_window_width_LineEdit)
        layout.addRow("Window height", self.settings_window_height_LineEdit)
        layout.addRow("Export Directory", self.settings_export_dir_lineEdit)
        layout.addRow("Mod Action Channels", self.credentials_channels_to_join_LineEdit)

        # Set dialog layout
        parent.setLayout(layout)

        self.settings_apply_button.clicked.connect(self.settings_apply_callback)

    def settings_apply_callback(self):
        changed = False
        self.settings["Window Size"] = [int(self.settings_window_width_LineEdit.text()), int(self.settings_window_height_LineEdit.text())]

        if not (self.settings == self.old_settings):
            with open("settings.json", "w") as settings_file:
                json.dump(self.settings, settings_file, indent="  ")
            changed = True

        if not ", ".join(self.api.credentials["bot channels"]) == self.credentials_channels_to_join_LineEdit.text():
            with open("credentials.json", "r") as credentials_file:
                _credentials = json.load(credentials_file)
                _credentials["bot channels"] = [channel.strip() for channel in self.credentials_channels_to_join_LineEdit.text().split(",")]
            with open("credentials.json", "w") as credentials_file:
                json.dump(_credentials, credentials_file, indent="  ")
            self.api.load_credentials()
            changed = True

        if changed:
            print("Settings saved")
    # </editor-fold>
