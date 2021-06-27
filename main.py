import os.path
import sys
import json

from PySide6 import QtWidgets, QtCore

import toolui

# Default settings
settings = {"Style Sheet": "Stylesheets/DarkTheme.qss"}

if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    widget = toolui.TwitchToolUi()

    if os.path.isfile("settings.json"):
        with open("settings.json", "r") as settings_file:
            settings = json.load(settings_file)
    else:
        with open("settings.json", "w") as settings_file:
            json.dump(settings, settings_file)
            widget.print_status("Failed to load settings, using default")

    try:
        with open(settings['Style Sheet'], "r") as f:
            _style = f.read()
            app.setStyleSheet(_style)
    except:
        widget.print_status("Failed to load Stylesheet")

    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())
