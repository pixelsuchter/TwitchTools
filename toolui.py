import random
import sys

from PySide6 import QtWidgets
from PySide6.QtGui import Qt
from PySide6.QtWidgets import *

import twitchapi


class TwitchToolUi(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.api = twitchapi.Twitch_api()

        # Create widgets
        self.username_LineEdit = QLineEdit("")
        self.getFollows_Button = QPushButton("Get Follows")
        self.followList_Widget = QTableWidget()
        self.followList_Widget.setColumnCount(2)
        self.followList_Widget.setHorizontalHeaderItem(0, QTableWidgetItem("Name"))
        self.followList_Widget.setHorizontalHeaderItem(1, QTableWidgetItem("Time of follow"))
        self.followList_SortingBox = QComboBox()
        self.followList_SortingBox.addItems(["Name A-Z", "Name Z-A", "Follow time New-Old", "Follow time Old-New"])

        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.username_LineEdit)
        layout.addWidget(self.getFollows_Button)
        layout.addWidget(self.followList_SortingBox)
        layout.addWidget(self.followList_Widget)

        # Set dialog layout
        self.setLayout(layout)

        # Add actions
        self.getFollows_Button.clicked.connect(self.getFollows_Button_Action)
        self.followList_SortingBox.currentTextChanged.connect(self.followList_SortingBox_Action)

    def followList_SortingBox_Action(self):
        if self.followList_SortingBox.currentText() == "Name A-Z":
            self.followList_Widget.sortByColumn(0, Qt.AscendingOrder)
        elif self.followList_SortingBox.currentText() == "Name Z-A":
            self.followList_Widget.sortByColumn(0, Qt.DescendingOrder)
        elif self.followList_SortingBox.currentText() == "Follow time New-Old":
            self.followList_Widget.sortByColumn(1, Qt.DescendingOrder)
        elif self.followList_SortingBox.currentText() == "Follow time Old-New":
            self.followList_Widget.sortByColumn(1, Qt.AscendingOrder)
        else:
            # todo error display
            pass

    def getFollows_Button_Action(self):
        self.followList_Widget.clearContents()
        name = self.username_LineEdit.text()
        if name:
            user_id = self.api.names_to_id(name)[0]
            if user_id:
                follows = self.api.get_all_followed_channel_names(user_id)
                self.followList_Widget.setRowCount(len(follows))
                for row, follow in enumerate(follows.items()):
                    self.followList_Widget.setItem(row, 0, QTableWidgetItem(follow[0]))
                    self.followList_Widget.setItem(row, 1, QTableWidgetItem(follow[1]))
                self.followList_SortingBox_Action()  # Update sorting
