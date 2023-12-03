# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'condensed_audio_exporter.ui'
#
# Created by: PyQt5 UI code generator 5.13.0
#
# WARNING! All changes made in this file will be lost!


from PyQt5 import QtCore, QtGui, QtWidgets


class Ui_Dialog(object):
    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(522, 130)
        self.verticalLayout = QtWidgets.QVBoxLayout(Dialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.outputDirBtn = QtWidgets.QPushButton(Dialog)
        self.outputDirBtn.setMinimumSize(QtCore.QSize(100, 0))
        self.outputDirBtn.setObjectName("outputDirBtn")
        self.horizontalLayout.addWidget(self.outputDirBtn)
        self.outputDir = QtWidgets.QLineEdit(Dialog)
        self.outputDir.setObjectName("outputDir")
        self.horizontalLayout.addWidget(self.outputDir)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.groupBox_2 = QtWidgets.QGroupBox(Dialog)
        self.groupBox_2.setObjectName("groupBox_2")
        self.verticalLayout_2 = QtWidgets.QVBoxLayout(self.groupBox_2)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.mediaDir = QtWidgets.QCheckBox(self.groupBox_2)
        self.mediaDir.setObjectName("mediaDir")
        self.verticalLayout_2.addWidget(self.mediaDir)
        self.verticalLayout.addWidget(self.groupBox_2)
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.startBtn = QtWidgets.QPushButton(Dialog)
        self.startBtn.setObjectName("startBtn")
        self.horizontalLayout_2.addWidget(self.startBtn)
        self.verticalLayout.addLayout(self.horizontalLayout_2)

        self.retranslateUi(Dialog)
        self.startBtn.clicked.connect(Dialog.accept)
        QtCore.QMetaObject.connectSlotsby_name(Dialog)

    def retranslateUi(self, Dialog):
        _translate = QtCore.QCoreApplication.translate
        Dialog.setWindowTitle(_translate("Dialog", "Export Condensed Audio"))
        self.outputDirBtn.setText(_translate("Dialog", "Output Directory:"))
        self.groupBox_2.setTitle(_translate("Dialog", "Options:"))
        self.mediaDir.setText(_translate("Dialog", "Store temporary audio files in the collection.media folder"))
        self.startBtn.setText(_translate("Dialog", "Start"))
