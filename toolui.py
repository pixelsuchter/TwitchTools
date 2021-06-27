import json
import random
import sys

from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtGui import Qt
from PySide6.QtWidgets import *

import twitchapi


class TwitchToolUi(QtWidgets.QWidget):
    def __init__(self, settings):
        super(TwitchToolUi, self).__init__()
        self.old_settings = settings.copy()
        self.settings = settings

        self.tool_tab_widget = QtWidgets.QTabWidget()
        self.following_tab = QtWidgets.QWidget()
        self.user_info_tab = QtWidgets.QWidget()
        self.blocklist_info_tab = QtWidgets.QTabWidget()

        self.tool_tab_widget.addTab(self.following_tab, "Following")
        self.tool_tab_widget.addTab(self.user_info_tab, "User Info")
        self.tool_tab_widget.addTab(self.blocklist_info_tab, "Blocklist Info")



        self.init_follow_grabber(self.following_tab)
        self.init_user_info(self.user_info_tab)
        self.init_blocklist_info(self.blocklist_info_tab)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setText("")

        layout = QVBoxLayout()
        layout.addWidget(self.tool_tab_widget)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

        self.api = twitchapi.Twitch_api()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.settings["Window Size"] = [self.size().width(), self.size().height()]
        self.settings["Maximized"] = self.isMaximized()

        if not (self.settings == self.old_settings):
            with open("settings.json", "w") as settings_file:
                json.dump(self.settings, settings_file, indent="  ")
                self.print_status("Settings saved")
                print("Settings saved")

    def print_status(self, status: str):
        self.status_label.setText(status)

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
            self.print_status("Error in follow grabber")

    def follow_grabber_get_follows_button_action(self):
        self.follow_grabber_follow_Table.clearContents()
        name = self.follow_grabber_username_LineEdit.text()
        if name:
            user_id = self.api.names_to_id(name)[0]
            if user_id:
                follows = self.api.get_all_followed_channel_names(user_id)
                self.follow_grabber_follow_Table.setRowCount(len(follows))
                for row, follow in enumerate(follows.items()):
                    self.follow_grabber_follow_Table.setItem(row, 0, QTableWidgetItem(follow[0]))
                    self.follow_grabber_follow_Table.setItem(row, 1, QTableWidgetItem(follow[1]))
                self.follow_grabber_follow_list_sorting_box_action()  # Update sorting
                self.follow_grabber_follow_Table.resizeColumnsToContents()
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
        self.user_info_info_Table.clearContents()
        name = self.user_info_username_LineEdit.text()
        if name:
            user_id = self.api.names_to_id(name)[0]
            if user_id:
                user_info = self.api.get_user_info(user_id)
                self.user_info_info_Table.setRowCount(len(user_info))
                for row, info in enumerate(user_info.items()):
                    self.user_info_info_Table.setItem(row, 0, QTableWidgetItem(info[0]))
                    self.user_info_info_Table.setItem(row, 1, QTableWidgetItem(str(info[1])))
                self.user_info_info_Table.resizeColumnsToContents()
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
        self.blocklist_info_Table.clearContents()
        self.api.get_all_blocked_users()
    # </editor-fold>
