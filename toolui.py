import json
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
        self.old_settings = settings.copy()
        self.settings = settings

        self.status_list = ["Idle"]

        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" % self.threadpool.maxThreadCount())

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

    def print_output(self, s):
        print(s)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.settings["Window Size"] = [self.size().width(), self.size().height()]
        self.settings["Maximized"] = self.isMaximized()

        if not (self.settings == self.old_settings):
            with open("settings.json", "w") as settings_file:
                json.dump(self.settings, settings_file, indent="  ")
                print("Settings saved")

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
