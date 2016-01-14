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

def srt_time_to_seconds(time):
    split_time = time.split(',')
    major, minor = (split_time[0].split(':'), split_time[1])
    return int(major[0]) * 3600 + int(major[1]) * 60 + int(major[2]) + float(minor) / 1000

def get_time_parts(time):
    millisecs = str(time).split(".")[1]
    if len(millisecs) != 3:
        millisecs = millisecs + ('0' * (3 - len(millisecs)))
    millisecs = int(millisecs)
    mins, secs = divmod(time, 60)
    hours, mins = divmod(mins, 60)

    return (hours, mins, secs, millisecs)

def seconds_to_srt_time(time):
    return '%02d:%02d:%02d,%03d' % get_time_parts(time)

def seconds_to_tsv_time(time):
    return '%d.%02d.%02d.%03d' % get_time_parts(time)

def seconds_to_ffmpeg_time(time):
    return '%02d:%02d:%02d.%03d' % get_time_parts(time)

def fix_empty_lines(content):
    return re.sub('\n\n+', '\n\n', content)

def load_subtitle(filename):
    file_content = open(filename, 'r').read()
    if file_content[:3]=='\xef\xbb\xbf': # with bom
        file_content = file_content[3:]

    ## Оставляем только одну пустую строку между субтитрами
    file_content = fix_empty_lines(file_content)

    ## Читаем субтитры
    return read_subtitles(file_content)

def read_subtitles(content):
    en_subs = []
    
    for sub in content.strip().split('\n\n'):
        sub_chunks = sub.split('\n')
        if (len(sub_chunks) >= 3):
            sub_timecode =  sub_chunks[1].split(' --> ')
            
            sub_start = srt_time_to_seconds(sub_timecode[0].strip())
            sub_end = srt_time_to_seconds(sub_timecode[1].strip())
            sub_content = " ".join(sub_chunks[2:]).strip()

            en_subs.append((sub_start, sub_end, sub_content))
        else:
            print "%s" % repr(sub)
   
    return en_subs

def write_subtitles(file_name, subs):
    f_out = open(file_name, 'w')

    for idx in range(len(subs)):
        f_out.write(str(idx+1) + "\n")
        f_out.write(seconds_to_srt_time(subs[idx][0]) + " --> " + seconds_to_srt_time(subs[idx][1]) + "\n")
        f_out.write(subs[idx][2] + "\n")
        f_out.write("\n")
    
    f_out.close()

# Формат субтитров
# [(start_time, end_time, subtitle), (), ...], [(...)], ...
def join_lines_within_subs(subs):
    subs_joined = []

    for sub in subs:
        sub_start = sub[0][0]
        sub_end = sub[-1][1]

        sub_content = ""
        for s in sub:
            sub_content = sub_content + " " + s[2]
        
        subs_joined.append((sub_start, sub_end, sub_content.strip()))

    return subs_joined

def convert_into_phrases(en_subs, time_delta):
    subs = []

    for sub in en_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content = sub[2]

        if ( len(subs) > 0 and (sub_start - prev_sub_end) <= time_delta ):
            subs[-1].append((sub_start, sub_end, sub_content))
        else:
            subs.append([(sub_start, sub_end, sub_content)])

        prev_sub_end = sub_end

    subs = join_lines_within_subs(subs)
    return subs

def sync_subtitles(en_subs, ru_subs):
    subs = []

    for en_sub in en_subs:
        en_sub_start = en_sub[0]
        en_sub_end = en_sub[1]
        sub_content = []

        subs.append((en_sub_start, en_sub_end, sub_content))

        for ru_sub in ru_subs:
            ru_sub_start = ru_sub[0]
            ru_sub_end = ru_sub[1]
            ru_sub_content = ru_sub[2]

            if ru_sub_start < en_sub_start:
                if ru_sub_end > en_sub_start and ru_sub_end < en_sub_end:
                    sub_content.append(ru_sub_content) # TODO
                elif ru_sub_end >= en_sub_end:
                    sub_content.append(ru_sub_content) 
            elif ru_sub_start >= en_sub_start and ru_sub_start < en_sub_end:
                if ru_sub_end <= en_sub_end:
                    sub_content.append(ru_sub_content)
                elif ru_sub_end > en_sub_end:
                    sub_content.append(ru_sub_content) # TODO

    tmp_subs = subs
    subs = []

    for sub in tmp_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content = " ".join(sub[2])

        subs.append((sub_start, sub_end, sub_content))

    return subs

def add_pad_timings_between_phrases(subs, shift_start, shift_end):
    for idx in range(len(subs)):
        (start_time, end_time, subtitle) = subs[idx]
        subs[idx] = (start_time - shift_start, end_time + shift_end, subtitle)
    
    (start_time, end_time, subtitle) = subs[0]
    if start_time < 0:
        subs[0] = (0.0, end_time, subtitle)

def change_subtitles_ending_time(subs):
    for idx in range(1, len(subs)):
        (start_time, end_time, subtitle) = subs[idx]
        (prev_start_time, prev_end_time, prev_subtitle) = subs[idx - 1]

        subs[idx - 1] = (prev_start_time, start_time, prev_subtitle)

    (start_time, end_time, subtitle) = subs[0]
    if start_time > 5:
        subs.insert(0, (0.0, start_time, ""))
    else:
        subs[0] = (0.0, end_time, subtitle)

    (start_time, end_time, subtitle) = subs[-1]
    subs[-1] = (start_time, end_time + 600, subtitle)

def guess_srt_file(video_file, mask_list, default_filename):
    for mask in mask_list:
        glob_result = glob.glob(video_file[:-4] + mask)
        if len(glob_result) == 1:
            print "Found subtitle: " + glob_result[0]
            return glob_result[0]
    else:
        return default_filename

def format_filename(deck_name):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in deck_name if c in valid_chars)
    filename = filename.replace(' ','_')
    return filename

def write_tsv_file(deck_name, en_subs, ru_subs, directory):
    prefix = format_filename(deck_name)
    filename = os.path.join(directory, prefix + ".tsv")
    
    f_out = open(filename, 'w')

    ffmpeg_split_timestamps = []
    for idx in range(len(en_subs)):
        start_time = seconds_to_tsv_time(en_subs[idx][0])
        end_time = seconds_to_tsv_time(en_subs[idx][1])

        en_sub = en_subs[idx][2]
        en_sub = re.sub('\n', ' ', en_sub)
        ru_sub = ru_subs[idx][2]
        ru_sub = re.sub('\n', ' ', ru_sub)

        tag = prefix
        sequence = str(idx + 1).zfill(3) + "_" + start_time
        sound = prefix + "_" + start_time + "-" + end_time + ".mp3"
        video = prefix + "_" + start_time + "-" + end_time + ".mp4"

        f_out.write(tag + "\t" + sequence + "\t[sound:" + sound + "]\t[sound:" + video + "]\t")
        f_out.write(en_sub)
        f_out.write("\t")
        f_out.write(ru_sub)
        f_out.write('\n')

        ffmpeg_split_timestamps.append((prefix + "_" + start_time + "-" + end_time, 
            seconds_to_ffmpeg_time(en_subs[idx][0]), 
            seconds_to_ffmpeg_time(en_subs[idx][1])))
    
    f_out.close()

    return ffmpeg_split_timestamps

def create_or_clean_collection_dir(basedir):
    directory = os.path.join(basedir, "collection.media")
    if os.path.exists(directory):
        print "Remove dir " + directory
        shutil.rmtree(directory)
    print "Create dir " + directory
    os.makedirs(directory)

def convert_video(video_file, video_width, video_height, audio_id, directory, ffmpeg_split_timestamps):
    video_resolution = str(video_width) + "x" + str(video_height)
    for chunk in ffmpeg_split_timestamps:
        filename = directory + os.sep + "collection.media" + os.sep + chunk[0]
        ss = chunk[1]
        to = chunk[2]

        print ss
        
        call(["ffmpeg", "-ss", ss, "-i", video_file, "-strict", "-2", "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:v:0", "-map", "0:a:" + str(audio_id), "-c:v", "libx264",
                "-s", video_resolution, "-c:a", "libmp3lame", "-ac", "2", "-copyts", filename + ".mp4"])
        call(["ffmpeg", "-ss", ss, "-i", video_file, "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:a:" + str(audio_id), "-copyts", filename + ".mp3"])

class Model(object):
    def __init__(self):
        self.video_file = ""
        self.audio_id = 0

        self.en_srt = ""
        self.ru_srt = ""

        self.out_en_srt = "out.en.srt"
        self.out_ru_srt = "out.ru.srt"

        self.deck_name = ""

        self.directory = os.getcwd()

        self.time_delta = 1.75

        self.video_width = 480
        self.video_height = 320

        self.shift_start = 0.25
        self.shift_end = 0.25

        self.mode = "Movie"

    def run(self):
        print "--------------------------"
        print "Video file: %s" % self.video_file
        print "Audio id: %s" % self.audio_id
        print "English subtitles: %s" % self.en_srt
        print "Russian subtitles: %s" % self.ru_srt
        print "Output Directory: %s" % self.directory
        print "Deck name: %s" % self.deck_name
        print "Time delta: %s" % self.time_delta
        print "Video width: %s" % self.video_width
        print "Video height: %s" % self.video_height
        print "Shift start: %s" % self.shift_start
        print "Shift end: %s" % self.shift_end
        print "Mode: %s" % self.mode
        print "--------------------------"

        # Загружаем английские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading English subtitles..."
        en_subs = load_subtitle(self.en_srt)
        print "English subtitles: %s" % len(en_subs)

        # Разбиваем субтитры на фразы
        en_subs_phrases = convert_into_phrases(en_subs, self.time_delta)
        print "English phrases: %s" % len(en_subs_phrases)

        # Загружаем русские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading Russian subtitles..."
        ru_subs = load_subtitle(self.ru_srt)
        print "Russian subtitles: %s" % len(ru_subs)

        # Синхронизируем русские субтитры с получившимися английскими субтитрами
        print "Syncing Russian subtitles with English phrases..."
        ru_subs_phrases = sync_subtitles(en_subs_phrases, ru_subs)

        # Добавляем смещения к каждой фразе
        print "Adding Pad Timings between English phrases..."
        add_pad_timings_between_phrases(en_subs_phrases, self.shift_start, self.shift_end)

        print "Adding Pad Timings between Russian phrases..."
        add_pad_timings_between_phrases(ru_subs_phrases, self.shift_start, self.shift_end)

        if self.mode == "Movie":
            # Меняем длительность фраз в английских субтитрах
            print "Changing duration English subtitles..."
            change_subtitles_ending_time(en_subs_phrases)

            # Меняем длительность фраз в русских субтитрах
            print "Changing duration Russian subtitles..."
            change_subtitles_ending_time(ru_subs_phrases)

        # Записываем английские субтитры
        print "Writing English subtitles..."
        write_subtitles(self.out_en_srt, en_subs_phrases)

        # Записываем русские субтитры
        print "Writing Russian subtitles..."
        write_subtitles(self.out_ru_srt, ru_subs_phrases)

        # Формируем tsv файл для импорта в Anki
        ffmpeg_split_timestamps = write_tsv_file(self.deck_name, en_subs_phrases, ru_subs_phrases, self.directory)

        # Создаем директорию collection.media
        create_or_clean_collection_dir(self.directory)

        # Конвертируем видео
        convert_video(self.video_file, self.video_width, self.video_height, self.audio_id, self.directory, ffmpeg_split_timestamps)

        # Готово
        print "Done"

    def getTimeDelta(self):
        return self.time_delta

    def getVideoWidth(self):
        return self.video_width

    def getVideoHeight(self):
        return self.video_height

    def getShiftStart(self):
        return self.shift_start * 1000

    def getShiftEnd(self):
        return self.shift_end * 1000

    def setShiftStart(self, value):
        self.shift_start = value / 1000.0

    def setShiftEnd(self, value):
        self.shift_end = value / 1000.0

    def getMode(self):
        return self.mode

class Example(QtGui.QMainWindow):
    
    def __init__(self):
        super(Example, self).__init__()
        
        self.model = Model()
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
        self.videoButton.clicked.connect(self.showVideoFileDialog)
        self.audioIdComboBox.currentIndexChanged.connect(self.setAudioId)
        self.subsEngButton.clicked.connect(self.showSubsEngFileDialog)
        self.subsRusButton.clicked.connect(self.showSubsRusFileDialog)
        self.outDirButton.clicked.connect(self.showOutDirectoryDialog)
        self.deckEdit.textChanged.connect(self.setDeckName)
        self.startButton.clicked.connect(self.start)
        self.timeSpinBox.valueChanged.connect(self.setTimeDelta)
        self.widthSpinBox.valueChanged.connect(self.setVideoWidth)
        self.heightSpinBox.valueChanged.connect(self.setVideoHeight)
        self.startSpinBox.valueChanged.connect(self.setShiftStart)
        self.endSpinBox.valueChanged.connect(self.setShiftEnd)
        self.movieRadioButton.toggled.connect(self.setMovieMode)
        self.phrasesRadioButton.toggled.connect(self.setPhrasesMode)
        # ---------------------------------------------------
        vbox.addStretch(1)

        w.setLayout(vbox)
        
        self.setCentralWidget(w)

        self.adjustSize()
        # self.resize(600, self.height())
        self.setWindowTitle('movies2anki')
        self.show()

    def showVideoFileDialog(self):
        fname, _ = QtGui.QFileDialog.getOpenFileName(dir = self.dir, filter = "Video Files (*.avi *.mkv *.mp4);;All files (*.*)")
        self.videoEdit.setText(fname)
        self.model.video_file = fname
        
        # Get Audio Streams
        self.audioIdComboBox.clear()
        self.getAudioStreams(fname)
        self.audioIdComboBox.addItems(self.audio_streams)

        # Try to find subtitles
        self.model.en_srt = guess_srt_file(fname, ["*eng.srt", "*en.srt"], "")
        self.subsEngEdit.setText(self.model.en_srt)

        self.model.ru_srt = guess_srt_file(fname, ["*rus.srt", "*ru.srt"], "")
        self.subsRusEdit.setText(self.model.ru_srt)

        self.dir = os.path.dirname(fname)

    def showSubsEngFileDialog(self):
        fname, _ = QtGui.QFileDialog.getOpenFileName(dir = self.dir, filter = "Subtitle Files (*.srt)")
        self.subsEngEdit.setText(fname)
        self.model.en_srt = fname

        self.dir = os.path.dirname(fname)

    def showSubsRusFileDialog(self):
        fname, _ = QtGui.QFileDialog.getOpenFileName(dir = self.dir, filter = "Subtitle Files (*.srt)")
        self.subsRusEdit.setText(fname)
        self.model.ru_srt = fname

        self.dir = os.path.dirname(fname)

    def showOutDirectoryDialog(self):
        fname = QtGui.QFileDialog.getExistingDirectory(dir = self.dir)

        if len(fname) != 0:
            self.model.directory = fname

        self.outDirEdit.setText(self.model.directory)

    def setAudioId(self):
        self.model.audio_id = self.audioIdComboBox.currentIndex()

    def getAudioStreams(self, video_file):
        output = check_output(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", video_file])
        json_data = json.loads(output)
        streams = json_data["streams"]

        self.audio_streams = []
        for idx in range(len(streams)):
            audio = streams[idx]

            title = ""
            language = ""

            if audio.has_key("tags"):
                tags = audio["tags"]
                if tags.has_key("language"):
                    language = tags["language"]

            if len(title) != 0:
                stream = "%i: %s [%s]" % (idx, title, language)
            else:
                stream = "%i: [%s]" % (idx, language)

            self.audio_streams.append(stream)

    def setVideoWidth(self):
        self.model.video_width = self.widthSpinBox.value()

    def setVideoHeight(self):
        self.model.video_height = self.heightSpinBox.value()

    def setShiftStart(self):
        self.model.setShiftStart(self.startSpinBox.value())

    def setShiftEnd(self):
        self.model.setShiftEnd(self.endSpinBox.value())

    def setTimeDelta(self):
        self.model.time_delta = self.timeSpinBox.value()

    def setMovieMode(self):
        self.model.mode = "Movie"

    def setPhrasesMode(self):
        self.model.mode = "Phrases"

    def setDeckName(self):
        self.model.deck_name = self.deckEdit.text()

    def start(self):
        self.model.run()

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
        self.outDirEdit.setText(self.model.directory)

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
        self.widthSpinBox.setValue(self.model.getVideoWidth())

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.widthSpinBox)
        hbox.addWidget(QtGui.QLabel("px"))

        layout.addRow(QtGui.QLabel("Width:"), hbox)

        self.heightSpinBox = QtGui.QSpinBox()
        self.heightSpinBox.setRange(16, 2048)
        self.heightSpinBox.setSingleStep(2)
        self.heightSpinBox.setValue(self.model.getVideoHeight())

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
        self.startSpinBox.setValue(self.model.getShiftStart())

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.startSpinBox)
        hbox.addWidget(QtGui.QLabel("ms"))

        layout.addRow(QtGui.QLabel("Start:"), hbox)

        self.endSpinBox = QtGui.QSpinBox()
        self.endSpinBox.setRange(-9999, 9999)
        self.endSpinBox.setValue(self.model.getShiftEnd())

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
        self.timeSpinBox.setValue(self.model.getTimeDelta())

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
        self.phrasesRadioButton = QtGui.QRadioButton("Phrases")

        if self.model.getMode() == 'Phrases':
            self.phrasesRadioButton.setChecked(True)
        else:
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
    ex = Example()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()