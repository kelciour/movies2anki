#!/usr/bin/env python
# -*- coding: utf-8 -*-

import codecs
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

def change_subtitles_duration(subs):
    for idx in range(1, len(subs)):
        (start_time, end_time, subtitle) = subs[idx]
        (prev_start_time, prev_end_time, prev_subtitle) = subs[idx - 1]
        if start_time - prev_end_time > 0.25:
            subs[idx] = (start_time - 0.25, end_time, subtitle)
            subs[idx - 1] = (prev_start_time, start_time - 0.25, prev_subtitle)
        else:
            subs[idx - 1] = (prev_start_time, start_time, prev_subtitle) # TODO if will be implemented splitting long phrases

    (start_time, end_time, subtitle) = subs[0]
    if (start_time > 5):
        subs[0] = (start_time - 0.25, end_time, subtitle)
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

class Model(object):
    def __init__(self):
        self.video_file = ""
        self.audio_id = 0

        self.en_srt = "en.srt"
        self.ru_srt = "ru.srt"

        self.out_en_srt = "out.en.srt"
        self.out_ru_srt = "out.ru.srt"

        self.deck_name = ""

        self.directory = "collection.media"
        self.time_delta = 1.75

    def run(self):
        print "--------------------------"
        print "Video file: %s" % self.video_file
        print "Audio id: %s" % self.audio_id
        print "English subtitles: %s" % self.en_srt
        print "Russian subtitles: %s" % self.ru_srt
        print "Deck name: %s" % self.deck_name
        print "Time delta: %s" % self.time_delta
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

        # Меняем длительность фраз в английских субтитрах
        print "Changing duration English subtitles..."
        change_subtitles_duration(en_subs_phrases)

        # Меняем длительность фраз в русских субтитрах
        print "Changing duration Russian subtitles..."
        change_subtitles_duration(ru_subs_phrases)

        # Записываем английские субтитры
        print "Writing English subtitles..."
        write_subtitles(self.out_en_srt, en_subs_phrases)

        # Записываем русские субтитры
        print "Writing Russian subtitles..."
        write_subtitles(self.out_ru_srt, ru_subs_phrases)

        # Готово
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

        self.videoButton = QtGui.QPushButton("Video...")
        self.videoEdit = QtGui.QLineEdit()
        self.audioIdComboBox = QtGui.QComboBox()

        self.videoButton.clicked.connect(self.showVideoFileDialog)
        self.audioIdComboBox.currentIndexChanged.connect(self.setAudioId)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.videoButton)
        hbox.addWidget(self.videoEdit)
        hbox.addWidget(self.audioIdComboBox)

        vbox.addLayout(hbox)

        self.subsEngButton = QtGui.QPushButton("Eng Subs...")
        self.subsEngEdit = QtGui.QLineEdit()

        self.subsEngButton.clicked.connect(self.showSubsEngFileDialog)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.subsEngButton)
        hbox.addWidget(self.subsEngEdit)

        vbox.addLayout(hbox)

        self.subsRusButton = QtGui.QPushButton("Rus Subs...")
        self.subsRusEdit = QtGui.QLineEdit()

        self.subsRusButton.clicked.connect(self.showSubsRusFileDialog)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.subsRusButton)
        hbox.addWidget(self.subsRusEdit)

        vbox.addLayout(hbox)

        self.deckLabel = QtGui.QLabel('Name for deck:')
        self.deckEdit = QtGui.QLineEdit()
        self.startButton = QtGui.QPushButton("Go!")

        self.startButton.clicked.connect(self.start)
        self.deckEdit.textChanged.connect(self.setDeckName)

        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.deckLabel)
        hbox.addWidget(self.deckEdit)
        hbox.addWidget(self.startButton)

        vbox.addLayout(hbox)

        vbox.addStretch(1)

        w.setLayout(vbox)
        
        self.setCentralWidget(w)

        self.adjustSize()
        self.resize(600, self.height())
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
        if len(self.subsEngEdit.text()) == 0:
            self.model.en_srt = guess_srt_file(fname, ["*eng.srt", "*en.srt"], "")
            self.subsEngEdit.setText(self.model.en_srt)

        if len(self.subsRusEdit.text()) == 0:
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

    def setDeckName(self):
        self.model.deck_name = self.deckEdit.text()

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

    def start(self):
        self.model.run()
        
def main():
    
    app = QtGui.QApplication(sys.argv)
    main = Example()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()