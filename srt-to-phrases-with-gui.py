#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import glob
import os
import re
import shutil
import string
import sys
import time

from PySide import QtCore, QtGui
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

def split_long_phrases(en_subs, phrases_duration_limit):
    subs = []

    for sub in en_subs:
        sub_start = sub[0][0]
        sub_end = sub[-1][1]

        if (sub_end - sub_start) > phrases_duration_limit:
            sub_chunks_num = int((sub_end - sub_start) / phrases_duration_limit) + 1

            sub_splitted = [[] for i in range(sub_chunks_num)]

            # +1 for [0...(sub_chunks_num-1)] not [0...sub_chunks_num]
            sub_chunks_limit = (sub_end - sub_start + 1) / sub_chunks_num

            for s in sub:
                s_start = s[0]
                s_end = s[1]
                s_content = s[2]

                pos = int((s_end - sub_start) / sub_chunks_limit)
                sub_splitted[pos].append((s_start, s_end, s_content))

            for s in sub_splitted:
                subs.append(s)
        else:
            subs.append(sub)

    return subs

def convert_into_phrases(en_subs, time_delta, phrases_duration_limit, is_split_long_phrases):
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

    if is_split_long_phrases:
        subs = split_long_phrases(subs, phrases_duration_limit)
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

def create_or_clean_collection_dir(basedir, deck_name):
    prefix = format_filename(deck_name)
    directory = os.path.join(basedir, prefix + ".media")
    if os.path.exists(directory):
        print "Remove dir " + directory
        shutil.rmtree(directory)
    print "Create dir " + directory
    os.makedirs(directory)

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

        self.is_split_long_phrases = False
        self.phrases_duration_limit = 60

        self.video_width = 480
        self.video_height = 320

        self.shift_start = 0.25
        self.shift_end = 0.25

        self.mode = "Movie"

        self.encodings = ["utf-8", "cp1251"]
        self.sub_encoding = None

    def convert_to_unicode(self, file_content):
        for enc in self.encodings:
            try:
                content = file_content.decode(enc)
                self.sub_encoding = enc
                return content
            
            except UnicodeDecodeError:
                pass

        self.sub_encoding = None
        return file_content

    def load_subtitle(self, filename):
        if len(filename) == 0:
            return []

        file_content = open(filename, 'r').read()
        if file_content[:3]=='\xef\xbb\xbf': # with bom
            file_content = file_content[3:]

        ## Оставляем только одну пустую строку между субтитрами
        file_content = fix_empty_lines(file_content)

        ## Конвертируем субтитры в Unicode
        file_content = self.convert_to_unicode(file_content)

        ## Читаем субтитры
        return read_subtitles(file_content)

    def encode_str(self, enc_str):
        if self.sub_encoding == None:
            return enc_str
        return enc_str.encode('utf-8')

    def write_subtitles(self, file_name, subs):
        f_out = open(file_name, 'w')

        for idx in range(len(subs)):
            f_out.write(self.encode_str(str(idx+1) + "\n"))
            f_out.write(self.encode_str(seconds_to_srt_time(subs[idx][0]) + " --> " + seconds_to_srt_time(subs[idx][1]) + "\n"))
            f_out.write(self.encode_str(subs[idx][2] + "\n"))
            f_out.write(self.encode_str("\n"))
        
        f_out.close()

    def write_tsv_file(self, deck_name, en_subs, ru_subs, directory):
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

            f_out.write(self.encode_str(tag + "\t" + sequence + "\t[sound:" + sound + "]\t[sound:" + video + "]\t"))
            f_out.write(self.encode_str(en_sub))
            f_out.write(self.encode_str("\t"))
            f_out.write(self.encode_str(ru_sub))
            f_out.write(self.encode_str('\n'))

            ffmpeg_split_timestamps.append((prefix + "_" + start_time + "-" + end_time, 
                seconds_to_ffmpeg_time(en_subs[idx][0]), 
                seconds_to_ffmpeg_time(en_subs[idx][1])))
        
        f_out.close()

        return ffmpeg_split_timestamps

    def create_subtitles(self):
        print "--------------------------"
        print "Video file: %s" % self.video_file
        print "Audio id: %s" % self.audio_id
        print "English subtitles: %s" % self.en_srt
        print "Russian subtitles: %s" % self.ru_srt
        print "Output Directory: %s" % self.directory
        print "Deck name: %s" % self.deck_name
        print "Gap between phrases: %s" % self.time_delta
        print "Split Long Phrases: %s" % self.is_split_long_phrases
        print "Max length phrases: %s" % self.phrases_duration_limit
        print "Video width: %s" % self.video_width
        print "Video height: %s" % self.video_height
        print "Shift start: %s" % self.shift_start
        print "Shift end: %s" % self.shift_end
        print "Mode: %s" % self.mode
        print "--------------------------"

        # Загружаем английские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading English subtitles..."
        en_subs = self.load_subtitle(self.en_srt)
        print "Encoding: %s" % self.sub_encoding 
        print "English subtitles: %s" % len(en_subs)

        if len(en_subs) == 0:
            print "Error: english subtitles can't be empty"
            return

        # Разбиваем субтитры на фразы
        self.en_subs_phrases = convert_into_phrases(en_subs, self.time_delta, self.phrases_duration_limit, self.is_split_long_phrases)
        print "English phrases: %s" % len(self.en_subs_phrases)

        # Загружаем русские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading Russian subtitles..."
        ru_subs = self.load_subtitle(self.ru_srt)
        print "Encoding: %s" % self.sub_encoding 
        print "Russian subtitles: %s" % len(ru_subs)

        # Синхронизируем русские субтитры с получившимися английскими субтитрами
        print "Syncing Russian subtitles with English phrases..."
        self.ru_subs_phrases = sync_subtitles(self.en_subs_phrases, ru_subs)

        # Добавляем смещения к каждой фразе
        print "Adding Pad Timings between English phrases..."
        add_pad_timings_between_phrases(self.en_subs_phrases, self.shift_start, self.shift_end)

        print "Adding Pad Timings between Russian phrases..."
        add_pad_timings_between_phrases(self.ru_subs_phrases, self.shift_start, self.shift_end)

        if self.mode == "Movie":
            # Меняем длительность фраз в английских субтитрах
            print "Changing duration English subtitles..."
            change_subtitles_ending_time(self.en_subs_phrases)

            # Меняем длительность фраз в русских субтитрах
            print "Changing duration Russian subtitles..."
            change_subtitles_ending_time(self.ru_subs_phrases)

        # Записываем английские субтитры
        print "Writing English subtitles..."
        self.write_subtitles(self.out_en_srt, self.en_subs_phrases)

        # Записываем русские субтитры
        print "Writing Russian subtitles..."
        self.write_subtitles(self.out_ru_srt, self.ru_subs_phrases)

    def create_tsv_file(self):
        # Формируем tsv файл для импорта в Anki
        print "Writing tsv file..."
        self.ffmpeg_split_timestamps = self.write_tsv_file(self.deck_name, self.en_subs_phrases, self.ru_subs_phrases, self.directory)

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

class VideoWorker(QtCore.QThread):

    updateProgress = QtCore.Signal(int)
    updateTitle = QtCore.Signal(str)
    jobFinished = QtCore.Signal(float)

    def __init__(self, data):
        QtCore.QThread.__init__(self)

        self.model = data
        self.canceled = False

    def cancel(self):
      self.canceled = True

    def run(self):
        prefix = format_filename(self.model.deck_name)
        self.video_resolution = str(self.model.video_width) + "x" + str(self.model.video_height)

        time_start = time.time()

        num_files = len(self.model.ffmpeg_split_timestamps)
        for i in range(num_files):
            if self.canceled:
                break

            chunk = self.model.ffmpeg_split_timestamps[i]
            
            self.updateProgress.emit((i * 1.0 / num_files) * 100)
                        
            filename = self.model.directory + os.sep + prefix + ".media" + os.sep + chunk[0]
            ss = chunk[1]
            to = chunk[2]

            print ss
            self.updateTitle.emit(ss)
            
            call(["ffmpeg", "-ss", ss, "-i", self.model.video_file, "-strict", "-2", "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:v:0", "-map", "0:a:" + str(self.model.audio_id), "-c:v", "libx264",
                    "-s", self.video_resolution, "-c:a", "libmp3lame", "-ac", "2", "-copyts", filename + ".mp4"])
            call(["ffmpeg", "-ss", ss, "-i", self.model.video_file, "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:a:" + str(self.model.audio_id), "-copyts", filename + ".mp3"])

        time_end = time.time()
        time_diff = (time_end - time_start)
 
        if not self.canceled:
            self.updateProgress.emit(100)
            self.jobFinished.emit(time_diff)

        print "Done"

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
        self.splitPhrasesSpinBox.valueChanged.connect(self.setPhrasesDurationLimit)
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
        self.tryToSetEngAudio()

        # Try to find subtitles
        self.model.en_srt = guess_srt_file(fname, ["*eng*.srt", "*en*.srt"], "")
        self.subsEngEdit.setText(self.model.en_srt)

        self.model.ru_srt = guess_srt_file(fname, ["*rus*.srt", "*ru*.srt"], "")
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

    def tryToSetEngAudio(self):
        eng_id = len(self.audio_streams) - 1
        for cur_id in range(len(self.audio_streams)):
            if self.audio_streams[cur_id].find("[eng]") != -1:
                eng_id = cur_id
                break

        self.audioIdComboBox.setCurrentIndex(eng_id)

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
            language = "???"

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

    def setPhrasesDurationLimit(self):
        self.model.phrases_duration_limit = self.splitPhrasesSpinBox.value()

    def setSplitLongPhrases(self):
        self.model.is_split_long_phrases = self.splitLongPhrasesGroupBox.isChecked();

    def setMovieMode(self):
        self.model.mode = "Movie"

    def setPhrasesMode(self):
        self.model.mode = "Phrases"

    def setDeckName(self):
        self.model.deck_name = self.deckEdit.text()

    def start(self):
        # subtitles
        self.model.create_subtitles()

        # tsv file
        if len(self.model.deck_name) == 0:
            print "Error: deck name can't be empty"
            return
        
        self.model.create_tsv_file()

        if len(self.model.video_file) == 0:
            print "Error: video file name can't be empty"
            return

        # create or remove & create colletion.media directory
        create_or_clean_collection_dir(self.model.directory, self.model.deck_name)

        # video & audio files
        self.convert_video()

    def setProgress(self, progress):
        self.progressDialog.setValue(progress)

    def setTitle(self, title):
        self.progressDialog.setLabelText(title)

    def finishProgressDialog(self, time_diff):
        self.progressDialog.close()
        minutes = int(time_diff / 60)
        seconds = int(time_diff % 60)
        message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
        QtGui.QMessageBox.information(self, "movie2anki", message)

    def cancelProgressDialog(self):
        self.worker.cancel()

    def convert_video(self):
        self.progressDialog = QtGui.QProgressDialog(self)

        self.progressDialog.setWindowTitle("Generate Video & Audio")
        self.progressDialog.setCancelButtonText("Cancel")
        self.progressDialog.setMinimumDuration(0)

        progress_bar = QtGui.QProgressBar(self.progressDialog)
        progress_bar.setAlignment(QtCore.Qt.AlignCenter)
        self.progressDialog.setBar(progress_bar)

        self.worker = VideoWorker(self.model)
        self.worker.updateProgress.connect(self.setProgress)
        self.worker.updateTitle.connect(self.setTitle)
        self.worker.jobFinished.connect(self.finishProgressDialog)

        self.progressDialog.canceled.connect(self.cancelProgressDialog)
        self.progressDialog.setFixedSize(300, self.progressDialog.height())
        self.progressDialog.setModal(True)

        self.worker.start()
        
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
        self.splitLongPhrasesGroupBox = QtGui.QGroupBox("Split Long Phrases:")
        self.splitLongPhrasesGroupBox.setCheckable(True)
        self.splitLongPhrasesGroupBox.setChecked(self.model.is_split_long_phrases)
        self.splitLongPhrasesGroupBox.clicked.connect(self.setSplitLongPhrases)

        self.splitPhrasesSpinBox = QtGui.QSpinBox()
        self.splitPhrasesSpinBox.setRange(0, 6000)
        self.splitPhrasesSpinBox.setSingleStep(10)
        self.splitPhrasesSpinBox.setValue(60)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.splitPhrasesSpinBox)
        hbox.addWidget(QtGui.QLabel("sec"))

        self.splitLongPhrasesGroupBox.setLayout(hbox)

        return self.splitLongPhrasesGroupBox

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