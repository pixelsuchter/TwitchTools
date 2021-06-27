import os.path
import sys
import json

from PySide6 import QtWidgets, QtCore

import toolui

if __name__ == '__main__':
    if os.path.isfile("settings.json"):
        with open("settings.json", "r") as settings_file:
            settings = json.load(settings_file)
    else:
        settings = {"Style Sheet": "Stylesheets/DarkTheme.qss"}
        with open("settings.json", "w") as settings_file:
            json.dump(settings, settings_file)

    app = QtWidgets.QApplication([])

    with open(settings['Style Sheet'], "r") as f:
        _style = f.read()
        app.setStyleSheet(_style)



    widget = toolui.TwitchToolUi()
    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())

