import os.path
import sys
import json

from PySide6 import QtWidgets

import toolui


def main():
    # Default settings
    settings = {"Style Sheet": "Stylesheets/DarkTheme.qss", "Window Size": (800, 600), "Maximized": False}

    try:
        with open("settings.json", "r") as settings_file:
            _settings = json.load(settings_file)
            assert _settings.keys() == settings.keys()
            settings = _settings
    except (OSError, AssertionError):
        with open("settings.json", "w") as settings_file:
            print("Settings file corrupt, generated new")
            json.dump(settings, settings_file, indent="  ")

    app = QtWidgets.QApplication([])
    widget = toolui.TwitchToolUi(settings)

    try:
        with open(settings['Style Sheet'], "r") as f:
            _style = f.read()
            app.setStyleSheet(_style)
    except:
        widget.update_status("Failed to load Stylesheet")

    widget.resize(*settings["Window Size"])
    if settings["Maximized"]:
        widget.showMaximized()
    else:
        widget.show()
    return_code = app.exec()
    sys.exit(return_code)


if __name__ == '__main__':
    main()
