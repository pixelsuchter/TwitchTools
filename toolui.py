import datetime
import json
import os.path
import random
import sys
import threading
import time
import traceback
from threading import Thread

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Slot, QRunnable, Signal, QObject, QThreadPool
from PySide6.QtGui import Qt, QIcon
from PySide6.QtWidgets import *

import twitchapi


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
        self.run_bot = [True]
        self.old_settings = settings.copy()
        self.settings = settings

        self.status_list = ["Idle"]

        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

        self.tool_tab_widget = QtWidgets.QTabWidget()
        self.following_tab = QtWidgets.QWidget()
        self.user_info_tab = QtWidgets.QWidget()
        self.blocklist_info_tab = QtWidgets.QTabWidget()
        self.banlist_info_tab = QtWidgets.QTabWidget()
        self.mod_actions_tab = QtWidgets.QTabWidget()
        self.settings_tab = QtWidgets.QTabWidget()

        self.tool_tab_widget.addTab(self.following_tab, "Following")
        self.tool_tab_widget.addTab(self.user_info_tab, "User Info")
        self.tool_tab_widget.addTab(self.blocklist_info_tab, "Blocklist Info")
        self.tool_tab_widget.addTab(self.banlist_info_tab, "Banlist Info")
        self.tool_tab_widget.addTab(self.mod_actions_tab, "Moderator Actions")
        self.tool_tab_widget.addTab(self.settings_tab, "Settings")

        self.tool_tab_widget.currentChanged.connect(self.tab_clicked)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("")

        layout = QVBoxLayout()
        layout.addWidget(self.tool_tab_widget)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.api = twitchapi.Twitch_api()
        self.bot_worker = Worker(self.api.bot.run, run_flag=self.run_bot)
        self.bot_worker.signals.progress.connect(self.print_output)
        self.threadpool.start(self.bot_worker)

        self.pubsub_worker = Worker(self.api.init_pubsub)
        self.pubsub_worker.signals.progress.connect(self.pubsub_mod_action_handler)
        self.threadpool.start(self.pubsub_worker)

        self.init_follow_grabber(self.following_tab)
        self.init_user_info(self.user_info_tab)
        self.init_blocklist_info(self.blocklist_info_tab)
        self.init_banlist_info(self.banlist_info_tab)
        self.init_mod_actions_tab(self.mod_actions_tab)
        self.init_settings_tab(self.settings_tab)

    def tab_clicked(self):
        if self.tool_tab_widget.currentWidget() is self.settings_tab:
            # Update settings
            self.settings["Window Size"] = [self.size().width(), self.size().height()]
            self.settings["Maximized"] = self.isMaximized()

            # Update labels
            self.settings_window_width_LineEdit.setText(str(self.settings["Window Size"][0]))
            self.settings_window_height_LineEdit.setText(str(self.settings["Window Size"][1]))

    def print_output(self, s):
        # print(s)
        pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not (self.settings == self.old_settings):
            with open("settings.json", "w") as settings_file:
                json.dump(self.settings, settings_file, indent="  ")
                print("Settings saved")
        self.run_bot.remove(True)
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
        self.follow_grabber_getFollows_Button = QPushButton("Get Follows")
        self.follow_grabber_follow_Table = QTableWidget()
        self.follow_grabber_follow_Table.setColumnCount(2)
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(0, QTableWidgetItem("Name"))
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(1, QTableWidgetItem("Time of follow"))
        self.follow_grabber_follow_Table.resizeColumnsToContents()
        self.follow_grabber_followList_SortingBox = QComboBox()
        self.follow_grabber_followList_SortingBox.addItems(
            ["Name A-Z", "Name Z-A", "Follow time New-Old", "Follow time Old-New"])

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.follow_grabber_username_LineEdit)
        layout.addWidget(self.follow_grabber_getFollows_Button)
        layout.addWidget(self.follow_grabber_followList_SortingBox)
        layout.addWidget(self.follow_grabber_follow_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.follow_grabber_getFollows_Button.clicked.connect(self.follow_grabber_get_follows_button_action)
        self.follow_grabber_followList_SortingBox.currentTextChanged.connect(
            self.follow_grabber_follow_list_sorting_box_action)
        self.follow_grabber_follow_Table.doubleClicked.connect(self.follow_grabber_follow_table_action)

    def print_output(self, s):
        print(s)

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
    def follow_grabber_get_follows_button_action(self):
        self.follow_grabber_getFollows_Button.setEnabled(False)
        self.add_status("Getting followers, please wait")
        self.follow_grabber_follow_Table.clearContents()
        self.follow_grabber_follow_Table.setRowCount(0)
        name = self.follow_grabber_username_LineEdit.text()
        if name:
            user_id = self.api.names_to_id(name)[0]
            if user_id:
                worker = Worker(self.api.get_all_followed_channel_names, user_id)
                worker.signals.progress.connect(self.follow_grabber_get_follows_button_thread_return)
                worker.signals.result.connect(self.follow_grabber_get_follows_button_thread_done)
                self.threadpool.start(worker)
        else:
            self.follow_grabber_get_follows_button_thread_done()

    def follow_grabber_get_follows_button_thread_return(self, follows):
        row_count = self.follow_grabber_follow_Table.rowCount()
        self.follow_grabber_follow_Table.setRowCount(row_count + len(follows))
        for row, line in enumerate(follows.items()):
            for col, entry in enumerate(line):
                self.follow_grabber_follow_Table.setItem(row + row_count, col, QTableWidgetItem(QIcon(), str(entry)))

    def follow_grabber_get_follows_button_thread_done(self):
        self.follow_grabber_follow_list_sorting_box_action()  # Update sorting
        self.follow_grabber_follow_Table.resizeColumnsToContents()
        self.remove_status("Getting followers, please wait")
        self.follow_grabber_getFollows_Button.setEnabled(True)

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
            self.user_info_info_Table.setRowCount(len(user_info))
            for row, line in enumerate(user_info.items()):
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
        self.blocklist_info_Table = QTableWidget()
        self.blocklist_info_Table.setColumnCount(2)
        self.blocklist_info_Table.setHorizontalHeaderItem(0, QTableWidgetItem(" "))
        self.blocklist_info_Table.setHorizontalHeaderItem(1, QTableWidgetItem(" "))

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.blocklist_get_blocklist_Button)
        layout.addWidget(self.blocklist_info_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.blocklist_get_blocklist_Button.clicked.connect(self.blocklist_get_blocklist_Button_action)

    def blocklist_get_blocklist_Button_action(self):
        self.blocklist_get_blocklist_Button.setEnabled(False)
        self.add_status("Grabbing blocklist, please wait")
        self.blocklist_info_Table.clearContents()
        self.blocklist_info_Table.setRowCount(0)
        worker = Worker(self.api.get_all_blocked_users)
        worker.signals.progress.connect(self.blocklist_get_blocklist_Button_progress)
        worker.signals.result.connect(self.blocklist_get_blocklist_Button_done)
        self.threadpool.start(worker)

    def blocklist_get_blocklist_Button_progress(self, blocklist):
        row_count = self.blocklist_info_Table.rowCount()
        self.blocklist_info_Table.setRowCount(row_count + len(blocklist))
        for row, line in enumerate(blocklist.items()):
            for col, entry in enumerate(line):
                self.blocklist_info_Table.setItem(row + row_count, col, QTableWidgetItem(QIcon(), str(entry)))

    def blocklist_get_blocklist_Button_done(self):
        self.remove_status("Grabbing blocklist, please wait")
        self.blocklist_get_blocklist_Button.setEnabled(True)

    # </editor-fold>

    # <editor-fold desc="Banlist tab">
    def init_banlist_info(self, parent):
        # Create Widgets
        self.banlist_get_banlist_Button = QPushButton("Get Banlist")
        self.banlist_info_Table = QTableWidget()
        self.banlist_info_Table.setColumnCount(3)
        self.banlist_info_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User Name"))
        self.banlist_info_Table.setHorizontalHeaderItem(1, QTableWidgetItem("User ID"))
        self.banlist_info_Table.setHorizontalHeaderItem(2, QTableWidgetItem("Expires At"))

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.banlist_get_banlist_Button)
        layout.addWidget(self.banlist_info_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.banlist_get_banlist_Button.clicked.connect(self.banlist_get_banlist_Button_action)

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
        self.mod_actions_ids_to_names_Button = QPushButton("Convert ID's to names")
        self.mod_actions_Table = QTableWidget()
        self.mod_actions_Table.setColumnCount(6)
        self.mod_actions_Table.setHorizontalHeaderItem(0, QTableWidgetItem("User"))
        self.mod_actions_Table.setHorizontalHeaderItem(1, QTableWidgetItem("UserID"))
        self.mod_actions_Table.setHorizontalHeaderItem(2, QTableWidgetItem("Action"))
        self.mod_actions_Table.setHorizontalHeaderItem(3, QTableWidgetItem("Moderator"))
        self.mod_actions_Table.setHorizontalHeaderItem(4, QTableWidgetItem("Timestamp"))
        self.mod_actions_Table.setHorizontalHeaderItem(5, QTableWidgetItem("Reason"))


        # Create layout and add widgets
        button_row_layout = QHBoxLayout()
        button_row_layout.addWidget(self.modactions_export_all_Button)
        button_row_layout.addWidget(self.modactions_export_bans_Button)
        button_row_layout.addWidget(self.modactions_auto_export_all_checkbox)
        button_row_layout.addWidget(self.modactions_auto_export_bans_checkbox)
        button_row_layout.addWidget(self.mod_actions_ids_to_names_Button)

        layout = QVBoxLayout()
        layout.addLayout(button_row_layout)
        layout.addWidget(self.mod_actions_Table)

        # Set dialog layout
        parent.setLayout(layout)

        self.modactions_export_all_Button.clicked.connect(self.export_all_modactions)
        self.modactions_export_bans_Button.clicked.connect(self.export_bans)
        self.modactions_auto_export_bans_checkbox.stateChanged.connect(self.checkbox_event)
        self.mod_actions_ids_to_names_Button.clicked.connect(self.mod_actions_ids_to_names_callback)

    def mod_actions_ids_to_names_callback(self):
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
        print(response)
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
        self.mod_actions_ids_to_names_callback()
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
        self.mod_actions_ids_to_names_callback()
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
