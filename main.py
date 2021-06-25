import sys


from PySide6 import QtWidgets

import toolui

if __name__ == '__main__':
    app = QtWidgets.QApplication([])

    widget = toolui.TwitchToolUi()
    widget.resize(800, 600)
    widget.show()

    sys.exit(app.exec())

