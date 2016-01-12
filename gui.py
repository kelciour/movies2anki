#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import glob
import os
import re
import shutil
import string
import sys

from PySide import QtGui
from subprocess import check_output
from subprocess import call

class Example(QtGui.QMainWindow):
    
    def __init__(self):
        super(Example, self).__init__()
        
        self.audio_streams = []
        self.dir = ""
        
        self.initUI()
        
    def initUI(self):
        w = QtGui.QWidget()

        vbox = QtGui.QVBoxLayout()

        # ---------------------------------------------------
        filesGroup = self.createFilesGroup()
        vbox.addWidget(filesGroup)
        # ---------------------------------------------------
        outputGroup = self.createOutputGroup()
        vbox.addWidget(outputGroup)
        # ---------------------------------------------------
        optionsGroup = self.createOptionsGroup()
        vbox.addWidget(optionsGroup)
        # ---------------------------------------------------
        bottomGroup = self.createBottomGroup()
        vbox.addLayout(bottomGroup)
        # ---------------------------------------------------

        vbox.addStretch(1)

        w.setLayout(vbox)
        
        self.setCentralWidget(w)

        self.adjustSize()
        self.resize(600, self.height())
        self.setWindowTitle('movies2anki')
        self.show()

    def createFilesGroup(self):
        groupBox = QtGui.QGroupBox("Files:")

        vbox = QtGui.QVBoxLayout()

        self.videoButton = QtGui.QPushButton("Video...")
        self.videoEdit = QtGui.QLineEdit()
        self.audioIdComboBox = QtGui.QComboBox()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.videoButton)
        hbox.addWidget(self.videoEdit)
        hbox.addWidget(self.audioIdComboBox)

        vbox.addLayout(hbox)

        self.subsEngButton = QtGui.QPushButton("Eng Subs...")
        self.subsEngEdit = QtGui.QLineEdit()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.subsEngButton)
        hbox.addWidget(self.subsEngEdit)

        vbox.addLayout(hbox)

        self.subsRusButton = QtGui.QPushButton("Rus Subs...")
        self.subsRusEdit = QtGui.QLineEdit()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.subsRusButton)
        hbox.addWidget(self.subsRusEdit)

        vbox.addLayout(hbox)

        groupBox.setLayout(vbox)

        return groupBox

    def createOutputGroup(self):
        groupBox = QtGui.QGroupBox("Output:")

        vbox = QtGui.QVBoxLayout()

        self.outDirButton = QtGui.QPushButton("Directory...")
        self.outDirEdit = QtGui.QLineEdit()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.outDirButton)
        hbox.addWidget(self.outDirEdit)

        vbox.addLayout(hbox)

        groupBox.setLayout(vbox)

        return groupBox

    def createVideoDimensionsGroup(self):
        groupBox = QtGui.QGroupBox("Video Dimensions:")

        layout = QtGui.QFormLayout()

        self.widthSpinBox = QtGui.QSpinBox()
        self.widthSpinBox.setRange(16, 2048)
        self.widthSpinBox.setSingleStep(2)
        self.widthSpinBox.setValue(16)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.widthSpinBox)
        hbox.addWidget(QtGui.QLabel("px"))

        layout.addRow(QtGui.QLabel("Width:"), hbox)

        self.heightSpinBox = QtGui.QSpinBox()
        self.heightSpinBox.setRange(16, 2048)
        self.heightSpinBox.setSingleStep(2)
        self.heightSpinBox.setValue(16)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.heightSpinBox)
        hbox.addWidget(QtGui.QLabel("px"))

        layout.addRow(QtGui.QLabel("Height:"), hbox)

        groupBox.setLayout(layout)

        return groupBox

    def createPadTimingsGroup(self):
        groupBox = QtGui.QGroupBox("Pad Timings:")

        layout = QtGui.QFormLayout()

        self.startSpinBox = QtGui.QSpinBox()
        self.startSpinBox.setRange(-9999, 9999)
        self.startSpinBox.setValue(250)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.startSpinBox)
        hbox.addWidget(QtGui.QLabel("ms"))

        layout.addRow(QtGui.QLabel("Start:"), hbox)

        self.endSpinBox = QtGui.QSpinBox()
        self.endSpinBox.setRange(-9999, 9999)
        self.endSpinBox.setValue(250)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.endSpinBox)
        hbox.addWidget(QtGui.QLabel("ms"))

        layout.addRow(QtGui.QLabel("End:"), hbox)

        groupBox.setLayout(layout)

        return groupBox

    def createGapPhrasesGroup(self):
        groupBox = QtGui.QGroupBox("Gap between Phrases:")

        self.timeSpinBox = QtGui.QDoubleSpinBox()
        self.timeSpinBox.setRange(0, 60.0)
        self.timeSpinBox.setSingleStep(0.25)
        self.timeSpinBox.setValue(1.25)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.timeSpinBox)
        hbox.addWidget(QtGui.QLabel("sec"))

        groupBox.setLayout(hbox)

        return groupBox

    def createSplitPhrasesGroup(self):
        groupBox = QtGui.QGroupBox("Split Long Phrases:")
        groupBox.setCheckable(True)
        groupBox.setChecked(False)

        self.splitPhrasesSpinBox = QtGui.QSpinBox()
        self.splitPhrasesSpinBox.setRange(0, 6000)
        self.splitPhrasesSpinBox.setSingleStep(10)
        self.splitPhrasesSpinBox.setValue(60)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.splitPhrasesSpinBox)
        hbox.addWidget(QtGui.QLabel("sec"))

        groupBox.setLayout(hbox)

        return groupBox

    def createModeOptionsGroup(self):
        vbox = QtGui.QVBoxLayout()

        self.movieRadioButton = QtGui.QRadioButton("Movie")
        self.phrasesRadioButton = QtGui.QRadioButton("Phrase")

        self.movieRadioButton.setChecked(True)

        vbox.addWidget(self.movieRadioButton)
        vbox.addWidget(self.phrasesRadioButton)

        return vbox

    def createSubtitlePhrasesGroup(self):
        groupBox = QtGui.QGroupBox("General Settings:")

        layout = QtGui.QHBoxLayout()

        layout.addWidget(self.createGapPhrasesGroup())
        layout.addWidget(self.createSplitPhrasesGroup())
        layout.addLayout(self.createModeOptionsGroup())

        groupBox.setLayout(layout)

        return groupBox

    def createOptionsGroup(self):
        groupBox = QtGui.QGroupBox("Options:")

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.createVideoDimensionsGroup())
        hbox.addWidget(self.createPadTimingsGroup())
        hbox.addWidget(self.createSubtitlePhrasesGroup())

        groupBox.setLayout(hbox)

        return groupBox

    def createBottomGroup(self):
        groupBox = QtGui.QGroupBox("Name for deck:")

        self.deckEdit = QtGui.QLineEdit()

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.deckEdit)

        groupBox.setLayout(hbox)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(groupBox)

        vbox = QtGui.QVBoxLayout()
        self.previewButton = QtGui.QPushButton("Preview...")
        self.startButton = QtGui.QPushButton("Go!")
        vbox.addWidget(self.previewButton)
        vbox.addWidget(self.startButton)

        hbox.addLayout(vbox)

        return hbox

def main():
    
    app = QtGui.QApplication(sys.argv)
    main = Example()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()