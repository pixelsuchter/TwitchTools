import random
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import Qt
from PySide6.QtWidgets import *

import twitchapi


class TwitchToolUi(QtWidgets.QTabWidget):
    def __init__(self, parent=None):
        super(TwitchToolUi, self).__init__(parent)
        self.following_tab = QtWidgets.QWidget()
        self.user_info_tab = QtWidgets.QWidget()

        self.addTab(self.following_tab, "Following")
        self.addTab(self.user_info_tab, "User Info")

        self.init_follow_grabber(self.following_tab)
        self.init_user_info(self.user_info_tab)

        self.api = twitchapi.Twitch_api()


    # Follow Grabber
    def init_follow_grabber(self, parent):
        # Create widgets
        self.follow_grabber_username_LineEdit = QLineEdit("")
        self.follow_grabber_getFollows_Button = QPushButton("Get Follows")
        self.follow_grabber_follow_Table = QTableWidget()
        self.follow_grabber_follow_Table.setColumnCount(2)
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(0, QTableWidgetItem("Name"))
        self.follow_grabber_follow_Table.setHorizontalHeaderItem(1, QTableWidgetItem("Time of follow"))
        self.follow_grabber_followList_SortingBox = QComboBox()
        self.follow_grabber_followList_SortingBox.addItems(["Name A-Z", "Name Z-A", "Follow time New-Old", "Follow time Old-New"])

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.follow_grabber_username_LineEdit)
        layout.addWidget(self.follow_grabber_getFollows_Button)
        layout.addWidget(self.follow_grabber_followList_SortingBox)
        layout.addWidget(self.follow_grabber_follow_Table)

        # Set dialog layout
        parent.setLayout(layout)

        # Add actions
        self.follow_grabber_getFollows_Button.clicked.connect(self.follow_grabber_getFollows_Button_Action)
        self.follow_grabber_followList_SortingBox.currentTextChanged.connect(self.follow_grabber_followList_SortingBox_Action)

    def follow_grabber_followList_SortingBox_Action(self):
        if self.follow_grabber_followList_SortingBox.currentText() == "Name A-Z":
            self.follow_grabber_follow_Table.sortByColumn(0, Qt.AscendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Name Z-A":
            self.follow_grabber_follow_Table.sortByColumn(0, Qt.DescendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Follow time New-Old":
            self.follow_grabber_follow_Table.sortByColumn(1, Qt.DescendingOrder)
        elif self.follow_grabber_followList_SortingBox.currentText() == "Follow time Old-New":
            self.follow_grabber_follow_Table.sortByColumn(1, Qt.AscendingOrder)
        else:
            # todo error display
            pass

    def follow_grabber_getFollows_Button_Action(self):
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
                self.follow_grabber_followList_SortingBox_Action()  # Update sorting

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
        self.user_info_getInfo_Button.clicked.connect(self.user_info_getInfo_Button_Action)

    def user_info_getInfo_Button_Action(self):
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
