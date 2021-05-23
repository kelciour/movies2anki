# -*- coding: utf-8 -*-

# import the main window object (mw) from aqt
from aqt import mw
# import the "get file" tool from utils.py
from aqt.qt import *

from aqt.utils import showInfo
from anki.utils import call, noBundledLibs

from distutils.spawn import find_executable

import json
import os
import re
import shutil
import string
import sys
import time
import os

from collections import deque
from subprocess import check_output
from subprocess import Popen

import subprocess

from . import glob
from . import styles

from . import configparser

sys.path.append(os.path.join(os.path.dirname(__file__), "vendor"))

import pysubs2

if isMac and '/usr/local/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/usr/local/bin:" + os.environ['PATH']

if isMac and '/opt/homebrew/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/opt/homebrew/bin:" + os.environ['PATH']

ffprobe_executable = find_executable("ffprobe")
ffmpeg_executable = find_executable("ffmpeg")
mpv_executable = find_executable("mpv")

if mpv_executable is None and isMac:
    mpv_executable = "/Applications/mpv.app/Contents/MacOS/mpv"
    if not os.path.exists(mpv_executable):
        mpv_executable = None

# maybe a fix for macOS
# if ffprobe_executable is None:
#     ffprobe_executable = '/usr/local/bin/ffprobe'
# if ffmpeg_executable is None:
    # ffmpeg_executable = '/usr/local/bin/ffmpeg'

# anki.utils.py
if isWin:
    si = subprocess.STARTUPINFO()
    try:
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except:
        # pylint: disable=no-member
        si.dwFlags |= subprocess._subprocess.STARTF_USESHOWWINDOW
else:
    si = None

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
    split_time = re.split(r'[,\.]', time)
    major, minor = (split_time[0].split(':'), split_time[1])
    return int(major[0]) * 3600 + int(major[1]) * 60 + int(major[2]) + float(minor) / 1000

def tsv_time_to_seconds(tsv_time):
    return srt_time_to_seconds(tsv_time.replace(".", ","))

def get_time_parts(time):
    millisecs = str(time).split(".")[1][:3]
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
    reg_exp_square_braces = r"^[-\s]*\[[^\]]*\]([-\s]*\[[^\]]*\])*$"
    reg_exp_music = r"^[♪ ]*$"
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
    elif re.match(reg_exp_music, sub):
        return False

    return True

def format_subtitles(subs, is_ignore_SDH, join_lines_separator, join_sentences_separator, is_gap_phrases):
    subs2 = []
    for sub_start, sub_end, sub_text in subs:
        sub_text = re.sub(r"{\\\w+\d*}", "", sub_text)
        sub_text = re.sub(r"\t", " ", sub_text)
        sub_text = re.sub(r"\n +", "\n", sub_text)
        sub_text = re.sub(r"  +", " ", sub_text)
        sub_text = re.sub(r'<\d+:\d+:\d+\.\d+>', '', sub_text)

        sub_chunks = sub_text.split('\\N')
        sub_content = sub_chunks[0]
        for sub_line in sub_chunks[1:]:
            if sub_content[-1] not in [u".", u"?", u"!", u"？", u"！", u"♪", '"'] and not sub_line.startswith('- '):
                sub_content += join_lines_separator
            else:
                sub_content += join_sentences_separator

            sub_content += sub_line

            sub_content = sub_content.strip()

        subs2.append((sub_start, sub_end, sub_content))
    return subs2

def read_subtitles(content, is_ignore_SDH, join_lines_separator, join_sentences_separator, is_gap_phrases):
    en_subs = []
    
    content = re.sub(r'(?s)^WEBVTT.*?\n\n', '', content).strip()
    content = re.sub(r'(^(?:\d+\n)?\d+:\d+:\d+[,\.]\d+\s+-->\s+\d+:\d+:\d+[,\.]\d+)', r'#~~~~~~~~~~~~~~#\1', content, flags=re.M)
    for sub_id, sub in enumerate(content.strip().split('#~~~~~~~~~~~~~~#'), 1):
        sub = re.sub(r'\n\s*\n', '\n', sub).strip()
        if not sub:
            continue
        sub_chunks = sub.split('\n')
        if ' --> ' in sub_chunks[0]:
            sub_chunks.insert(0, sub_id)
        sub_timecode =  sub_chunks[1].split(' --> ')
        sub_start = srt_time_to_seconds(sub_timecode[0].strip())
        sub_end = srt_time_to_seconds(sub_timecode[1].strip())
        if len(sub_chunks) >= 3:
            # sub_content = join_lines_separator.join(sub_chunks[2:])

            sub_content = sub_chunks[2:][0]
            for sub_line in sub_chunks[2:][1:]:
                if sub_content[-1] not in [u".", u"?", u"!", u"？", u"！", u"♪", '"'] and not sub_line.startswith('- '):
                    sub_content += join_lines_separator
                else:
                    sub_content += join_sentences_separator
                sub_content += sub_line

            sub_content = re.sub(r"{\\\w+\d*}", "", sub_content)
            sub_content = re.sub(r"\t", " ", sub_content)
            sub_content = re.sub(r"\n +", "\n", sub_content)
            sub_content = re.sub(r"  +", " ", sub_content)
            sub_content = sub_content.strip()

            if len(sub_content) > 0:
                if not is_ignore_SDH:
                    en_subs.append((sub_start, sub_end, sub_content))
                else:
                    if is_not_sdh_subtitle(sub_content):
                        en_subs.append((sub_start, sub_end, sub_content))
                    # else:
                    #     print "Ignore subtitle: %s" % repr(sub_content)
            else:
                if not is_gap_phrases:
                    en_subs.append((sub_start, sub_end, sub_content))
            #     print "Empty subtitle: %s" % repr(sub)
        else:
            pass
        #     print "Ignore empty subtitle: %s" % repr(sub)
   
    return en_subs

# Формат субтитров
# [(start_time, end_time, subtitle), (), ...], [(...)], ...
def join_lines_within_subs(subs, join_sentences_separator):
    subs_joined = []

    global duration_longest_phrase
    duration_longest_phrase = 0

    for sub in subs:
        sub_start = sub[0][0]
        sub_end = sub[-1][1]

        sub_content = join_sentences_separator.join(s[2] for s in sub)
        
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

def remove_tags(sub):
    sub = re.sub(r"<[^>]+>", "", sub)
    sub = re.sub(r"  +", " ", sub)
    sub = sub.strip()

    return sub

def convert_into_sentences(en_subs, phrases_duration_limit, join_lines_that_end_with, join_questions_with_answers, join_sentences_separator, join_lines_separator, is_gap_phrases, is_split_long_phrases):
    subs = []

    if phrases_duration_limit == 0 or not is_split_long_phrases:
        sentence_duration_limit = 15
    else:
        sentence_duration_limit = phrases_duration_limit

    for sub in en_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content_original = sub[2]

        sub_content = remove_tags(sub_content_original)

        if not sub_content:
            continue

        if len(subs) > 0: 
            prev_sub_start = subs[-1][0]
            prev_sub_end = subs[-1][1]
            prev_sub_content_original = subs[-1][2]

            prev_sub_content = remove_tags(prev_sub_content_original)

            flag = False
            for regex in join_lines_that_end_with.split():
                if (sub_content[0].isalpha() and sub_content[0].islower()) or re.search(regex + r"$", prev_sub_content):
                    flag = True
                    break

            if not is_gap_phrases:
                subs.append((sub_start, sub_end, sub_content_original))
            elif (prev_sub_content.endswith(u"?") or prev_sub_content.endswith(u"？")) and join_questions_with_answers and (sub_start - prev_sub_end) <= 5:
                subs[-1] = (prev_sub_start, sub_end, prev_sub_content_original + join_sentences_separator + sub_content_original)
            elif flag and (sub_end - prev_sub_start) <= sentence_duration_limit:
                subs[-1] = (prev_sub_start, sub_end, prev_sub_content_original + join_lines_separator + sub_content_original)
            else:
                subs.append((sub_start, sub_end, sub_content_original))
        else:
            subs.append((sub_start, sub_end, sub_content_original))

    return subs

# Unused
def convert_into_sentences_source(en_subs, phrases_duration_limit):
    subs = []

    for sub in en_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content_original = sub[2]

        sub_content = remove_tags(sub_content_original)

        if len(subs) > 0: 
            prev_sub_start = subs[-1][0]
            prev_sub_end = subs[-1][1]
            prev_sub_content_original = subs[-1][2]

            prev_sub_content = remove_tags(prev_sub_content_original)

            if ((sub_start - prev_sub_end) <= 2 and (sub_end - prev_sub_start) < phrases_duration_limit and 
                sub_content[0] != '-' and
                sub_content[0] != '"' and
                sub_content[0] != u'♪' and
                (prev_sub_content[-1] != '.' or (sub_content[0:3] == '...' or (prev_sub_content[-3:] == '...' and sub_content[0].islower()))) and 
                prev_sub_content[-1] != '?' and
                prev_sub_content[-1] != '!' and
                prev_sub_content[-1] != ']' and
                prev_sub_content[-1] != ')' and
                prev_sub_content[-1] != u'♪' and
                prev_sub_content[-1] != '"' and
                (sub_content[0].islower() or sub_content[0].isdigit())):

                subs[-1] = (prev_sub_start, sub_end, prev_sub_content_original + " " + sub_content_original)
            else:
                subs.append((sub_start, sub_end, sub_content_original))
        else:
            subs.append((sub_start, sub_end, sub_content_original))

    return subs

def convert_into_phrases(en_subs, time_delta, phrases_duration_limit, is_split_long_phrases, join_sentences_separator):
    subs = []

    for sub in en_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content = sub[2]

        if ( time_delta > 0 and len(subs) > 0 and (sub_start - prev_sub_end) < time_delta ):
            subs[-1].append((sub_start, sub_end, sub_content))
        else:
            subs.append([(sub_start, sub_end, sub_content)])

        prev_sub_end = sub_end

    if is_split_long_phrases:
        subs = split_long_phrases(subs, phrases_duration_limit)
        
    subs_with_line_timings = subs

    subs = join_lines_within_subs(subs, join_sentences_separator)
    return (subs, subs_with_line_timings)

# TODO
def sync_subtitles(en_subs, ru_subs, join_sentences_separator, join_lines_that_end_with, join_lines_separator):
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
                    if ru_sub_end - en_sub_start >= 0.35: # TODO
                        sub_content.append(ru_sub_content)
                elif ru_sub_end >= en_sub_end:
                    sub_content.append(ru_sub_content) 
            elif ru_sub_start >= en_sub_start and ru_sub_start < en_sub_end:
                if ru_sub_end <= en_sub_end:
                    sub_content.append(ru_sub_content)
                elif ru_sub_end > en_sub_end:
                    if en_sub_end - ru_sub_start >= 0.35: # TODO
                        sub_content.append(ru_sub_content)

    tmp_subs = subs
    subs = []

    for sub in tmp_subs:
        sub_start = sub[0]
        sub_end = sub[1]
        sub_content = []
        for sub_line in sub[2]:
            if not sub_content:
                sub_content.append(sub_line)
                continue
            flag = False
            for regex in join_lines_that_end_with.split():
                if re.search(regex + r"$", sub_content[-1]):
                    flag = True
                    break
            if flag and not sub_line.startswith('- '):
                sub_content.append(join_lines_separator)
            else:
                sub_content.append(join_sentences_separator)
            sub_content.append(sub_line)
        sub_content = ''.join(sub_content)

        subs.append((sub_start, sub_end, sub_content))

    return subs

def add_pad_timings_between_phrases(subs, shift_start, shift_end):
    for idx in range(len(subs)):
        (start_time, end_time, subtitle) = subs[idx]
        subs[idx] = (start_time - shift_start, end_time + shift_end, subtitle)
    
    (start_time, end_time, subtitle) = subs[0]
    if start_time < 0:
        subs[0] = (0.0, end_time, subtitle)

def add_empty_subtitle(subs):
    (start_time, end_time, subtitle) = subs[0][0]
    if start_time > 15:
        subs.insert(0, [(0.0, start_time, "")])

def change_subtitles_ending_time(subs, duration):
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
    subs[-1] = (start_time, duration, subtitle)

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
            # print ("Found subtitle: " + glob_result[0]).encode('utf-8')
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
    # try:
    #     if os.path.exists(directory):
    #         # print "Remove dir " + directory.encode('utf-8')
    #         shutil.rmtree(directory)
    #         time.sleep(0.5)
    
    #     # print "Create dir " + directory.encode('utf-8')
    #     os.makedirs(directory)
    # except OSError as ex:
    #     # print ex
    #     return False

    return True

class Model(object):
    def __init__(self):
        self.config_file_name = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        
        self.video_file = ""
        self.audio_id = 0
        self.deck_name = ""
        self.model_name = "movies2anki (add-on)"
        self.default_model_names = ["movies2anki (add-on)", "movies2anki - subs2srs", "movies2anki - subs2srs (video)", "movies2anki - subs2srs (audio)"]

        self.en_srt = ""
        self.ru_srt = ""

        self.out_en_srt_suffix = "out.en.srt"
        self.out_ru_srt_suffix = "out.ru.srt"

        self.out_en_srt = "out.en.srt"
        self.out_ru_srt = "out.ru.srt"

        self.encodings = ["utf-8", "cp1251", "utf-16"]
        self.sub_encoding = None
        
        self.p = None

        self.load_settings()

    def default_settings(self):
        self.input_directory = os.path.expanduser("~")
        self.output_directory = mw.col.media.dir()

        self.time_delta = 0.00

        self.is_split_long_phrases = False
        self.is_gap_phrases = True
        self.phrases_duration_limit = 60

        self.video_width = -2
        self.video_height = 320

        self.shift_start = 0.25
        self.shift_end = 0.25

        self.mode = "Phrases"

        self.recent_deck_names = deque(maxlen = 5)

        self.is_write_output_subtitles = False
        self.is_write_output_subtitles_for_clips = False
        self.is_create_clips_with_softsub = False
        self.is_create_clips_with_hardsub = False
        self.hardsub_style = "FontName=Arial,FontSize=24,OutlineColour=&H5A000000,BorderStyle=3"
        self.is_ignore_sdh_subtitle = True
        self.is_add_dir_to_media_path = False

        # self.join_lines_that_end_with = r"\.\.\. , → [\u4e00-\u9fef]"
        self.join_lines_that_end_with = r"\.\.\. , →"
        self.join_lines_separator = " "
        self.join_sentences_separator = "<br>"
        self.join_questions_with_answers = False

    def load_settings(self):
        self.default_settings()

        if not os.path.isfile(self.config_file_name):
            return

        config = configparser.SafeConfigParser()
        config.read(self.config_file_name, encoding='utf-8')

        self.input_directory = config.get('main', 'input_directory')
        # self.output_directory = config.get('main', 'output_directory')
        # self.video_width = config.getint('main', 'video_width')
        # self.video_height = config.getint('main', 'video_height')
        self.shift_start = config.getfloat('main', 'pad_start')
        self.shift_end = config.getfloat('main', 'pad_end')
        self.time_delta = config.getfloat('main', 'gap_between_phrases')
        self.is_split_long_phrases = config.getboolean('main', 'is_split_long_phrases')
        self.is_gap_phrases = config.getboolean('main', 'is_gap_phrases')
        self.phrases_duration_limit = config.getint('main', 'phrases_duration_limit')
        self.mode = config.get('main', 'mode')
        self.is_write_output_subtitles = config.getboolean('main', 'is_write_output_subtitles')
        # self.is_write_output_subtitles_for_clips = config.getboolean('main', 'is_write_output_subtitles_for_clips')
        # self.is_create_clips_with_softsub = config.getboolean('main', 'is_create_clips_with_softsub')
        # self.is_create_clips_with_hardsub = config.getboolean('main', 'is_create_clips_with_hardsub')
        # self.hardsub_style = config.get('main', 'hardsub_style')
        self.is_ignore_sdh_subtitle = config.getboolean('main', 'is_ignore_sdh_subtitle')
        # self.is_add_dir_to_media_path = config.getboolean('main', 'is_add_dir_to_media_path')

        self.join_lines_that_end_with = config.get('main', 'join_lines_that_end_with').encode('utf-8').decode('unicode-escape').strip()
        self.join_lines_separator = config.get('main', 'join_lines_separator').replace("_", " ")
        self.join_sentences_separator = config.get('main', 'join_sentences_separator').replace("_", " ")
        self.join_questions_with_answers = config.getboolean('main', 'join_questions_with_answers')
        
        value = [e.strip() for e in config.get('main', 'recent_deck_names').split(',')]
        if len(value) != 0:
            self.recent_deck_names.extendleft(value)

    def save_settings(self):
        config = configparser.SafeConfigParser()
        config.add_section('main')
        config.set('main', 'input_directory', self.input_directory)
        # config.set('main', 'output_directory', self.output_directory.encode('utf-8'))
        # config.set('main', 'video_width', str(self.video_width))
        # config.set('main', 'video_height', str(self.video_height))
        config.set('main', 'pad_start', str(self.shift_start))
        config.set('main', 'pad_end', str(self.shift_end))
        config.set('main', 'gap_between_phrases', str(self.time_delta))
        config.set('main', 'is_split_long_phrases', str(self.is_split_long_phrases))
        config.set('main', 'is_gap_phrases', str(self.is_gap_phrases))
        config.set('main', 'phrases_duration_limit', str(self.phrases_duration_limit))
        config.set('main', 'mode', self.mode)
        config.set('main', 'is_write_output_subtitles', str(self.is_write_output_subtitles))
        # config.set('main', 'is_write_output_subtitles_for_clips', str(self.is_write_output_subtitles_for_clips))
        # config.set('main', 'is_create_clips_with_softsub', str(self.is_create_clips_with_softsub))
        # config.set('main', 'is_create_clips_with_hardsub', str(self.is_create_clips_with_hardsub))
        # config.set('main', 'hardsub_style', self.hardsub_style.encode('utf-8'))
        config.set('main', 'is_ignore_sdh_subtitle', str(self.is_ignore_sdh_subtitle))
        # config.set('main', 'is_add_dir_to_media_path', str(self.is_add_dir_to_media_path))

        config.set('main', 'join_lines_that_end_with', self.join_lines_that_end_with.encode('unicode-escape').decode('utf-8'))
        config.set('main', 'join_lines_separator', self.join_lines_separator.replace(" ", "_"))
        config.set('main', 'join_sentences_separator', self.join_sentences_separator.replace(" ", "_"))
        config.set('main', 'join_questions_with_answers', str(self.join_questions_with_answers))
        
        config.set('main', 'recent_deck_names', ",".join(reversed(self.recent_deck_names)))
  
        with open(self.config_file_name, 'w', encoding='utf-8') as f:
            config.write(f)

    def guess_encoding(self, file_content):
        if file_content[:3] == b'\xef\xbb\xbf': # with bom
            file_content = file_content[3:]
            return file_content, 'utf-8'
        try:
            # https://github.com/chardet/chardet/pull/109
            import chardet_with_utf16_fix
            enc = chardet_with_utf16_fix.detect(file_content)['encoding']
            return file_content, enc
        except:
            pass
        return file_content, None

    def convert_to_unicode(self, file_content):
        file_content, enc = self.guess_encoding(file_content)
        if enc:
            if enc in self.encodings:
                self.encodings.remove(enc)
            self.encodings.insert(0, enc)
        for enc in self.encodings:
            try:
                content = file_content.decode(enc)
                self.sub_encoding = enc
                return content
            except UnicodeDecodeError:
                pass
        self.sub_encoding = None
        return file_content.decode()

    def load_subtitle(self, filename, is_ignore_SDH, join_lines_separator, join_sentences_separator, is_gap_phrases):
        if len(filename) == 0:
            return []

        file_content = open(filename, 'rb').read()

        file_content, enc = self.guess_encoding(file_content)

        subs = pysubs2.load(filename, encoding=enc)

        subs.sort()

        subs2 = []
        for line in subs:
            subs2.append((line.start / 1000, line.end / 1000, line.text))

        subs2 = format_subtitles(subs2, is_ignore_SDH, join_lines_separator, join_sentences_separator, is_gap_phrases)

        return subs2

        ## Конвертируем субтитры в Unicode
        # file_content = self.convert_to_unicode(file_content)

        # file_content = file_content.replace('\r\n', '\n')

        ## Оставляем только одну пустую строку между субтитрами
        # file_content = fix_empty_lines(file_content)

        ## Читаем субтитры
        # return read_subtitles(file_content, is_ignore_SDH, join_lines_separator, join_sentences_separator, is_gap_phrases)

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

    def create_new_default_model(self):
        model = mw.col.models.new(self.model_name)
        model['css'] = styles.css.strip()
        mw.col.models.addField(model, mw.col.models.newField("Id"))
        mw.col.models.addField(model, mw.col.models.newField("Source"))
        mw.col.models.addField(model, mw.col.models.newField("Path"))
        mw.col.models.addField(model, mw.col.models.newField("Audio"))
        mw.col.models.addField(model, mw.col.models.newField("Video"))
        mw.col.models.addField(model, mw.col.models.newField("Expression"))
        mw.col.models.addField(model, mw.col.models.newField("Meaning"))
        mw.col.models.addField(model, mw.col.models.newField("Notes"))
        t = mw.col.models.newTemplate("Card 1")
        t['qfmt'] = styles.front_template.strip()
        t['afmt'] = styles.back_template.strip()
        mw.col.models.addTemplate(model, t)
        mw.col.models.add(model)

    def create_subs2srs_default_model(self):
        model = mw.col.models.new(self.model_name)
        if "subs2srs (video)" in self.model_name:
            model['css'] = styles.subs2srs_video_css.strip()
        else:
            model['css'] = styles.subs2srs_css.strip()
        
        mw.col.models.addField(model, mw.col.models.newField("Id"))
        mw.col.models.addField(model, mw.col.models.newField("Source"))
        mw.col.models.addField(model, mw.col.models.newField("Path"))
        mw.col.models.addField(model, mw.col.models.newField("Audio"))
        mw.col.models.addField(model, mw.col.models.newField("Video"))
        mw.col.models.addField(model, mw.col.models.newField("Expression"))
        mw.col.models.addField(model, mw.col.models.newField("Meaning"))
        mw.col.models.addField(model, mw.col.models.newField("Notes"))
        if "subs2srs (audio)" not in self.model_name:
            mw.col.models.addField(model, mw.col.models.newField("Snapshot"))
        if "subs2srs (video)" in self.model_name:
            mw.col.models.addField(model, mw.col.models.newField("Video Sound"))

        t = mw.col.models.newTemplate("Card 1")
        if self.model_name == "movies2anki - subs2srs (video)":
            t['qfmt'] = styles.subs2srs_video_front_template.strip()
            t['afmt'] = styles.subs2srs_video_back_template.strip()
        elif self.model_name == "movies2anki - subs2srs (audio)":
            t['qfmt'] = styles.subs2srs_audio_front_template.strip()
            t['afmt'] = styles.subs2srs_audio_back_template.strip()
        else:
            t['qfmt'] = styles.subs2srs_front_template.strip()
            t['afmt'] = styles.subs2srs_back_template.strip()

        mw.col.models.addTemplate(model, t)
        mw.col.models.add(model)

    def write_tsv_file(self, deck_name, en_subs, ru_subs, directory):
        # prefix = format_filename(deck_name)
        prefix = format_filename(os.path.splitext(os.path.basename(self.video_file))[0])
        # filename = os.path.join(directory, prefix + ".tsv")
        
        # f_out = open(filename, 'w')

        if not mw.col.models.byName(self.model_name):
            if self.model_name.startswith("movies2anki - subs2srs"):
                self.create_subs2srs_default_model()
            else:
                self.create_new_default_model()

        config = mw.addonManager.getConfig(__name__)

        ffmpeg_split_timestamps = []
        for idx in range(len(en_subs)):
            start_time = seconds_to_tsv_time(en_subs[idx][0])
            end_time = seconds_to_tsv_time(en_subs[idx][1])

            en_sub = en_subs[idx][2]
            en_sub = re.sub('\n', '<br>', en_sub)
            en_sub = escape_double_quotes(en_sub)
            
            ru_sub = ru_subs[idx][2]
            ru_sub = re.sub('\n', '<br>', ru_sub)
            ru_sub = escape_double_quotes(ru_sub)

            tag = prefix
            sequence = str(idx + 1).zfill(3) + "_" + start_time

            filename_suffix = ""
            if self.is_create_clips_with_hardsub:
                filename_suffix = ".sub"

            sound = prefix + "_" + start_time + "-" + end_time + ".mp3"
            video = prefix + "_" + start_time + "-" + end_time + filename_suffix + "." + config["video extension"]
               
            if self.is_add_dir_to_media_path:
                sound = prefix + ".media/" + sound
                video = prefix + ".media/" + video

            # New Anki Card
            model = mw.col.models.byName(self.model_name)
            mw.col.models.setCurrent(model)

            note = mw.col.newNote(forDeck=False)

            note["Id"] = prefix + "_" + start_time + "-" + end_time
            note["Source"] = os.path.splitext(os.path.basename(self.video_file))[0]
            note["Path"] = self.video_file
            # note["Audio"] = "[sound:" + sound + "]"
            note["Audio"] = sound
            note["Video"] = video
            note["Expression"] = en_sub          
            note["Meaning"] = ru_sub

            snapshot_time_ffmpeg = None
            snapshot_time_filename = None
            if self.model_name.startswith("movies2anki - subs2srs") and "subs2srs (audio)" not in self.model_name:
                if self.model_name == "movies2anki - subs2srs (video)":
                    snapshot_time_seconds = en_subs[idx][0]
                else:
                    snapshot_time_seconds = en_subs[idx][0] + ((en_subs[idx][1] - en_subs[idx][0]) / 2.0)
                snapshot_time_ffmpeg = seconds_to_ffmpeg_time(snapshot_time_seconds)
                # snapshot_time_filename = prefix + "_" + seconds_to_tsv_time(snapshot_time_seconds) + ".jpg"
                snapshot_time_filename = prefix + "_" + start_time + "-" + end_time + ".jpg"
                note["Snapshot"] = '<img src="%s">' % snapshot_time_filename

            # if self.model_name == "movies2anki - subs2srs (video)":
            #     note["Video Sound"] = "[sound:{}]".format(video)
                # note["Video Sound"] = "[sound:{}]".format(video.replace('.mp4', '.webm'))

            # ret = note.dupeOrEmpty()
            # if ret == 2:
            #     continue

            did = mw.col.decks.id(self.deck_name)
            note.model()['did'] = did

            if mw.state == "deckBrowser":
                mw.col.decks.select(did)

            mw.col.addNote(note)

            # f_out.write(self.encode_str(tag + "\t" + sequence + "\t[sound:" + sound + "]\t[sound:" + video + "]\t"))
            # f_out.write(self.encode_str(en_sub))
            # f_out.write(self.encode_str("\t"))
            # f_out.write(self.encode_str(ru_sub))
            # f_out.write(self.encode_str('\n'))
            
            if self.model_name.startswith("movies2anki - subs2srs"):
                ffmpeg_split_timestamps.append((prefix + "_" + start_time + "-" + end_time, 
                    seconds_to_ffmpeg_time(en_subs[idx][0]), 
                    seconds_to_ffmpeg_time(en_subs[idx][1]),
                    snapshot_time_ffmpeg, snapshot_time_filename))
            else:
                ffmpeg_split_timestamps.append((prefix + "_" + start_time + "-" + end_time, 
                    seconds_to_ffmpeg_time(en_subs[idx][0]), 
                    seconds_to_ffmpeg_time(en_subs[idx][1])))
        
        mw.reset()

        # f_out.close()

        return ffmpeg_split_timestamps

    def create_subtitles(self):
        # print "--------------------------"
        # print "Video file: %s" % self.video_file.encode('utf-8')
        # print "Audio id: %s" % self.audio_id
        # print "English subtitles: %s" % self.en_srt.encode('utf-8')
        # print "Russian subtitles: %s" % self.ru_srt.encode('utf-8')
        # print "English subtitles output: %s" % self.out_en_srt.encode('utf-8')
        # print "Russian subtitles output: %s" % self.out_ru_srt.encode('utf-8')
        # print "Write output subtitles: %s" % self.is_write_output_subtitles
        # print "Write output subtitles for clips: %s" % self.is_write_output_subtitles_for_clips
        # print "Create clips with softsub: %s" % self.is_create_clips_with_softsub
        # print "Create clips with hardsub: %s" % self.is_create_clips_with_hardsub
        # print "Style for hardcoded subtitles: %s" % self.hardsub_style
        # print "Ignore SDH subtitles: %s" % self.is_ignore_sdh_subtitle
        # print "Output Directory: %s" % self.output_directory.encode('utf-8')
        # print "Video width: %s" % self.video_width
        # print "Video height: %s" % self.video_height
        # print "Pad start: %s" % self.shift_start
        # print "Pad end: %s" % self.shift_end
        # print "Gap between phrases: %s" % self.time_delta
        # print "Split Long Phrases: %s" % self.is_split_long_phrases
        # print "Max length phrases: %s" % self.phrases_duration_limit
        # print "Mode: %s" % self.mode
        # print "Deck name: %s" % self.deck_name.encode('utf-8')
        # print "--------------------------"

        self.is_subtitles_created = False

        # Загружаем английские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        # print "Loading English subtitles..."
        en_subs = self.load_subtitle(self.en_srt, self.is_ignore_sdh_subtitle, self.join_lines_separator, self.join_sentences_separator, self.is_gap_phrases)
        # print "Encoding: %s" % self.sub_encoding 
        # print "English subtitles: %s" % len(en_subs)

        # Разбиваем субтитры на предложения
        self.en_subs_sentences = convert_into_sentences(en_subs, self.phrases_duration_limit, self.join_lines_that_end_with, self.join_questions_with_answers, self.join_sentences_separator, self.join_lines_separator, self.is_gap_phrases, self.is_split_long_phrases)
        # print "English sentences: %s" % len(self.en_subs_sentences)

        # Разбиваем субтитры на фразы
        self.en_subs_phrases, self.subs_with_line_timings = convert_into_phrases(self.en_subs_sentences, self.time_delta, self.phrases_duration_limit, self.is_split_long_phrases, self.join_sentences_separator)
        # print "English phrases: %s" % len(self.en_subs_phrases)

        # Загружаем русские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
        # print "Loading Russian subtitles..."
        ru_subs = self.load_subtitle(self.ru_srt, self.is_ignore_sdh_subtitle, self.join_lines_separator, self.join_sentences_separator, is_gap_phrases=True)
        # print "Encoding: %s" % self.sub_encoding 
        # print "Russian subtitles: %s" % len(ru_subs)

        # Для preview диалога
        self.num_en_subs = len(en_subs)
        self.num_ru_subs = len(ru_subs)
        self.num_phrases = len(self.en_subs_phrases)

        # Синхронизируем русские субтитры с получившимися английскими субтитрами
        # print "Syncing Russian subtitles with English phrases..."
        self.ru_subs_phrases = sync_subtitles(self.en_subs_phrases, ru_subs, self.join_sentences_separator, self.join_lines_that_end_with, self.join_lines_separator)

        # Добавляем смещения к каждой фразе
        # print "Adding Pad Timings between English phrases..."
        add_pad_timings_between_phrases(self.en_subs_phrases, self.shift_start, self.shift_end)

        # print "Adding Pad Timings between Russian phrases..."
        add_pad_timings_between_phrases(self.ru_subs_phrases, self.shift_start, self.shift_end)

        if self.mode == "Movie":
            with noBundledLibs():
                if ffprobe_executable is not None:
                    output = check_output([ffprobe_executable, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", self.video_file], startupinfo=si, encoding='utf-8')
                else:
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${=duration}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--no-config", "--", self.video_file], startupinfo=si, encoding='utf-8')

            self.duration = float(output.strip())
            
            # Меняем длительность фраз в английских субтитрах
            # print "Changing duration English subtitles..."
            change_subtitles_ending_time(self.en_subs_phrases, self.duration)
            add_empty_subtitle(self.subs_with_line_timings)

            # Меняем длительность фраз в русских субтитрах
            # print "Changing duration Russian subtitles..."
            change_subtitles_ending_time(self.ru_subs_phrases, self.duration)

        self.is_subtitles_created = True

    def write_output_subtitles(self):
        # Записываем английские субтитры
        # print "Writing English subtitles..."
        self.write_subtitles(self.out_en_srt, self.en_subs_phrases)

        # Записываем русские субтитры
        # print "Writing Russian subtitles..."
        self.write_subtitles(self.out_ru_srt, self.ru_subs_phrases)

    def create_tsv_file(self):
        # Формируем tsv файл для импорта в Anki
        # print "Writing tsv file..."
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

class VideoWorker(QThread):

    updateProgress = pyqtSignal(int)
    updateProgressWindowTitle = pyqtSignal(str)
    updateProgressText = pyqtSignal(str)
    jobFinished = pyqtSignal(float)
    batchJobsFinished = pyqtSignal()
    errorRaised = pyqtSignal(str)

    def __init__(self, data):
        QThread.__init__(self)

        self.model = data
        self.canceled = False

    def cancel(self):
      self.canceled = True

    def run(self):
        self.video_resolution = str(self.model.video_width) + ":" + str(self.model.video_height)

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

                # collection_dir = getNameForCollectionDirectory(self.model.output_directory, self.model.deck_name)
                # ret = create_collection_dir(collection_dir)
                # if ret == False:
                #     self.errorRaised.emit("Can't create media directory.")
                #     self.canceled = True
                #     break

                self.updateProgressWindowTitle.emit("Generating Cards [%s/%s]" % (idx + 1, len(self.model.jobs)))
            else:
                ffmpeg_split_timestamps = self.model.ffmpeg_split_timestamps[idx]

            last_update = None
            prefix = format_filename(os.path.splitext(os.path.basename(self.model.video_file))[0])
            # prefix = format_filename(self.model.deck_name)
            for i in range(len(ffmpeg_split_timestamps)):
                if self.canceled:
                    break

                chunk = ffmpeg_split_timestamps[i]
                
                # Seems to be a working fix for progressbar window beeing stuck and app crash on Windows 10 x64
                # Anki 2.1.15 (442df9d6)
                # Qt 5.12.1 PyQt 5.11.3
                # TODO Maybe use aqt.progress.ProgressDialog?
                if last_update is None or time.time() - last_update > 0.5:
                    last_update = time.time()
                    self.updateProgress.emit((num_files_completed * 1.0 / num_files) * 100)
                
                filename = mw.col.media.dir() + os.sep + chunk[0]            
                # filename = self.model.output_directory + os.sep + prefix + ".media" + os.sep + chunk[0]
                ss = chunk[1]
                to = chunk[2]

                t = tsv_time_to_seconds(to) - tsv_time_to_seconds(ss)

                af_d = 0.25
                af_st = 0
                af_to = t - af_d
                af_params = "afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(af_st, af_d, af_to, af_d)

                # print ss
                self.updateProgressText.emit(ss)

                # clip subtitles
                if self.model.is_write_output_subtitles_for_clips or self.model.is_create_clips_with_softsub or self.model.is_create_clips_with_hardsub:
                    with open(filename + ".srt", 'w') as f_sub:
                        clip_subs = self.model.subs_with_line_timings[i]
                        clip_sub_shift = tsv_time_to_seconds(ss)

                        for sub_id in range(len(clip_subs)):
                            f_sub.write(self.model.encode_str(str(sub_id+1) + "\n"))
                            f_sub.write(self.model.encode_str(seconds_to_srt_time(clip_subs[sub_id][0] - clip_sub_shift) + " --> " + seconds_to_srt_time(clip_subs[sub_id][1] - clip_sub_shift) + "\n"))
                            f_sub.write(self.model.encode_str(clip_subs[sub_id][2] + "\n"))
                            f_sub.write(self.model.encode_str("\n"))
                
                vf = "scale=" + self.video_resolution
                if self.model.is_create_clips_with_hardsub:
                    srt_style = self.model.hardsub_style
                    srt_filename = os.path.abspath(filename + ".srt")
                    if srt_filename[1] == ":": # Windows
                        srt_filename = srt_filename.replace("\\", "/")
                        srt_filename = srt_filename.replace(":", "\\\\:")
                    vf += ",subtitles=" + srt_filename + ":force_style='" + srt_style + "'"

                softsubs_options = ""
                softsubs_map = ""
                if self.model.is_create_clips_with_softsub:
                    softsubs_options = "-i" + " " + '"' + filename + ".srt" + '"' + " " + "-c:s mov_text"
                    softsubs_map = "-map 1:0"

                filename_suffix = ""
                if self.model.is_create_clips_with_hardsub:
                    filename_suffix = ".sub"

                if self.model.model_name.startswith("movies2anki - subs2srs") and "subs2srs (audio)" not in self.model.model_name:
                    snapshot_time = chunk[3]
                    snapshot_filename = chunk[4]

                    self.model.p = None
                    cmd = [ffmpeg_executable, "-y", "-ss", snapshot_time, "-i", self.model.video_file, "-loglevel", "quiet", "-vf", "scale={}:{}".format(-2, self.model.video_height), "-vframes", "1", "-q:v", "2", snapshot_filename]
                    call(cmd)
                    # self.model.p = Popen(cmd, shell=True, **subprocess_args())
                    # self.model.p.wait()

                # if self.model.model_name == "movies2anki - subs2srs (video)":
                #     self.model.p = None
                #     cmd = ["ffmpeg", "-ss", ss, "-i", self.model.video_file, "-loglevel", "quiet", "-strict", "-2", "-t", "{:.3f}".format(t), "-af", af_params, "-map", "0:v:0", "-map", "0:a:" + str(self.model.audio_id), "-c:v", "libx264", "-vf", vf, "-profile:v", "baseline", "-level", "3.0", "-c:a", "aac", "-ac", "2", filename + filename_suffix + ".mp4"]
                #     call(cmd)

                # print cmd.encode('utf-8')
                # self.model.p = Popen(cmd.encode(sys.getfilesystemencoding()), shell=True, **subprocess_args())
                # self.model.p.wait()

                # if (self.model.is_create_clips_with_hardsub or self.model.is_create_clips_with_softsub) and not self.model.is_write_output_subtitles_for_clips:
                #     os.remove(filename + ".srt")

                if self.canceled:
                    break

                # cmd = " ".join(["ffmpeg", "-y", "-ss", ss, "-i", '"' + self.model.video_file + '"', "-loglevel", "quiet", "-t", str(t), "-af", af_params, "-map", "0:a:" + str(self.model.audio_id), '"' + filename + ".mp3" + '"'])
                # print cmd.encode('utf-8')
                # self.model.p = Popen(cmd.encode(sys.getfilesystemencoding()), shell=True, **subprocess_args())
                # self.model.p.wait()

                num_files_completed += 1

        time_end = time.time()
        time_diff = (time_end - time_start)
        if self.model.batch_mode:
            self.batchJobsFinished.emit()
 
        if not self.canceled:
            self.updateProgress.emit(100)
            self.jobFinished.emit(time_diff)

        # if self.canceled:
        #     print "Canceled"
        # else:
        #     print "Done"
        

class JobsInfo(QDialog):
    
    def __init__(self, message, parent=None):
        super(JobsInfo, self).__init__(parent)
        
        self.initUI(message)

    def initUI(self, message):
        
        okButton = QPushButton("OK")
        cancelButton = QPushButton("Cancel")
        
        okButton.clicked.connect(self.ok)
        cancelButton.clicked.connect(self.cancel)

        reviewEdit = QTextEdit()
        reviewEdit.setReadOnly(True)
        reviewEdit.setText(message)

        grid = QGridLayout()
        grid.setSpacing(10)

        grid.addWidget(reviewEdit, 1, 1, 1, 3)
        grid.addWidget(okButton, 2, 2)
        grid.addWidget(cancelButton, 2, 3)

        grid.setColumnStretch(1,1)
        
        self.setLayout(grid) 
        
        self.setWindowTitle('movies2anki [Batch Processing]')
        # self.setModal(True)

        self.setMinimumSize(400, 300)

    def ok(self):
        self.done(1)

    def cancel(self):
        self.done(0)

class MainDialog(QDialog):
    
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        
        self.model = Model()
        self.audio_streams = []
        self.directory = self.model.input_directory
        
        self.initUI()
        
    def initUI(self):
        vbox = QVBoxLayout()

        # ---------------------------------------------------
        filesGroup = self.createFilesGroup()
        vbox.addWidget(filesGroup)
        # ---------------------------------------------------
        outputGroup = self.createOutputGroup()
        # vbox.addWidget(outputGroup)
        # ---------------------------------------------------
        optionsGroup = self.createOptionsGroup()
        vbox.addWidget(optionsGroup)
        # ---------------------------------------------------
        bottomGroup = self.createBottomGroup()
        vbox.addLayout(bottomGroup)
        # ---------------------------------------------------
        self.videoButton.clicked.connect(self.showVideoFileDialog)
        # self.audioIdComboBox.currentIndexChanged.connect(self.setAudioId)
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

        self.setLayout(vbox)
        
        self.adjustSize()
        self.setWindowTitle('movies2anki')
        self.setModal(True)
        self.show()

    # def closeEvent(self, event):
    #     # save settings
    #     self.model.save_settings()
        
        # QDialog.closeEvent(self, event)

    def done(self, r):
        self.model.save_settings()
        return QDialog.done(self, r)

    def showVideoFileDialog(self):
        fname, _ = QFileDialog.getOpenFileName(directory = self.directory, filter = "Video Files (*.avi *.mkv *.mp4 *.mov *.webm *.mp3 *.m4a *.wav);;All files (*.*)")
        self.videoEdit.setText(fname)

        if os.path.exists(fname):
            self.directory = os.path.dirname(fname)

    def showSubsEngFileDialog(self):
        fname, _ = QFileDialog.getOpenFileName(directory = self.directory, filter = "Subtitle Files (*.srt *.vtt *.ass)")
        self.subsEngEdit.setText(fname)

        if os.path.exists(fname):
            self.directory = os.path.dirname(fname)

    def showSubsRusFileDialog(self):
        fname, _ = QFileDialog.getOpenFileName(directory = self.directory, filter = "Subtitle Files (*.srt *.vtt *.ass)")
        self.subsRusEdit.setText(fname)

        if os.path.exists(fname):
            self.directory = os.path.dirname(fname)

    def showOutDirectoryDialog(self):
        fname = QFileDialog.getExistingDirectory(directory = self.model.output_directory)

        if len(fname) != 0:
            self.model.output_directory = fname

        self.outDirEdit.setText(self.model.output_directory)

    def showErrorDialog(self, message):
        QMessageBox.critical(self, "movies2anki", message)

    def showDirAlreadyExistsDialog(self, dir):
        reply = QMessageBox.question(self, "movies2anki",
            "Folder '" + dir + "' already exists. Do you want to overwrite it?", QMessageBox.Yes | 
            QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            return True
            
        return False
        
    # def tryToSetEngAudio(self):
    #     eng_id = len(self.audio_streams) - 1
    #     for cur_id in range(len(self.audio_streams)):
    #         if self.audio_streams[cur_id].find("[eng]") != -1:
    #             eng_id = cur_id
    #             break

    #     self.audioIdComboBox.setCurrentIndex(eng_id)

    # def setAudioId(self):
    #     self.model.audio_id = self.audioIdComboBox.currentIndex()

    # def getAudioStreams(self, video_file):
    #     self.audio_streams = []
        
    #     if "*" in video_file or "?" in video_file:
    #         glob_results = find_glob_files(video_file)

    #         if len(glob_results) == 0:
    #             # print "Video file not found"
    #             return
    #         else:
    #             video_file = glob_results[0]  

    #     elif not os.path.isfile(video_file):
    #         # print "Video file not found"
    #         return

    #     try:
    #         with noBundledLibs():
    #             output = check_output([ffprobe_executable, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", video_file], startupinfo=si, encoding='utf-8')
    #     except OSError as ex:
    #         self.model.audio_id = 0
    #         # print "Can't find ffprobe", ex
    #         return

    #     json_data = json.loads(output)
    #     streams = json_data["streams"]

    #     for idx in range(len(streams)):
    #         audio = streams[idx]

    #         title = ""
    #         language = "???"

    #         if "tags" in audio:
    #             tags = audio["tags"]
    #             if "language" in tags:
    #                 language = tags["language"]

    #         if len(title) != 0:
    #             stream = "%i: %s [%s]" % (idx, title, language)
    #         else:
    #             stream = "%i: [%s]" % (idx, language)

    #         self.audio_streams.append(stream)

    # def changeAudioStreams(self):
    #     self.audioIdComboBox.clear()
    #     self.getAudioStreams(self.model.video_file)
    #     self.audioIdComboBox.addItems(self.audio_streams)
    #     self.tryToSetEngAudio()

    def changeSubtitles(self):
        self.model.en_srt = guess_srt_file(self.model.video_file, [".srt", "*eng*.srt", "*en*.srt", "*.srt", ".ass", "*.ass", ".vtt", "*.vtt"], "")
        self.subsEngEdit.setText(self.model.en_srt)

        self.model.ru_srt = guess_srt_file(self.model.video_file, ["*rus*.srt", "*ru*.srt"], "")
        self.subsRusEdit.setText(self.model.ru_srt)

    def changeVideoFile(self):
        self.model.video_file = self.videoEdit.text().strip()
        if not os.path.isfile(self.model.video_file):
            return
        
        self.directory = os.path.dirname(self.model.video_file)
        self.model.input_directory = self.directory

        # self.changeAudioStreams()

        self.model.out_en_srt = self.model.out_en_srt_suffix
        self.model.out_ru_srt = self.model.out_ru_srt_suffix
        if len(self.model.video_file) > 4:
            self.model.out_en_srt = self.model.video_file[:-3] + self.model.out_en_srt
            self.model.out_ru_srt = self.model.video_file[:-3] + self.model.out_ru_srt

        self.changeSubtitles()

        self.setDeckName()

    def changeEngSubs(self):
        self.model.en_srt = self.subsEngEdit.text().strip()

    def changeRusSubs(self):
        self.model.ru_srt = self.subsRusEdit.text().strip()

    def changeOutDir(self):
        self.model.output_directory = self.outDirEdit.text().strip()

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

    def setGapPhrases(self):
        self.model.is_gap_phrases = self.gapPhrasesGroupBox.isChecked();

    def setMovieMode(self):
        self.model.mode = "Movie"

    def setPhrasesMode(self):
        self.model.mode = "Phrases"

    def setDeckName(self):
        if self.deckComboBox.currentText().strip() == "":
            self.deckComboBox.lineEdit().setText(os.path.splitext(os.path.basename(self.model.video_file))[0])

        self.model.deck_name = self.deckComboBox.currentText().strip()

    def validateSubtitles(self):
        if len(self.model.en_srt) == 0:
            self.showErrorDialog("Add Subs 1.")
            return False

        if "*" in self.model.en_srt or "?" in self.model.en_srt:
            glob_results = find_glob_files(self.model.en_srt)

            if len(glob_results) == 0:
                # print "English subtitles not found."
                return
            else:
                self.model.en_srt = glob_results[0]  

        elif not os.path.isfile(self.model.en_srt):
            # print "English subtitles didn't exist."
            return False

        if len(self.model.ru_srt) != 0:
            if "*" in self.model.ru_srt or "?" in self.model.ru_srt:
                glob_results = find_glob_files(self.model.ru_srt)

                if len(glob_results) == 0:
                    # print "Russian subtitles not found."
                    return
                else:
                    self.model.ru_srt = glob_results[0]  

            elif not os.path.isfile(self.model.ru_srt):
                # print "Russian subtitles didn't exist."
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
            # print "Writing output subtitles with phrases..."
            self.model.write_output_subtitles()

        minutes = int(duration_longest_phrase / 60)
        seconds = int(duration_longest_phrase % 60)

        # show info dialog
        message = """Subs 1:  %s
Subs 2:  %s
Phrases: %s
The longest phrase: %s min. %s sec.""" % (self.model.num_en_subs, self.model.num_ru_subs, self.model.num_phrases, minutes, seconds)
        QMessageBox.information(self, "Preview", message)

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
            self.model.video_file = video_file
            self.model.en_srt = en_srt
            self.model.ru_srt = ru_srt
            self.model.deck_name = deck_name

            self.model.create_subtitles()
            self.model.create_tsv_file()

    def check_directories(self):
        # for video_file, en_srt, ru_srt, deck_name in self.model.jobs:
        #     collection_dir = getNameForCollectionDirectory(self.model.output_directory, deck_name)

        #     if os.path.exists(collection_dir):
        #         if self.showDirAlreadyExistsDialog(collection_dir) == False:
        #             return False
        #         else:
        #             try:
        #                 # print "Remove dir " + collection_dir.encode('utf-8')
        #                 shutil.rmtree(collection_dir)
        #             except OSError as ex:
        #                 # print ex
        #                 return False
        return True
        
    def startBatchMode(self):
        self.model.batch_mode = True

        self.model.tmp_video_file = self.model.video_file
        self.model.tmp_en_srt = self.model.en_srt
        self.model.tmp_ru_srt = self.model.ru_srt
        self.model.tmp_deck_name = self.model.deck_name

        if len(self.model.deck_name) == 0:
            self.showErrorDialog("Deck can't be empty.")
            return

        # deck_name_pattern = self.model.deck_name
        # m = re.match(r'(.*){(#+)/(\d+)}(.*)', deck_name_pattern)
        # if not m:
        #     self.showErrorDialog("[Batch Mode] Couldn't find {##/<number>} in deck's name.\nFor example: 'Deck s02e{##/1}'")
        #     return
        # else:
        #     deck_name_prefix = m.group(1)
        #     deck_number_width = len(m.group(2))
        #     deck_number_start = int(m.group(3))
        #     deck_name_suffix = m.group(4)
        
        video_files = sorted(find_glob_files(self.model.video_file))
        en_srt_files = sorted(find_glob_files(self.model.en_srt))
        ru_srt_files = sorted(find_glob_files(self.model.ru_srt))

        if len(en_srt_files) != len(video_files):
            message = "The number of videos [%d] does not match the number of Subs 1 subtitles [%d]." % (len(video_files), len(en_srt_files))
            self.showErrorDialog(message)
            return

        if len(ru_srt_files) < len(video_files):
            max_len = max(len(ru_srt_files), len(video_files))
            ru_srt_files = ru_srt_files + [""] * (max_len - len(ru_srt_files))

        for idx, video_file in enumerate(video_files):
            en_srt = en_srt_files[idx]
            ru_srt = ru_srt_files[idx]

            video_file = os.path.abspath(video_file)

            # deck_number = str(deck_number_start + idx)
            # deck_number = deck_number.zfill(deck_number_width)
            # deck_name = deck_name_prefix + deck_number +  deck_name_suffix

            deck_name = self.model.deck_name

            self.model.jobs.append((video_file, en_srt, ru_srt, deck_name))


        # if len(self.model.ru_srt) != 0:
        #     message = "\n".join("%s\n%s\n%s\n%s\n" % 
        #         (os.path.basename(t[0]), os.path.basename(t[1]), os.path.basename(t[2]), t[3]) for t in self.model.jobs)
        # else:
        #     message = "\n".join("%s\n%s\n%s\n" % 
        #         (os.path.basename(t[0]), os.path.basename(t[1]), t[3]) for t in self.model.jobs)

        if len(self.model.ru_srt) != 0:
            message = "\n".join("%s\n%s\n%s\n" % 
                (os.path.basename(t[0]), os.path.basename(t[1]), os.path.basename(t[2])) for t in self.model.jobs)
        else:
            message = "\n".join("%s\n%s\n" % 
                (os.path.basename(t[0]), os.path.basename(t[1])) for t in self.model.jobs)
        ret = JobsInfo(message).exec_()
        if ret == 1:
            ret = self.check_directories()
            if ret == True:
                self.updateDeckComboBox()

                mw.progress.start(immediate=True, parent=self)
                self.create_tsv_files()
                mw.progress.finish()

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
            self.showErrorDialog("Deck can't be empty.")
            return

        self.updateDeckComboBox()

        # if not os.path.isdir(self.model.output_directory):
        #     self.showErrorDialog("Output directory didn't exist.")
        #     return

        # save settings
        self.model.save_settings()

        if len(self.model.video_file) == 0:
            self.showErrorDialog("Video file name can't be empty.")
            return

        self.model.create_tsv_file()

        if not os.path.isfile(self.model.video_file):
            self.showErrorDialog("Video file didn't exist.")
            return

        # try:
        #     call(["ffmpeg", "-version"], **subprocess_args())
        # except OSError as ex: 
        #     # print "Can't find ffmpeg", ex
        #     self.showErrorDialog("Can't find ffmpeg.")
        #     return

        # create or remove & create colletion.media directory
        # collection_dir = getNameForCollectionDirectory(self.model.output_directory, self.model.deck_name)
        # if os.path.exists(collection_dir) and self.showDirAlreadyExistsDialog(collection_dir) == False:
        #     return

        # ret = create_or_clean_collection_dir(collection_dir)
        # if ret == False:
        #     self.showErrorDialog("Can't create or clean media directory. Try again in a few seconds.")
        #     return

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
        QMessageBox.information(self, "movies2anki", message)

    def updateDeckComboBox(self):
        text = self.deckComboBox.currentText().strip()
        if self.deckComboBox.findText(text) == -1:
            self.deckComboBox.addItem(text)
            self.model.recent_deck_names.append(text)
        else:
            if text in self.model.recent_deck_names:
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
        self.progressDialog = QProgressDialog(self)

        self.progressDialog.setWindowTitle("Generating Cards...")
        self.progressDialog.setCancelButtonText("Cancel")
        self.progressDialog.setMinimumDuration(0)

        progress_bar = QProgressBar(self.progressDialog)
        progress_bar.setAlignment(Qt.AlignCenter)
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
        self.progressDialog.setWindowModality(Qt.WindowModal)

        self.worker.start()
        
    def createFilesGroup(self):
        groupBox = QGroupBox("Files:")

        vbox = QVBoxLayout()

        self.videoButton = QPushButton("Video...")
        self.videoEdit = QLineEdit()
        # self.audioIdComboBox = QComboBox()

        hbox = QHBoxLayout()
        hbox.addWidget(self.videoButton)
        hbox.addWidget(self.videoEdit)
        # hbox.addWidget(self.audioIdComboBox)

        vbox.addLayout(hbox)

        self.subsEngButton = QPushButton("Subs 1...")
        self.subsEngEdit = QLineEdit()

        hbox = QHBoxLayout()
        hbox.addWidget(self.subsEngButton)
        hbox.addWidget(self.subsEngEdit)

        vbox.addLayout(hbox)

        self.subsRusButton = QPushButton("Subs 2...")
        self.subsRusEdit = QLineEdit()

        hbox = QHBoxLayout()
        hbox.addWidget(self.subsRusButton)
        hbox.addWidget(self.subsRusEdit)

        vbox.addLayout(hbox)

        groupBox.setLayout(vbox)

        return groupBox

    def createOutputGroup(self):
        groupBox = QGroupBox("Output:")

        vbox = QVBoxLayout()

        self.outDirButton = QPushButton("Directory...")
        self.outDirEdit = QLineEdit()
        self.outDirEdit.setText(self.model.output_directory)

        hbox = QHBoxLayout()
        hbox.addWidget(self.outDirButton)
        hbox.addWidget(self.outDirEdit)

        vbox.addLayout(hbox)

        groupBox.setLayout(vbox)

        return groupBox

    def createVideoDimensionsGroup(self):
        groupBox = QGroupBox("Video Dimensions:")

        layout = QFormLayout()

        self.widthSpinBox = QSpinBox()
        self.widthSpinBox.setRange(-2, 2048)
        self.widthSpinBox.setSingleStep(2)
        self.widthSpinBox.setValue(self.model.getVideoWidth())

        hbox = QHBoxLayout()
        hbox.addWidget(self.widthSpinBox)
        hbox.addWidget(QLabel("px"))

        layout.addRow(QLabel("Width:"), hbox)

        self.heightSpinBox = QSpinBox()
        self.heightSpinBox.setRange(-2, 2048)
        self.heightSpinBox.setSingleStep(2)
        self.heightSpinBox.setValue(self.model.getVideoHeight())

        hbox = QHBoxLayout()
        hbox.addWidget(self.heightSpinBox)
        hbox.addWidget(QLabel("px"))

        layout.addRow(QLabel("Height:"), hbox)

        groupBox.setLayout(layout)

        return groupBox

    def createPadTimingsGroup(self):
        groupBox = QGroupBox("Pad Timings:")

        layout = QFormLayout()

        self.startSpinBox = QSpinBox()
        self.startSpinBox.setRange(-9999, 9999)
        self.startSpinBox.setValue(self.model.getShiftStart())

        hbox = QHBoxLayout()
        hbox.addWidget(self.startSpinBox)
        hbox.addWidget(QLabel("ms"))

        layout.addRow(QLabel("Start:"), hbox)

        self.endSpinBox = QSpinBox()
        self.endSpinBox.setRange(-9999, 9999)
        self.endSpinBox.setValue(self.model.getShiftEnd())

        hbox = QHBoxLayout()
        hbox.addWidget(self.endSpinBox)
        hbox.addWidget(QLabel("ms"))

        layout.addRow(QLabel("End:"), hbox)

        groupBox.setLayout(layout)
        groupBox.setMinimumWidth(140)

        return groupBox

    def createGapPhrasesGroup(self):
        self.gapPhrasesGroupBox = QGroupBox("Gap between Phrases:")
        self.gapPhrasesGroupBox.setCheckable(True)
        self.gapPhrasesGroupBox.setChecked(self.model.is_gap_phrases)
        self.gapPhrasesGroupBox.clicked.connect(self.setGapPhrases)

        self.timeSpinBox = QDoubleSpinBox()
        self.timeSpinBox.setRange(0, 600.0)
        self.timeSpinBox.setSingleStep(0.25)
        self.timeSpinBox.setValue(self.model.getTimeDelta())

        hbox = QHBoxLayout()
        hbox.addWidget(self.timeSpinBox)
        hbox.addWidget(QLabel("sec"))

        self.gapPhrasesGroupBox.setLayout(hbox)

        return self.gapPhrasesGroupBox

    def createSplitPhrasesGroup(self):
        self.splitLongPhrasesGroupBox = QGroupBox("Split Long Phrases:")
        self.splitLongPhrasesGroupBox.setCheckable(True)
        self.splitLongPhrasesGroupBox.setChecked(self.model.is_split_long_phrases)
        self.splitLongPhrasesGroupBox.clicked.connect(self.setSplitLongPhrases)

        self.splitPhrasesSpinBox = QSpinBox()
        self.splitPhrasesSpinBox.setRange(1, 6000)
        self.splitPhrasesSpinBox.setSingleStep(10)
        self.splitPhrasesSpinBox.setValue(self.model.getPhrasesDurationLimit())

        hbox = QHBoxLayout()
        hbox.addWidget(self.splitPhrasesSpinBox)
        hbox.addWidget(QLabel("sec"))

        self.splitLongPhrasesGroupBox.setLayout(hbox)

        return self.splitLongPhrasesGroupBox

    def createModeOptionsGroup(self):
        vbox = QVBoxLayout()

        self.movieRadioButton = QRadioButton("Movie")
        self.phrasesRadioButton = QRadioButton("Phrases")

        if self.model.getMode() == 'Phrases':
            self.phrasesRadioButton.setChecked(True)
        else:
            self.movieRadioButton.setChecked(True)

        vbox.addWidget(self.movieRadioButton)
        vbox.addWidget(self.phrasesRadioButton)

        return vbox

    def createSubtitlePhrasesGroup(self):
        groupBox = QGroupBox("General Settings:")

        layout = QHBoxLayout()

        layout.addWidget(self.createGapPhrasesGroup())
        layout.addWidget(self.createSplitPhrasesGroup())
        layout.addLayout(self.createModeOptionsGroup())

        groupBox.setLayout(layout)

        return groupBox

    def createOptionsGroup(self):
        groupBox = QGroupBox("Options:")

        hbox = QHBoxLayout()
        self.videoDimensionsGroup = self.createVideoDimensionsGroup()
        # hbox.addWidget(self.videoDimensionsGroup)
        hbox.addWidget(self.createPadTimingsGroup())
        hbox.addWidget(self.createSubtitlePhrasesGroup())

        groupBox.setLayout(hbox)

        return groupBox

    def setModelName(self):
        self.model.model_name = self.modelComboBox.currentText()

    def createBottomGroup(self):
        modelGroupBox = QGroupBox("Model:")

        # self.modelComboBox = QLineEdit(self.model.model_name)
        # self.modelComboBox.setAlignment(Qt.AlignCenter)
        # self.modelComboBox.setReadOnly(True)
        
        self.modelComboBox = QComboBox()
        self.modelComboBox.setSizeAdjustPolicy(QComboBox.AdjustToContents);
        self.modelComboBox.addItems(self.model.default_model_names)
        self.modelComboBox.currentIndexChanged.connect(self.setModelName)

        # self.modelComboBox.setEditable(False)
        # self.modelComboBox.lineEdit().setAlignment(Qt.AlignCenter)
        # self.modelComboBox.lineEdit().setReadOnly(True)
        # self.modelComboBox.addItems(sorted(mw.col.models.allNames()))
        # self.modelComboBox.addItem("movies2anki")
        # self.modelComboBox.setReadOnly(True)
        # self.modelComboBox.setMinimumWidth(140)
        # self.modelComboBox.setMaximumWidth(140)
        
        modelGroupBox.setMinimumWidth(160)

        modelComboBoxWidth = self.modelComboBox.minimumSizeHint().width()
        self.modelComboBox.view().setMinimumWidth(modelComboBoxWidth)

        hbox = QHBoxLayout()
        hbox.addWidget(self.modelComboBox)

        modelGroupBox.setLayout(hbox)

        deckGroupBox = QGroupBox("Deck:")

        self.deckComboBox = QComboBox()
        self.deckComboBox.setEditable(True)
        self.deckComboBox.setMaxCount(5)
        self.deckComboBox.setSizePolicy(QSizePolicy.Expanding,
                QSizePolicy.Preferred)
        self.deckComboBox.addItems(sorted(mw.col.decks.allNames()))
        self.deckComboBox.clearEditText()
        self.deckComboBox.setInsertPolicy(QComboBox.NoInsert)
        
        hbox = QHBoxLayout()
        hbox.addWidget(self.deckComboBox)

        deckGroupBox.setLayout(hbox)

        grid = QGridLayout()

        hbox = QHBoxLayout()
        hbox.addWidget(deckGroupBox)
        hbox.addWidget(modelGroupBox)

        vbox = QVBoxLayout()
        self.previewButton = QPushButton("Preview...")
        self.startButton = QPushButton("Go!")
        vbox.addWidget(self.previewButton)
        vbox.addWidget(self.startButton)

        hbox.addLayout(vbox)

        return hbox

def main():
    mainDialog = MainDialog(mw)
    mainDialog.exec_()

action = QAction("Generate Video Cards...", mw)
action.setShortcut(QKeySequence("Ctrl+M"))
action.triggered.connect(main)
# mw.form.menuTools.addSeparator()
mw.form.menuTools.addAction(action)