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

from collections import deque
from ConfigParser import SafeConfigParser
from PyQt4 import QtCore, QtGui
from subprocess import call
from subprocess import check_output
from subprocess import Popen

import subprocess
import os.path

# Determine if we're frozen with Pyinstaller or not.
if getattr(sys, 'frozen', False):
    isFrozen = True
else:
    isFrozen = False

# Create a set of arguments which make a ``subprocess.Popen`` (and
# variants) call work with or without Pyinstaller, ``--noconsole`` or
# not, on Windows and Linux. Typical use::
#
#   subprocess.call(['program_to_run', 'arg_1'], **subprocess_args())
#
# When calling ``check_output``::
#
#   subprocess.check_output(['program_to_run', 'arg_1'],
#                           **subprocess_args(False))
def subprocess_args(include_stdout=True):
    # The following is true only on Windows.
    if hasattr(subprocess, 'STARTUPINFO'):
        # On Windows, subprocess calls will pop up a command window by default
        # when run from Pyinstaller with the ``--noconsole`` option. Avoid this
        # distraction.
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        # Windows doesn't search the path by default. Pass it an environment so
        # it will.
        env = os.environ
    else:
        si = None
        env = None

    # ``subprocess.check_output`` doesn't allow specifying ``stdout``::
    #
    #   Traceback (most recent call last):
    #     File "test_subprocess.py", line 58, in <module>
    #       **subprocess_args(stdout=None))
    #     File "C:\Python27\lib\subprocess.py", line 567, in check_output
    #       raise ValueError('stdout argument not allowed, it will be overridden.')
    #   ValueError: stdout argument not allowed, it will be overridden.
    #
    # So, add it only if it's needed.
    if include_stdout:
        ret = {'stdout': subprocess.PIPE}
    else:
        ret = {}

    # On Windows, running this from the binary produced by Pyinstaller
    # with the ``--noconsole`` option requires redirecting everything
    # (stdin, stdout, stderr) to avoid an OSError exception
    # "[Error 6] the handle is invalid."
    ret.update({'stdin': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'startupinfo': si,
                'env': env })
    return ret

def srt_time_to_seconds(time):
    split_time = time.split(',')
    major, minor = (split_time[0].split(':'), split_time[1])
    return int(major[0]) * 3600 + int(major[1]) * 60 + int(major[2]) + float(minor) / 1000

def tsv_time_to_seconds(tsv_time):
    return srt_time_to_seconds(tsv_time.replace(".", ","))

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

def escape_double_quotes(content):
    return re.sub('"', '&quot;', content)

def is_not_sdh_subtitle(sub):
    reg_exp_round_braces = r"^\([^)]*\)(\s*\([^)]*\))*$"
    reg_exp_square_braces = r"^\[[^\]]*\](\s*\[[^\]]*\])*$"
    reg_exp_round_braces_with_tags = r"^(?:- )?(?:<[^>]+>)*\([^)]*\)(\s*\([^)]*\))*(?:<[^>]+>)*$"
    reg_exp_round_braces_with_tags_multiline = r"^(\([^)]*\)(\s*\([^)]*\))*|\s|-|(?:<[^>]+>)*)*$"

    if re.match(reg_exp_round_braces, sub):
        return False
    elif re.match(reg_exp_square_braces, sub):
        return False
    elif re.match(reg_exp_round_braces_with_tags, sub):
        return False
    elif re.match(reg_exp_round_braces_with_tags_multiline, sub):
        return False

    return True

def read_subtitles(content, is_ignore_SDH):
    en_subs = []
    
    for sub in content.strip().split('\n\n'):
        sub_chunks = sub.split('\n')
        if (len(sub_chunks) >= 3):
            sub_timecode =  sub_chunks[1].split(' --> ')
            
            sub_start = srt_time_to_seconds(sub_timecode[0].strip())
            sub_end = srt_time_to_seconds(sub_timecode[1].strip())
            sub_content = " ".join(sub_chunks[2:]).replace("\t", " ")
            sub_content = re.sub(r"\n +", "\n", sub_content)
            sub_content = re.sub(r"  +", " ", sub_content)
            sub_content = sub_content.strip()

            if len(sub_content) > 0:
                if not is_ignore_SDH:
                    en_subs.append((sub_start, sub_end, sub_content))
                else:
                    if is_not_sdh_subtitle(sub_content):
                        en_subs.append((sub_start, sub_end, sub_content))
                    else:
                        print "Ignore subtitle: %s" % repr(sub_content)
            else:
                print "Empty subtitle: %s" % repr(sub)
        else:
            print "Ignore subtitle: %s" % repr(sub)
   
    return en_subs

# Формат субтитров
# [(start_time, end_time, subtitle), (), ...], [(...)], ...
def join_lines_within_subs(subs):
    subs_joined = []

    global duration_longest_phrase
    duration_longest_phrase = 0

    for sub in subs:
        sub_start = sub[0][0]
        sub_end = sub[-1][1]

        sub_content = ""
        for s in sub:
            sub_content = sub_content + " " + s[2]
        
        subs_joined.append((sub_start, sub_end, sub_content.strip()))

        if sub_end - sub_start > duration_longest_phrase:
            duration_longest_phrase = int(sub_end - sub_start)

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
                if len(s) != 0:
                    subs.append(s)
        else:
            subs.append(sub)

    return subs

def convert_into_sentences(en_subs, phrases_duration_limit):
    subs = []

    for sub in en_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content = sub[2]

        if len(subs) > 0: 
            prev_sub_start = subs[-1][0]
            prev_sub_end = subs[-1][1]
            prev_sub_content = subs[-1][2]

            if ((sub_start - prev_sub_end) < 1.5 and (sub_end - prev_sub_start) < phrases_duration_limit and 
                prev_sub_content[-1] != '.' and 
                prev_sub_content[-1] != '?' and
                prev_sub_content[-1] != '!'):

                subs[-1] = (prev_sub_start, sub_end, prev_sub_content + " " + sub_content)
            else:
                subs.append((sub_start, sub_end, sub_content))
        else:
            subs.append((sub_start, sub_end, sub_content))

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

        if prev_end_time < start_time:
            subs[idx - 1] = (prev_start_time, start_time, prev_subtitle)

    (start_time, end_time, subtitle) = subs[0]
    if start_time > 15:
        subs.insert(0, (0.0, start_time, ""))
    else:
        subs[0] = (0.0, end_time, subtitle)

    (start_time, end_time, subtitle) = subs[-1]
    subs[-1] = (start_time, end_time + 600, subtitle)

def find_glob_files(glob_pattern):
    # replace the left square bracket with [[]
    glob_pattern = re.sub(r'\[', '[[]', glob_pattern)
    # replace the right square bracket with []] but be careful not to replace
    # the right square brackets in the left square bracket's 'escape' sequence.
    glob_pattern = re.sub(r'(?<!\[)\]', '[]]', glob_pattern)

    return glob.glob(glob_pattern)

def guess_srt_file(video_file, mask_list, default_filename):
    for mask in mask_list:
        glob_pattern = video_file[:-4] + mask

        glob_result = find_glob_files(glob_pattern)
        if len(glob_result) >= 1:
            print ("Found subtitle: " + glob_result[0]).encode('utf-8')
            return glob_result[0]
    else:
        return default_filename

def format_filename(deck_name):
    """
    Returns the given string converted to a string that can be used for a clean
    filename. Specifically, leading and trailing spaces are removed; other
    spaces are converted to underscores; and anything that is not a unicode
    alphanumeric, dash, underscore, or dot, is removed.
    >>> get_valid_filename("john's portrait in 2004.jpg")
    'johns_portrait_in_2004.jpg'
    """
    s = deck_name.strip().replace(' ', '_')
    return re.sub(r'(?u)[^-\w.]', '', s)

def getNameForCollectionDirectory(basedir, deck_name):
    prefix = format_filename(deck_name)
    directory = os.path.join(basedir, prefix + ".media")
    return directory

def create_collection_dir(directory):
    try:
        os.makedirs(directory)
    except OSError as ex:
        return False
    return True

def create_or_clean_collection_dir(directory):
    try:
        if os.path.exists(directory):
            print "Remove dir " + directory.encode('utf-8')
            shutil.rmtree(directory)
            time.sleep(0.5)
    
        print "Create dir " + directory.encode('utf-8')
        os.makedirs(directory)
    except OSError as ex:
        print ex
        return False

    return True

class Model(object):
    def __init__(self):
        self.config_file_name = 'config.ini'
        
        self.video_file = ""
        self.audio_id = 0
        self.deck_name = ""

        self.en_srt = ""
        self.ru_srt = ""

        self.out_en_srt_suffix = "out.en.srt"
        self.out_ru_srt_suffix = "out.ru.srt"

        self.out_en_srt = "out.en.srt"
        self.out_ru_srt = "out.ru.srt"

        self.encodings = ["utf-8", "cp1251"]
        self.sub_encoding = None
        
        self.p = None

        self.load_settings()

    def default_settings(self):
        self.input_directory = ""
        self.output_directory = os.getcwd()

        self.time_delta = 1.75

        self.is_split_long_phrases = False
        self.phrases_duration_limit = 60

        self.video_width = 480
        self.video_height = 320

        self.shift_start = 0.75
        self.shift_end = 0.75

        self.mode = "Movie"

        self.recent_deck_names = deque(maxlen = 5)

        self.is_write_output_subtitles = False
        self.is_ignore_sdh_subtitle = True
        self.is_add_dir_to_media_path = False

    def load_settings(self):
        self.default_settings()

        if not os.path.isfile(self.config_file_name):
            return

        config = SafeConfigParser()
        config.read(self.config_file_name)

        self.input_directory = config.get('main', 'input_directory').decode('utf-8')
        self.output_directory = config.get('main', 'output_directory').decode('utf-8')
        self.video_width = config.getint('main', 'video_width')
        self.video_height = config.getint('main', 'video_height')
        self.shift_start = config.getfloat('main', 'pad_start')
        self.shift_end = config.getfloat('main', 'pad_end')
        self.time_delta = config.getfloat('main', 'gap_between_phrases')
        self.is_split_long_phrases = config.getboolean('main', 'is_split_long_phrases')
        self.phrases_duration_limit = config.getint('main', 'phrases_duration_limit')
        self.mode = config.get('main', 'mode')
        self.is_write_output_subtitles = config.getboolean('main', 'is_write_output_subtitles')
        self.is_ignore_sdh_subtitle = config.getboolean('main', 'is_ignore_sdh_subtitle')
        self.is_add_dir_to_media_path = config.getboolean('main', 'is_add_dir_to_media_path')
        
        value = [e.strip() for e in config.get('main', 'recent_deck_names').decode('utf-8').split(',')]
        if len(value) != 0:
            self.recent_deck_names.extendleft(value)

    def save_settings(self):
        config = SafeConfigParser()
        config.add_section('main')
        config.set('main', 'input_directory', self.input_directory.encode('utf-8'))
        config.set('main', 'output_directory', self.output_directory.encode('utf-8'))
        config.set('main', 'video_width', str(self.video_width))
        config.set('main', 'video_height', str(self.video_height))
        config.set('main', 'pad_start', str(self.shift_start))
        config.set('main', 'pad_end', str(self.shift_end))
        config.set('main', 'gap_between_phrases', str(self.time_delta))
        config.set('main', 'is_split_long_phrases', str(self.is_split_long_phrases))
        config.set('main', 'phrases_duration_limit', str(self.phrases_duration_limit))
        config.set('main', 'mode', self.mode)
        config.set('main', 'is_write_output_subtitles', str(self.is_write_output_subtitles))
        config.set('main', 'is_ignore_sdh_subtitle', str(self.is_ignore_sdh_subtitle))
        config.set('main', 'is_add_dir_to_media_path', str(self.is_add_dir_to_media_path))
        
        config.set('main', 'recent_deck_names', ",".join(reversed(self.recent_deck_names)).encode('utf-8'))
  
        with open(self.config_file_name, 'w') as f:
            config.write(f)

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

    def load_subtitle(self, filename, is_ignore_SDH):
        if len(filename) == 0:
            return []

        file_content = open(filename, 'rU').read()
        if file_content[:3]=='\xef\xbb\xbf': # with bom
            file_content = file_content[3:]

        ## Оставляем только одну пустую строку между субтитрами
        file_content = fix_empty_lines(file_content)

        ## Конвертируем субтитры в Unicode
        file_content = self.convert_to_unicode(file_content)

        ## Читаем субтитры
        return read_subtitles(file_content, is_ignore_SDH)

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
            en_sub = escape_double_quotes(en_sub)
            
            ru_sub = ru_subs[idx][2]
            ru_sub = re.sub('\n', ' ', ru_sub)
            ru_sub = escape_double_quotes(ru_sub)

            tag = prefix
            sequence = str(idx + 1).zfill(3) + "_" + start_time

            sound = prefix + "_" + start_time + "-" + end_time + ".mp3"
            video = prefix + "_" + start_time + "-" + end_time + ".mp4"

            if self.is_add_dir_to_media_path:
                sound = prefix + ".media/" + sound
                video = prefix + ".media/" + video

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
        print "Video file: %s" % self.video_file.encode('utf-8')
        print "Audio id: %s" % self.audio_id
        print "English subtitles: %s" % self.en_srt.encode('utf-8')
        print "Russian subtitles: %s" % self.ru_srt.encode('utf-8')
        print "English subtitles output: %s" % self.out_en_srt.encode('utf-8')
        print "Russian subtitles output: %s" % self.out_ru_srt.encode('utf-8')
        print "Write output subtitles: %s" % self.is_write_output_subtitles
        print "Ignore SDH subtitles: %s" % self.is_ignore_sdh_subtitle
        print "Output Directory: %s" % self.output_directory.encode('utf-8')
        print "Video width: %s" % self.video_width
        print "Video height: %s" % self.video_height
        print "Pad start: %s" % self.shift_start
        print "Pad end: %s" % self.shift_end
        print "Gap between phrases: %s" % self.time_delta
        print "Split Long Phrases: %s" % self.is_split_long_phrases
        print "Max length phrases: %s" % self.phrases_duration_limit
        print "Mode: %s" % self.mode
        print "Deck name: %s" % self.deck_name.encode('utf-8')
        print "--------------------------"

        self.is_subtitles_created = False

        # Загружаем английские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading English subtitles..."
        en_subs = self.load_subtitle(self.en_srt, self.is_ignore_sdh_subtitle)
        print "Encoding: %s" % self.sub_encoding 
        print "English subtitles: %s" % len(en_subs)

        # Разбиваем субтитры на предложения
        self.en_subs_sentences = convert_into_sentences(en_subs, self.phrases_duration_limit)
        print "English sentences: %s" % len(self.en_subs_sentences)

        # Разбиваем субтитры на фразы
        self.en_subs_phrases = convert_into_phrases(self.en_subs_sentences, self.time_delta, self.phrases_duration_limit, self.is_split_long_phrases)
        print "English phrases: %s" % len(self.en_subs_phrases)

        # Загружаем русские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        print "Loading Russian subtitles..."
        ru_subs = self.load_subtitle(self.ru_srt, self.is_ignore_sdh_subtitle)
        print "Encoding: %s" % self.sub_encoding 
        print "Russian subtitles: %s" % len(ru_subs)

        # Для preview диалога
        self.num_en_subs = len(en_subs)
        self.num_ru_subs = len(ru_subs)
        self.num_phrases = len(self.en_subs_phrases)

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

        self.is_subtitles_created = True

    def write_output_subtitles(self):
        # Записываем английские субтитры
        print "Writing English subtitles..."
        self.write_subtitles(self.out_en_srt, self.en_subs_phrases)

        # Записываем русские субтитры
        print "Writing Russian subtitles..."
        self.write_subtitles(self.out_ru_srt, self.ru_subs_phrases)

    def create_tsv_file(self):
        # Формируем tsv файл для импорта в Anki
        print "Writing tsv file..."
        self.ffmpeg_split_timestamps.append(self.write_tsv_file(self.deck_name, self.en_subs_phrases, self.ru_subs_phrases, self.output_directory))

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

    def getPhrasesDurationLimit(self):
        return self.phrases_duration_limit

    def getMode(self):
        return self.mode

class VideoWorker(QtCore.QThread):

    updateProgress = QtCore.pyqtSignal(int)
    updateProgressWindowTitle = QtCore.pyqtSignal(str)
    updateProgressText = QtCore.pyqtSignal(str)
    jobFinished = QtCore.pyqtSignal(float)
    batchJobsFinished = QtCore.pyqtSignal()
    errorRaised = QtCore.pyqtSignal(str)

    def __init__(self, data):
        QtCore.QThread.__init__(self)

        self.model = data
        self.canceled = False

    def cancel(self):
      self.canceled = True

    def run(self):
        self.video_resolution = str(self.model.video_width) + "x" + str(self.model.video_height)

        time_start = time.time()

        num_files_completed = 0       
        num_files = sum(len(files) for files in self.model.ffmpeg_split_timestamps)
        for idx in range(len(self.model.ffmpeg_split_timestamps)):
            if self.canceled:
                break

            if self.model.batch_mode:
                ffmpeg_split_timestamps = self.model.ffmpeg_split_timestamps[idx]
                
                video_file, en_srt, ru_srt, deck_name = self.model.jobs[idx]

                self.model.video_file = video_file
                self.model.en_srt = en_srt
                self.model.ru_srt = ru_srt
                self.model.deck_name = deck_name

                collection_dir = getNameForCollectionDirectory(self.model.output_directory, self.model.deck_name)
                ret = create_collection_dir(collection_dir)
                if ret == False:
                    self.errorRaised.emit("Can't create media directory.")
                    self.canceled = True
                    break

                self.updateProgressWindowTitle.emit("Generate Video & Audio Clips [%s/%s]" % (idx + 1, len(self.model.jobs)))
            else:
                ffmpeg_split_timestamps = self.model.ffmpeg_split_timestamps[idx]

            prefix = format_filename(self.model.deck_name)
            for i in range(len(ffmpeg_split_timestamps)):
                if self.canceled:
                    break

                chunk = ffmpeg_split_timestamps[i]
                
                self.updateProgress.emit((num_files_completed * 1.0 / num_files) * 100)
                            
                filename = self.model.output_directory + os.sep + prefix + ".media" + os.sep + chunk[0]
                ss = chunk[1]
                to = chunk[2]

                t = tsv_time_to_seconds(to) - tsv_time_to_seconds(ss)

                af_d = 0.25
                af_st = 0
                af_to = t - af_d
                af_params = "afade=t=in:st=%s:d=%s,afade=t=out:st=%s:d=%s" % (af_st, af_d, af_to, af_d)

                print ss
                self.updateProgressText.emit(ss)

                cmd = " ".join(["ffmpeg", "-ss", ss, "-i", '"' + self.model.video_file + '"', "-strict", "-2", "-loglevel", "quiet", "-t", str(t), "-af", af_params, "-map", "0:v:0", "-map", "0:a:" + str(self.model.audio_id), "-c:v", "libx264", "-s", self.video_resolution, "-c:a", "aac", "-ac", "2", '"' + filename + ".mp4" + '"'])
                print cmd.encode('utf-8')
                self.model.p = Popen(cmd.encode(sys.getfilesystemencoding()), shell=True, **subprocess_args())
                self.model.p.wait()

                if self.canceled:
                    break

                cmd = " ".join(["ffmpeg", "-ss", ss, "-i", '"' + self.model.video_file + '"', "-loglevel", "quiet", "-t", str(t), "-af", af_params, "-map", "0:a:" + str(self.model.audio_id), '"' + filename + ".mp3" + '"'])
                print cmd.encode('utf-8')
                self.model.p = Popen(cmd.encode(sys.getfilesystemencoding()), shell=True, **subprocess_args())
                self.model.p.wait()

                num_files_completed += 1

        time_end = time.time()
        time_diff = (time_end - time_start)
 
        if not self.canceled:
            self.updateProgress.emit(100)
            self.jobFinished.emit(time_diff)

        if self.canceled:
            print "Canceled"
        else:
            print "Done"
        
        if self.model.batch_mode:
            self.batchJobsFinished.emit()

class JobsInfo(QtGui.QDialog):
    
    def __init__(self, message, parent=None):
        super(JobsInfo, self).__init__(parent)
        
        self.initUI(message)

    def initUI(self, message):
        
        okButton = QtGui.QPushButton("OK")
        cancelButton = QtGui.QPushButton("Cancel")
        
        okButton.clicked.connect(self.ok)
        cancelButton.clicked.connect(self.cancel)

        reviewEdit = QtGui.QTextEdit()
        reviewEdit.setReadOnly(True)
        reviewEdit.setText(message)

        grid = QtGui.QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(reviewEdit, 1, 1, 1, 3)
        grid.addWidget(okButton, 2, 2)
        grid.addWidget(cancelButton, 2, 3)

        grid.setColumnStretch(1,1)
        
        self.setLayout(grid) 
        
        self.setWindowTitle('movies2anki [Batch Processing]')
        self.setModal(True)

        self.setMinimumSize(400, 300)

    def ok(self):
        self.done(1)

    def cancel(self):
        self.done(0)

class Example(QtGui.QMainWindow):
    
    def __init__(self):
        super(Example, self).__init__()
        
        self.model = Model()
        self.audio_streams = []
        self.directory = self.model.input_directory
        
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
        self.deckComboBox.editTextChanged.connect(self.setDeckName)
        self.previewButton.clicked.connect(self.preview)
        self.startButton.clicked.connect(self.start)
        self.timeSpinBox.valueChanged.connect(self.setTimeDelta)
        self.splitPhrasesSpinBox.valueChanged.connect(self.setPhrasesDurationLimit)
        self.widthSpinBox.valueChanged.connect(self.setVideoWidth)
        self.heightSpinBox.valueChanged.connect(self.setVideoHeight)
        self.startSpinBox.valueChanged.connect(self.setShiftStart)
        self.endSpinBox.valueChanged.connect(self.setShiftEnd)
        self.movieRadioButton.toggled.connect(self.setMovieMode)
        self.phrasesRadioButton.toggled.connect(self.setPhrasesMode)

        self.videoEdit.textChanged.connect(self.changeVideoFile)
        self.subsEngEdit.textChanged.connect(self.changeEngSubs)
        self.subsRusEdit.textChanged.connect(self.changeRusSubs)
        self.outDirEdit.textChanged.connect(self.changeOutDir)
        # ---------------------------------------------------
        vbox.addStretch(1)

        w.setLayout(vbox)
        
        self.setCentralWidget(w)

        self.adjustSize()
        self.setWindowTitle('movies2anki')
        self.show()

    def closeEvent(self, event):
        # save settings
        self.model.save_settings()
        
        QtGui.QMainWindow.closeEvent(self, event)

    def showVideoFileDialog(self):
        fname = unicode(QtGui.QFileDialog.getOpenFileName(directory = self.directory, filter = "Video Files (*.avi *.mkv *.mp4 *.ts);;All files (*.*)"))
        self.videoEdit.setText(fname)

    def showSubsEngFileDialog(self):
        fname = unicode(QtGui.QFileDialog.getOpenFileName(directory = self.directory, filter = "Subtitle Files (*.srt)"))
        self.subsEngEdit.setText(fname)

        self.directory = os.path.dirname(fname)

    def showSubsRusFileDialog(self):
        fname = unicode(QtGui.QFileDialog.getOpenFileName(directory = self.directory, filter = "Subtitle Files (*.srt)"))
        self.subsRusEdit.setText(fname)

        self.directory = os.path.dirname(fname)

    def showOutDirectoryDialog(self):
        fname = unicode(QtGui.QFileDialog.getExistingDirectory(directory = self.model.output_directory))

        if len(fname) != 0:
            self.model.output_directory = fname

        self.outDirEdit.setText(self.model.output_directory)

    def showErrorDialog(self, message):
        QtGui.QMessageBox.critical(self, "movies2anki", message)

    def showDirAlreadyExistsDialog(self, dir):
        reply = QtGui.QMessageBox.question(self, "movies2anki",
            "Folder '" + dir + "' already exists. Do you want to overwrite it?", QtGui.QMessageBox.Yes | 
            QtGui.QMessageBox.No, QtGui.QMessageBox.No)

        if reply == QtGui.QMessageBox.Yes:
            return True
            
        return False
        
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
        self.audio_streams = []
        
        if "*" in video_file or "?" in video_file:
            glob_results = find_glob_files(video_file)

            if len(glob_results) == 0:
                print "Video file not found"
                return
            else:
                video_file = glob_results[0]  

        elif not os.path.isfile(video_file):
            print "Video file not found"
            return

        try:
            output = check_output(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", video_file.encode(sys.getfilesystemencoding())], **subprocess_args(False))
        except OSError as ex:
            self.model.audio_id = 0
            print "Can't find ffprobe", ex
            return

        json_data = json.loads(output)
        streams = json_data["streams"]

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

    def changeAudioStreams(self):
        self.audioIdComboBox.clear()
        self.getAudioStreams(self.model.video_file)
        self.audioIdComboBox.addItems(self.audio_streams)
        self.tryToSetEngAudio()

    def changeSubtitles(self):
        self.model.en_srt = guess_srt_file(self.model.video_file, ["*eng*.srt", "*en*.srt", ".srt"], "")
        self.subsEngEdit.setText(self.model.en_srt)

        self.model.ru_srt = guess_srt_file(self.model.video_file, ["*rus*.srt", "*ru*.srt"], "")
        self.subsRusEdit.setText(self.model.ru_srt)

    def changeVideoFile(self):
        self.model.video_file = unicode(self.videoEdit.text()).strip()
        self.directory = os.path.dirname(self.model.video_file)
        self.model.input_directory = self.directory

        self.changeAudioStreams()
        
        if not os.path.isfile(self.model.video_file):
            return

        self.model.out_en_srt = self.model.out_en_srt_suffix
        self.model.out_ru_srt = self.model.out_ru_srt_suffix
        if len(self.model.video_file) > 4:
            self.model.out_en_srt = self.model.video_file[:-3] + self.model.out_en_srt
            self.model.out_ru_srt = self.model.video_file[:-3] + self.model.out_ru_srt

        self.changeSubtitles()

    def changeEngSubs(self):
        self.model.en_srt = unicode(self.subsEngEdit.text()).strip()

    def changeRusSubs(self):
        self.model.ru_srt = unicode(self.subsRusEdit.text()).strip()

    def changeOutDir(self):
        self.model.output_directory = unicode(self.outDirEdit.text()).strip()

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
        self.model.deck_name = unicode(self.deckComboBox.currentText()).strip()

    def validateSubtitles(self):
        if len(self.model.en_srt) == 0:
            self.showErrorDialog("Add english subtitles.")
            return False

        if "*" in self.model.en_srt or "?" in self.model.en_srt:
            glob_results = find_glob_files(self.model.en_srt)

            if len(glob_results) == 0:
                print "English subtitles not found."
                return
            else:
                self.model.en_srt = glob_results[0]  

        elif not os.path.isfile(self.model.en_srt):
            print "English subtitles didn't exist."
            return False

        if len(self.model.ru_srt) != 0:
            if "*" in self.model.ru_srt or "?" in self.model.ru_srt:
                glob_results = find_glob_files(self.model.ru_srt)

                if len(glob_results) == 0:
                    print "Russian subtitles not found."
                    return
                else:
                    self.model.ru_srt = glob_results[0]  

            elif not os.path.isfile(self.model.ru_srt):
                print "Russian subtitles didn't exist."
                return False

        return True

    def preview(self):
        # save settings
        self.model.save_settings()

        if not self.validateSubtitles():
            return

        # subtitles
        self.model.create_subtitles()

        if not self.model.is_subtitles_created:
            self.showErrorDialog("Check log.txt")
            return

        if self.model.is_write_output_subtitles:
            print "Writing output subtitles with phrases..."
            self.model.write_output_subtitles()

        minutes = int(duration_longest_phrase / 60)
        seconds = int(duration_longest_phrase % 60)

        # show info dialog
        message = """English subtitles: %s
Russian subtitles: %s
Phrases: %s
The longest phrase: %s min. %s sec.""" % (self.model.num_en_subs, self.model.num_ru_subs, self.model.num_phrases, minutes, seconds)
        QtGui.QMessageBox.information(self, "Preview", message)

        self.changeEngSubs()
        self.changeRusSubs()

    def start(self):
        self.model.jobs = []
        self.model.ffmpeg_split_timestamps = []
        if "*" not in self.model.video_file and "?" not in self.model.video_file:
            self.startSingleMode()
        else:
            self.startBatchMode()

    def create_tsv_files(self):
        for video_file, en_srt, ru_srt, deck_name in self.model.jobs:
            self.model.en_srt = en_srt
            self.model.ru_srt = ru_srt
            self.model.deck_name = deck_name

            self.model.create_subtitles()
            self.model.create_tsv_file()

    def check_directories(self):
        for video_file, en_srt, ru_srt, deck_name in self.model.jobs:
            collection_dir = getNameForCollectionDirectory(self.model.output_directory, deck_name)

            if os.path.exists(collection_dir):
                if self.showDirAlreadyExistsDialog(collection_dir) == False:
                    return False
                else:
                    try:
                        print "Remove dir " + collection_dir.encode('utf-8')
                        shutil.rmtree(collection_dir)
                    except OSError as ex:
                        print ex
                        return False
        return True
        
    def startBatchMode(self):
        self.model.batch_mode = True

        self.model.tmp_video_file = self.model.video_file
        self.model.tmp_en_srt = self.model.en_srt
        self.model.tmp_ru_srt = self.model.ru_srt
        self.model.tmp_deck_name = self.model.deck_name

        deck_name_pattern = self.model.deck_name
        m = re.match(r'(.*){(#+)/(\d+)}(.*)', deck_name_pattern)
        if not m:
            self.showErrorDialog("[Batch Mode] Couldn't find {##/<number>} in deck's name.\nFor example: 'Deck s02e{##/1}'")
            return
        else:
            deck_name_prefix = m.group(1)
            deck_number_width = len(m.group(2))
            deck_number_start = int(m.group(3))
            deck_name_suffix = m.group(4)
        
        video_files = find_glob_files(self.model.video_file)
        en_srt_files = find_glob_files(self.model.en_srt)
        ru_srt_files = find_glob_files(self.model.ru_srt)

        if len(en_srt_files) != len(video_files):
            message = "The number of videos [%d] does not match the number of english subtitles [%d]." % (len(video_files), len(en_srt_files))
            self.showErrorDialog(message)
            return

        if len(ru_srt_files) < len(video_files):
            max_len = max(len(ru_srt_files), len(video_files))
            ru_srt_files = ru_srt_files + [""] * (max_len - len(ru_srt_files))

        for idx, video_file in enumerate(video_files):
            en_srt = en_srt_files[idx]
            ru_srt = ru_srt_files[idx]

            deck_number = str(deck_number_start + idx)
            deck_number = deck_number.zfill(deck_number_width)
            deck_name = deck_name_prefix + deck_number +  deck_name_suffix

            self.model.jobs.append((video_file, en_srt, ru_srt, deck_name))

        if len(self.model.ru_srt) != 0:
            message = "\n".join("%s\n%s\n%s\n%s\n" % 
                (os.path.basename(t[0]), os.path.basename(t[1]), os.path.basename(t[2]), t[3]) for t in self.model.jobs)
        else:
            message = "\n".join("%s\n%s\n%s\n" % 
                (os.path.basename(t[0]), os.path.basename(t[1]), t[3]) for t in self.model.jobs)
        ret = JobsInfo(message).exec_()
        if ret == 1:
            ret = self.check_directories()
            if ret == True:
                self.updateDeckComboBox()

                self.create_tsv_files()

                self.convert_video()

    def startSingleMode(self):
        self.model.batch_mode = False

        if not self.validateSubtitles():
            return

        # subtitles
        self.model.create_subtitles()

        if not self.model.is_subtitles_created:
            self.showErrorDialog("Check log.txt")
            return

        # tsv file
        if len(self.model.deck_name) == 0:
            self.showErrorDialog("Deck's name can't be empty.")
            return

        self.updateDeckComboBox()

        if not os.path.isdir(self.model.output_directory):
            self.showErrorDialog("Output directory didn't exist.")
            return

        # save settings
        self.model.save_settings()

        self.model.create_tsv_file()

        if len(self.model.video_file) == 0:
            self.showErrorDialog("Video file name can't be empty.")
            return

        if not os.path.isfile(self.model.video_file):
            self.showErrorDialog("Video file didn't exist.")
            return

        try:
            call(["ffmpeg", "-version"], **subprocess_args())
        except OSError as ex: 
            print "Can't find ffmpeg", ex
            self.showErrorDialog("Can't find ffmpeg.")
            return

        # create or remove & create colletion.media directory
        collection_dir = getNameForCollectionDirectory(self.model.output_directory, self.model.deck_name)
        if os.path.exists(collection_dir) and self.showDirAlreadyExistsDialog(collection_dir) == False:
            return

        ret = create_or_clean_collection_dir(collection_dir)
        if ret == False:
            self.showErrorDialog("Can't create or clean media directory. Try again in a few seconds.")
            return

        # video & audio files
        self.convert_video()

    def setProgress(self, progress):
        self.progressDialog.setValue(progress)

    def setProgressWindowTitle(self, title):
        self.progressDialog.setWindowTitle(title)

    def setProgressText(self, text):
        self.progressDialog.setLabelText(text)

    def revertModelChanges(self):
        self.model.video_file = self.model.tmp_video_file
        self.model.en_srt = self.model.tmp_en_srt
        self.model.ru_srt = self.model.tmp_ru_srt
        self.model.deck_name = self.model.tmp_deck_name

    def finishProgressDialog(self, time_diff):
        self.progressDialog.done(0)
        minutes = int(time_diff / 60)
        seconds = int(time_diff % 60)
        message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
        QtGui.QMessageBox.information(self, "movies2anki", message)

    def updateDeckComboBox(self):
        text = unicode(self.deckComboBox.currentText()).strip()
        if self.deckComboBox.findText(text) == -1:
            self.deckComboBox.addItem(text)
            self.model.recent_deck_names.append(text)
        else:
            self.model.recent_deck_names.remove(text)
            self.model.recent_deck_names.append(text)

        self.deckComboBox.clear()
        self.deckComboBox.addItems(self.model.recent_deck_names)
        self.deckComboBox.setCurrentIndex(self.deckComboBox.count()-1)

    def cancelProgressDialog(self):
        self.worker.cancel()
        if self.model.p != None:
            self.model.p.terminate()

    def displayErrorMessage(self, message):
        self.showErrorDialog(message)

    def convert_video(self):
        self.progressDialog = QtGui.QProgressDialog(self)

        self.progressDialog.setWindowTitle("Generate Video & Audio Clips")
        self.progressDialog.setCancelButtonText("Cancel")
        self.progressDialog.setMinimumDuration(0)

        progress_bar = QtGui.QProgressBar(self.progressDialog)
        progress_bar.setAlignment(QtCore.Qt.AlignCenter)
        self.progressDialog.setBar(progress_bar)

        self.worker = VideoWorker(self.model)
        self.worker.updateProgress.connect(self.setProgress)
        self.worker.updateProgressWindowTitle.connect(self.setProgressWindowTitle)
        self.worker.updateProgressText.connect(self.setProgressText)
        self.worker.jobFinished.connect(self.finishProgressDialog)
        self.worker.batchJobsFinished.connect(self.revertModelChanges)
        self.worker.errorRaised.connect(self.displayErrorMessage)

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
        self.outDirEdit.setText(self.model.output_directory)

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
        self.timeSpinBox.setRange(0, 600.0)
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
        self.splitPhrasesSpinBox.setRange(1, 6000)
        self.splitPhrasesSpinBox.setSingleStep(10)
        self.splitPhrasesSpinBox.setValue(self.model.getPhrasesDurationLimit())

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

        self.deckComboBox = QtGui.QComboBox()
        self.deckComboBox.setEditable(True)
        self.deckComboBox.setMaxCount(5)
        self.deckComboBox.setSizePolicy(QtGui.QSizePolicy.Expanding,
                QtGui.QSizePolicy.Preferred)
        self.deckComboBox.addItems(self.model.recent_deck_names)
        self.deckComboBox.clearEditText()
                
        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(self.deckComboBox)

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
    sys.stderr = open('log.txt', 'w')
    sys.stdout = sys.stderr

    os.environ["PATH"] += os.pathsep + "." + os.sep + "ffmpeg" + os.sep + "bin"

    main()
    
    sys.stderr.close()
    sys.stderr = sys.__stderr__