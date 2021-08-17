import os.path
import sys
import json

from PySide6 import QtWidgets

import toolui


class Setup_wizzard(QtWidgets.QWidget):
    def __init__(self, credentials):
        super(Setup_wizzard, self).__init__()
        self.credentials = credentials
        layout = QtWidgets.QFormLayout()
        self.save_button = QtWidgets.QPushButton("Save")
        self.client_id_lineEdit = QtWidgets.QLineEdit(self.credentials["client id"])
        self.client_secret_lineEdit = QtWidgets.QLineEdit(self.credentials["app secret"])
        self.bot_nickname_lineEdit = QtWidgets.QLineEdit(self.credentials["bot nickname"])
        self.bot_token_required_checkbox = QtWidgets.QCheckBox()
        self.bot_token_lineEdit = QtWidgets.QLineEdit(self.credentials["bot token"])
        self.bot_token_lineEdit.setEnabled(False)

        self.save_button.clicked.connect(self.save_button_callback)
        self.bot_token_required_checkbox.stateChanged.connect(self.checkbox_callback)

        layout.addRow(self.save_button)
        layout.addRow("Client ID", self.client_id_lineEdit)
        layout.addRow("Client Secret", self.client_secret_lineEdit)
        layout.addRow("Bot Username", self.bot_nickname_lineEdit)
        layout.addRow("Seperate Token for Bot", self.bot_token_required_checkbox)
        layout.addRow("Bot Token", self.bot_token_lineEdit)
        self.setLayout(layout)

    def save_button_callback(self):
        self.credentials["client id"] = self.client_id_lineEdit.text().strip()
        self.credentials["app secret"] = self.client_secret_lineEdit.text().strip()
        self.credentials["bot nickname"] = self.bot_nickname_lineEdit.text().strip()
        self.credentials["use seperate token for bot"] = self.bot_token_required_checkbox.isChecked()
        self.credentials["bot token"] = self.bot_token_lineEdit.text().strip()
        if self.credentials["use seperate token for bot"] and not self.credentials["bot token"]:
            QtWidgets.QMessageBox(text="Please insert a bot token!", parent=self).exec()
        else:
            with open("credentials.json", "w") as credentials_file:
                print("Saved credentials")
                json.dump(self.credentials, credentials_file, indent="  ")

            with open("settings.json", "r") as settings_file:
                settings = json.load(settings_file)
            with open("settings.json", "w") as settings_file:
                settings["Setup required"] = False
                json.dump(settings, settings_file, indent="  ")
                print("Saved settings")

    def checkbox_callback(self):
        if self.bot_token_required_checkbox.isChecked():
            self.bot_token_lineEdit.setEnabled(True)
        else:
            self.bot_token_lineEdit.setEnabled(False)


def main():
    # Default settings
    settings = {"Style Sheet": "Stylesheets/DarkTheme/DarkTheme.qss", "Window Size": (800, 600), "Maximized": False, "Export Directory": "Exports/", "Setup required": True}
    _settings = {}
    try:
        with open("settings.json", "r") as settings_file:
            _settings = json.load(settings_file)
            assert _settings.keys() == settings.keys()
            settings = _settings
    except (OSError, AssertionError, json.JSONDecodeError):
        with open("settings.json", "w") as settings_file:
            print("Settings file corrupt, generated new")
            settings.update(_settings)
            json.dump(settings, settings_file, indent="  ")

    credentials = {"client id": "", "app secret": "", "oauth token": "", "refresh token": "", "bot nickname": "", "bot command prefix": "!", "bot channels": [""],
                   "use seperate token for bot": False, "bot token": ""}
    # Default credentials
    try:
        with open("credentials.json", "r") as credentials_file:
            _credentials = json.load(credentials_file)
            assert _credentials.keys() == credentials.keys()
            credentials = _credentials
    except (OSError, AssertionError):
        with open("credentials.json", "w") as credentials_file:
            print("Credentials file corrupt, generated new")
            credentials.update(_credentials)
            json.dump(credentials, credentials_file, indent="  ")

    app = QtWidgets.QApplication([])
    if settings["Setup required"]:
        wzrd = Setup_wizzard(credentials)
        wzrd.show()
    else:
        widget = toolui.TwitchToolUi(settings)

        try:
            with open(settings['Style Sheet'], "r") as f:
                _style = f.read()
                app.setStyleSheet(_style)
        except:
            widget.add_status("Failed to load Stylesheet")

        widget.resize(*settings["Window Size"])
        if settings["Maximized"]:
            widget.showMaximized()
        else:
            widget.show()
    return_code = app.exec()
    sys.exit(return_code)


if __name__ == '__main__':
    main()
