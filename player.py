# -*- coding: utf-8 -*-

import subprocess, sys, json, time, re, os, atexit
import logging
import tempfile
import traceback

try:
    from aqt.sound import play, _packagedCmd, si
    import aqt.sound as sound # Anki 2.1.17+
except ImportError:
    from anki.sound import play, _packagedCmd, si
    import anki.sound as sound

from anki.lang import _, ngettext
from anki.hooks import addHook, wrap
from anki.utils import no_bundled_libs, strip_html
from aqt.reviewer import Reviewer
from aqt import mw, browser
from aqt.utils import showWarning, showInfo, tooltip, is_win, is_mac
from aqt.qt import *
from subprocess import check_output, CalledProcessError

# ------------- ADDITIONAL OPTIONS -------------
NORMALIZE_AUDIO = False
NORMALIZE_AUDIO_FILTER = "I=-18:LRA=11"
NORMALIZE_AUDIO_WITH_MP3GAIN = True
ADJUST_AUDIO_STEP = 0.25
ADJUST_AUDIO_REPLAY_TIME = 2.5
VLC_DIR = ""
IINA_DIR = "/Applications/IINA.app/Contents/MacOS/IINA"
# ----------------------------------------------

info = None
if is_win:
    info = subprocess.STARTUPINFO()
    info.wShowWindow = subprocess.SW_HIDE
    info.dwFlags = subprocess.STARTF_USESHOWWINDOW

p = None

from distutils.spawn import find_executable

if is_mac and '/usr/local/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/usr/local/bin:" + os.environ['PATH']

if is_mac and '/opt/homebrew/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/opt/homebrew/bin:" + os.environ['PATH']

mpv_executable, env = find_executable("mpv"), os.environ

if mpv_executable is None and is_mac:
    mpv_executable = "/Applications/mpv.app/Contents/MacOS/mpv"
    if not os.path.exists(mpv_executable):
        mpv_executable = None

with_bundled_libs = False
if mpv_executable is None:
    mpv_path, env = _packagedCmd(["mpv"])
    mpv_executable = mpv_path[0]
    with_bundled_libs = True

ffmpeg_executable = find_executable("ffmpeg")
ffprobe_executable = find_executable("ffprobe")

# maybe a fix for macOS
if ffprobe_executable is None:
    ffprobe_executable = '/usr/local/bin/ffprobe'
    if not os.path.exists(ffprobe_executable):
        ffprobe_executable = None
if ffmpeg_executable is None:
    ffmpeg_executable = '/usr/local/bin/ffmpeg'
    if not os.path.exists(ffmpeg_executable):
        ffmpeg_executable = None

logger = logging.getLogger()
ch = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.handlers = []
logger.addHandler(ch)

def timeToSeconds(t):
    hours, minutes, seconds, milliseconds = t.split('.')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) * 0.001

def secondsToTime(seconds, sep="."):
    ms = (seconds * 1000) % 1000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d%s%02d%s%02d.%03d" % (h, sep, m, sep, s, ms)

def playVideoClip(path=None, state=None, shift=None, isEnd=True, isPrev=False, isNext=False):
    global p, _player

    fields = {}
    for item in mw.reviewer.card.note().items():
        fields[item[0]] = item[1]

    # if path is not None and os.path.exists(path):
    #     _player(path)
    #     return

    if not path:
        if state is not None:
            path = fields["Audio"]
        else:
            path = fields["Video"]

    path = strip_html(path)

    # elif path.endswith(".mp3"): # workaround to fix replay button (R) without refreshing webview.
    #     path = fields["Audio"]
    # else:
    #     path = fields["Video"]

    # if mw.reviewer.state == "question" and mw.reviewer.card.note_type()["name"] == "movies2anki - subs2srs (video)":
    #     path = fields["Video"]

    m = re.fullmatch(r"(.*?)_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*", path)

    if not m:
        return False

    card_prefix, time_start, time_end = m.groups()
    time_start = timeToSeconds(time_start)
    time_end = timeToSeconds(time_end)

    if state == None and (isPrev or isNext):
        cards = sorted(mw.col.findCards('"Id:{}_*"'.format(card_prefix), order=True))
        card_idx = cards.index(mw.reviewer.card.id)

        prev_card_idx = card_idx - 1 if card_idx - 1 > 0 else 0
        next_card_idx = card_idx + 1
        if next_card_idx >= len(cards):
            next_card_idx = len(cards) - 1

        if (isPrev and mw.col.getCard(cards[prev_card_idx]).id == mw.reviewer.card.id):
            tooltip("It's the first card.")
            return
        if (isNext and mw.col.getCard(cards[next_card_idx]).id == mw.reviewer.card.id):
            tooltip("It's the last card.")
            return

        curr_card = mw.col.getCard(cards[card_idx])
        prev_card = mw.col.getCard(cards[prev_card_idx])
        next_card = mw.col.getCard(cards[next_card_idx])

        prev_card_audio = prev_card.note()["Audio"]
        next_card_audio = next_card.note()["Audio"]

        # TODO compare Id field prefix or Source field or limit search by Source or maybe something else

        m = re.fullmatch(r".*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*", prev_card_audio)

        prev_time_start, prev_time_end = m.groups()
        prev_time_start = timeToSeconds(prev_time_start)
        prev_time_end = timeToSeconds(prev_time_end)

        m = re.fullmatch(r".*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*", next_card_audio)

        next_time_start, next_time_end = m.groups()
        next_time_start = timeToSeconds(next_time_start)
        next_time_end = timeToSeconds(next_time_end)

        if isPrev:
            time_start = prev_time_start

        if isNext:
            time_end = next_time_end

    if state != None:
        if state == "start":
            time_start = time_start - shift
        elif state == "end":
            time_end = time_end + shift
        elif state == "start reset":
            m = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", fields["Id"])
            id_time_start, id_time_end = m.groups()
            id_time_start = timeToSeconds(id_time_start)
            time_start = id_time_start
        elif state == "end reset":
            m = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", fields["Id"])
            id_time_start, id_time_end = m.groups()
            id_time_end = timeToSeconds(id_time_end)
            time_end = id_time_end

        time_interval = "%s-%s" % (secondsToTime(time_start), secondsToTime(time_end))
        mw.reviewer.card.note()["Audio"] = re.sub(r"_\d+\.\d\d\.\d\d\.\d+-\d+\.\d\d\.\d\d\.\d+\.", "_%s." % time_interval, fields["Audio"])
        mw.reviewer.card.note()["Video"] = re.sub(r"_\d+\.\d\d\.\d\d\.\d+-\d+\.\d\d\.\d\d\.\d+\.", "_%s." % time_interval, fields["Video"])
        mw.reviewer.card.note().flush()

    if VLC_DIR:
        default_args = ["-I", "dummy", "--play-and-exit", "--no-video-title", "--video-on-top", "--sub-track=8"]
        if is_win:
            default_args += ["--dummy-quiet"]
        default_args += ["--no-sub-autodetect-file"]
    else:
        default_args = ["--pause=no", "--script=%s" % os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.lua")]
        default_args += ["--sub-visibility=no", "--no-resume-playback", "--save-position-on-quit=no"]

    if path.endswith(".mp3"):
        if VLC_DIR:
            default_args += ["--no-video"]
        else:
            default_args += ["--force-window=no", "--video=no"]

    args = list(default_args)
    if state == None:
        if VLC_DIR:
            args += ["--start-time={}".format(time_start)]
            if isEnd:
                args += ["--stop-time={}".format(time_end)]
        else:
            args += ["--start={}".format(time_start)]
            if isEnd:
                args += ["--end={}".format(time_end)]
    elif state == "start" or state == "start reset":
        if VLC_DIR:
            args += ["--start-time={}".format(time_start), "--stop-time={}".format(time_end)]
        else:
            args += ["--start={}".format(time_start), "--end={}".format(time_end)]
    elif state == "end" or state == "end reset":
        if VLC_DIR:
            args += ["--start-time={}".format(time_end - ADJUST_AUDIO_REPLAY_TIME), "--stop-time={}".format(time_end)]
        else:
            args += ["--start={}".format(time_end - ADJUST_AUDIO_REPLAY_TIME), "--end={}".format(time_end)]

    config = mw.addonManager.getConfig(__name__)
    af_d = float(config["audio fade in/out"])

    if (path.endswith(".mp3") and not isPrev and not isNext) or state != None:
        if VLC_DIR:
            pass
        else:
            if af_d:
                args += ["--af=afade=t=out:st=%s:d=%s" % (time_end - af_d, af_d)]
    else:
        if VLC_DIR:
            pass
        else:
            if not (state == None and isEnd == False):
                if af_d:
                    args += ["--af=afade=t=out:st=%s:d=%s" % (time_end - af_d, af_d)]

    fullpath = fields["Path"]
    if path is not None and os.path.exists(path) and isEnd == True and not any([state, isPrev, isNext]):
        fullpath = path
        args = list(default_args)

    if not os.path.exists(fullpath):
        return

    if VLC_DIR:
        cmd = [VLC_DIR] + args + [os.path.normpath(fullpath)]
    else:
        if is_mac and os.path.exists(IINA_DIR):
            args = [o.replace("--", "--mpv-") for o in args]
            cmd = [IINA_DIR] + args + [fullpath]
        else:
            cmd = [mpv_executable] + args + [fullpath]

    if p != None and p.poll() is None:
        p.kill()

    if with_bundled_libs:
        p = subprocess.Popen(cmd)
        return

    with no_bundled_libs():
        p = subprocess.Popen(cmd)

def queueExternalAV(self, path):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.note_type()["name"] == "movies2anki (add-on)" or mw.reviewer.card.note_type()["name"].startswith("movies2anki - subs2srs")):
        queueExternal(path)
    else:
        _player(path)

def queueExternal(path):
    global p, _player

    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.note_type()["name"] == "movies2anki (add-on)" or mw.reviewer.card.note_type()["name"].startswith("movies2anki - subs2srs")):
        # if mw.reviewer.state == "answer" and path.endswith(".mp4"):
        #     return

        try:
            clearExternalQueue()
            oldcwd = os.getcwd()
            os.chdir(mw.col.media.dir())
            ret = playVideoClip(path.filename if av_player else path)
            os.chdir(oldcwd)
            if ret == False:
                _player(path)
        except OSError:
            return showWarning(r"""<p>Please install <a href='https://mpv.io'>mpv</a>.</p>
                On Windows download mpv and either update PATH environment variable or put mpv.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)
    else:
        _player(path)

def _stopPlayer():
    global p

    if p != None and p.poll() is None:
        p.kill()

addHook("unloadProfile", _stopPlayer)
atexit.register(_stopPlayer)

def clearExternalQueue():
    global _queueEraser

    _stopPlayer()
    _queueEraser()

_player = sound._player
sound._player = queueExternal

try:
    import types
    from aqt.sound import av_player # Anki 2.1.20+
    from anki.sound import SoundOrVideoTag
    _player = av_player._play
    av_player._play = types.MethodType(queueExternalAV, av_player)
except Exception as e:
    av_player = None
    pass

_queueEraser = sound._queueEraser
sound._queueEraser = clearExternalQueue

def adjustAudio(state, shift=None):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.note_type()["name"] == "movies2anki (add-on)" or mw.reviewer.card.note_type()["name"].startswith("movies2anki - subs2srs")):
        try:
            clearExternalQueue()
            oldcwd = os.getcwd()
            os.chdir(mw.col.media.dir())
            playVideoClip(state=state, shift=shift)
            os.chdir(oldcwd)
        except OSError:
            return showWarning(r"""<p>Please install <a href='https://mpv.io'>mpv</a>.</p>
                On Windows download mpv and either update PATH environment variable or put mpv.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)

def selectVideoPlayer():
    global VLC_DIR
    try:
        if is_mac and os.path.exists(IINA_DIR):
            return

        if mpv_executable is None:
            raise OSError()

        if with_bundled_libs:
            p = subprocess.Popen([mpv_executable, "--version"], startupinfo=info)
        else:
            with no_bundled_libs():
                p = subprocess.Popen([mpv_executable, "--version"], startupinfo=info)

        if p != None and p.poll() is None:
            p.kill()
    except OSError:
        if VLC_DIR != "":
            return

        if is_win:
            VLC_DIR = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
            if os.path.exists(VLC_DIR):
                return

            VLC_DIR = r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            if os.path.exists(VLC_DIR):
                return
        elif is_mac:
            VLC_DIR = r"/Applications/VLC.app/Contents/MacOS/VLC"
            if os.path.exists(VLC_DIR):
                return

        VLC_DIR = ""

        return showWarning(r"""<p>Neither mpv nor VLC were found.</p>
            <p>Please install <a href='https://mpv.io'>mpv</a>.</p>
            On Windows download mpv and either update PATH environment variable or put mpv.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)

addHook("profileLoaded", selectVideoPlayer)

def shortcutKeys(self):
    shortcuts = DefaultShortcutKeys(self);

    return shortcuts + [
        (",", lambda: adjustAudio("start", ADJUST_AUDIO_STEP)),
        (".", lambda: adjustAudio("start", -1.0 * ADJUST_AUDIO_STEP)),
        ("Shift+,", lambda: adjustAudio("end", -1.0 * ADJUST_AUDIO_STEP)),
        ("Shift+.", lambda: adjustAudio("end", ADJUST_AUDIO_STEP)),
        ("Ctrl+Shift+,", lambda: adjustAudio("start reset")),
        ("Ctrl+Shift+.", lambda: adjustAudio("end reset")),

        ("Ctrl+R", replayVideo),
        ("Shift+R", lambda: replayVideo(isEnd=False)),
        ("[", lambda: replayVideo(isPrev=True)),
        ("]", lambda: replayVideo(isNext=True)),
        ("Shift+[", lambda: joinCard(isPrev=True)),
        ("Shift+]", lambda: joinCard(isNext=True)),
    ]

DefaultShortcutKeys = Reviewer._shortcutKeys
Reviewer._shortcutKeys = shortcutKeys

def replayVideo(isEnd=True, isPrev=False, isNext=False):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.note_type()["name"] == "movies2anki (add-on)" or mw.reviewer.card.note_type()["name"].startswith("movies2anki - subs2srs")):
        clearExternalQueue()
        oldcwd = os.getcwd()
        os.chdir(mw.col.media.dir())
        playVideoClip(isEnd=isEnd, isPrev=isPrev, isNext=isNext)
        os.chdir(oldcwd)

def joinCard(isPrev=False, isNext=False):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.note_type()["name"] == "movies2anki (add-on)" or mw.reviewer.card.note_type()["name"].startswith("movies2anki - subs2srs")):
        m = re.match(r"^(.*?)_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", mw.reviewer.card.note()["Audio"])

        card_prefix, time_start, time_end = m.groups()
        time_start = timeToSeconds(time_start)
        time_end = timeToSeconds(time_end)

        cards = sorted(mw.col.findCards('"Id:{}_*"'.format(card_prefix), order=True))
        card_idx = cards.index(mw.reviewer.card.id)

        prev_card_idx = card_idx - 1 if card_idx - 1 > 0 else 0
        next_card_idx = card_idx + 1
        if next_card_idx >= len(cards):
            next_card_idx = len(cards) - 1

        if (isPrev and mw.col.getCard(cards[prev_card_idx]).id == mw.reviewer.card.id) or \
            (isNext and mw.col.getCard(cards[next_card_idx]).id == mw.reviewer.card.id):
            tooltip("Nothing to do.")
            return

        curr_card = mw.col.getCard(cards[card_idx]).note()
        prev_card = mw.col.getCard(cards[prev_card_idx]).note()
        next_card = mw.col.getCard(cards[next_card_idx]).note()

        if (isPrev and prev_card["Source"] != curr_card["Source"]) or (isNext and curr_card["Source"] != next_card["Source"]):
           showInfo("Cards can't be joined due to the Source field difference.")
           return

        curr_card_audio = curr_card["Audio"]
        prev_card_audio = prev_card["Audio"]
        next_card_audio = next_card["Audio"]

        m = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", curr_card_audio)

        curr_time_start, curr_time_end = m.groups()
        curr_time_start = timeToSeconds(curr_time_start)
        curr_time_end = timeToSeconds(curr_time_end)

        m = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", prev_card_audio)

        prev_time_start, prev_time_end = m.groups()
        prev_time_start = timeToSeconds(prev_time_start)
        prev_time_end = timeToSeconds(prev_time_end)

        m = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", next_card_audio)

        next_time_start, next_time_end = m.groups()
        next_time_start = timeToSeconds(next_time_start)
        next_time_end = timeToSeconds(next_time_end)

        if isPrev:
            time_start = prev_time_start

        if isNext:
            time_end = next_time_end

        config = mw.addonManager.getConfig(__name__)

        c = mw.reviewer.card.note()
        for name, val in c.items():
            if name == "Id":
                c[name] = "%s_%s-%s" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end))
            elif name == "Audio":
                c[name] = "%s_%s-%s.mp3" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end))
            elif name == "Video":
                c[name] = "%s_%s-%s.%s" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end), config['video extension'])
            elif name == "Source":
                pass
            elif name == "Path":
                pass
            elif name == "Audio Sound":
                c["Audio Sound"] = ""
            elif name == "Video Sound":
                c["Video Sound"] = ""
            elif name == "Snapshot":
                pass
            else:
                if isPrev:
                    c[name] = prev_card[name] + "<br>" + c[name]
                else:
                    c[name] = c[name] + "<br>" + next_card[name]

        mw.checkpoint(_("Delete"))

        c.flush()

        if isPrev:
            cd = prev_card
        else:
            cd = next_card

        cnt = len(cd.cards())
        mw.col.remNotes([cd.id])
        mw.reset()

        tooltip(ngettext(
            "Notes joined and %d card deleted.",
            "Notes joined and %d cards deleted.",
            cnt) % cnt)

def join_and_add_double_quotes(cmd):
    return '[' + ' '.join(['"{}"'.format(s) if ' ' in s else s for s in cmd]) + ']'

class MediaWorker(QThread):
    updateProgress = pyqtSignal(int)
    updateProgressText = pyqtSignal(str)
    updateNote = pyqtSignal(str, str, str)
    jobFinished = pyqtSignal(float)

    def __init__(self, data, map_ids):
        QThread.__init__(self)

        self.data = data
        self.canceled = False
        self.fp = None
        self.map_ids = map_ids

        if os.environ.get("ADDON_DEBUG"):
            logger.setLevel(logging.DEBUG)

    def cancel(self):
        self.canceled = True

        if self.fp != None:
            self.fp.terminate()

    def run(self):
        job_start = time.time()

        mp3gain_executable = find_executable("mp3gain")

        logger.debug('mpv_executable: {}'.format(mpv_executable))

        config = mw.addonManager.getConfig(__name__)

        for idx, note in enumerate(self.data):
            if self.canceled:
                break

            self.updateProgress.emit((idx * 1.0 / len(self.data)) * 100)

            fld = note["Audio"]

            time_start, time_end = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", fld).groups()

            time_start_seconds = timeToSeconds(time_start)
            time_end_seconds = timeToSeconds(time_end)

            ss = secondsToTime(timeToSeconds(time_start), sep=":")
            se = secondsToTime(timeToSeconds(time_end), sep=":")
            t = timeToSeconds(time_end) - timeToSeconds(time_start)

            if config["audio fade in/out"]:
                af_d = float(config["audio fade in/out"])
                af_st = 0
                af_to = t - af_d
                default_af_params = "afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(af_st, af_d, af_to, af_d)
            else:
                default_af_params = ""

            audio_id = self.map_ids[note["Path"]]

            # TODO
            video_height = 320

            self.updateProgressText.emit(note["Source"] + "  " + ss)

            af_params = default_af_params
            if NORMALIZE_AUDIO and not (NORMALIZE_AUDIO_WITH_MP3GAIN and mp3gain_executable):
                cmd = [ffmpeg_executable, "-ss", ss, "-i", note["Path"], "-t", str(t), "-af", "loudnorm=%s:print_format=json" % NORMALIZE_AUDIO_FILTER, "-f", "null", "-"]
                logger.debug('normalize_audio: {}'.format('Started'))
                logger.debug('normalize_audio: {}'.format(join_and_add_double_quotes(cmd)))
                with no_bundled_libs():
                    output = check_output(cmd, startupinfo=info, encoding='utf-8')
                logger.debug('normalize_audio: {}'.format('Finished'))
                # https://github.com/slhck/ffmpeg-normalize/blob/5fe6b3df5f4b36b398fa08c11a9001b1e67cec10/ffmpeg_normalize/_streams.py#L171
                output_lines = [line.strip() for line in output.split('\n')]
                loudnorm_start = False
                loudnorm_end = False
                for index, line in enumerate(output_lines):
                    if line.startswith('[Parsed_loudnorm'):
                        loudnorm_start = index + 1
                        continue
                    if loudnorm_start and line.startswith('}'):
                        loudnorm_end = index + 1
                        break
                stats = json.loads('\n'.join(output_lines[loudnorm_start:loudnorm_end]))
                nf_params = "loudnorm={}:measured_I={}:measured_LRA={}:measured_TP={}:measured_thresh={}:offset={}:linear=true".format(NORMALIZE_AUDIO_FILTER, stats["input_i"], stats["input_lra"], stats["input_tp"], stats["input_thresh"], stats["target_offset"])
                if af_params:
                    af_params = "%s,%s" % (nf_params, af_params)
                else:
                    af_params = nf_params

            if note["Audio Sound"] == "" or not os.path.exists(os.path.join(mw.col.media.dir(), note["Audio"])):
                self.fp = None
                if ffmpeg_executable:
                    cmd = [ffmpeg_executable, "-y", "-ss", ss, "-i", note["Path"], "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
                    if af_params:
                        cmd += ["-af", af_params]
                    cmd += ["-sn"]
                    cmd += ["-map_metadata", "-1"]
                    cmd += ["-map", "0:a:{}".format(audio_id)]
                    cmd += [note["Audio"]]
                else:
                    cmd = [mpv_executable, note["Path"]]
                    # cmd += ["--include=%s" % self.mpvConf]
                    cmd += ["--start=%s" % ss, "--length=%s" % "{:.3f}".format(t)]
                    cmd += ["--aid=%d" % (audio_id + 1)]
                    cmd += ["--video=no"]
                    cmd += ["--no-ocopy-metadata"]
                    cmd += ["--af=afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(time_start_seconds, af_d, time_end_seconds - af_d, af_d)]
                    cmd += ["--o=%s" % note["Audio"]]

                logger.debug('export_audio: {}'.format('Started'))
                logger.debug('export_audio: {}'.format(join_and_add_double_quotes(cmd)))
                if with_bundled_libs:
                    self.fp = subprocess.Popen(cmd, startupinfo=info, cwd=mw.col.media.dir())
                    self.fp.wait()
                else:
                    with no_bundled_libs():
                        self.fp = subprocess.Popen(cmd, startupinfo=info, cwd=mw.col.media.dir())
                        self.fp.wait()
                logger.debug('export_audio: {}'.format('Finished'))

                if NORMALIZE_AUDIO and NORMALIZE_AUDIO_WITH_MP3GAIN and mp3gain_executable:
                    cmd = [mp3gain_executable, "/f", "/q", "/r", "/k", note["Audio"]]
                    with no_bundled_libs():
                        self.fp = subprocess.Popen(cmd, startupinfo=info, cwd=mw.col.media.dir())
                        self.fp.wait()

                if self.canceled:
                    break

                self.updateNote.emit(str(note.id), "Audio Sound", note["Audio"])

            if "Video Sound" in note and (note["Video Sound"] == "" or not os.path.exists(os.path.join(mw.col.media.dir(), note["Video"]))):
                self.fp = None
                if ffmpeg_executable:
                    cmd = [ffmpeg_executable, "-y", "-ss", ss, "-i", note["Path"], "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
                    if af_params:
                        cmd += ["-af", af_params]
                    cmd += ["-map", "0:v:0", "-map", "0:a:{}".format(audio_id), "-ac", "2", "-vf", "scale=-2:%s,setsar=1" % video_height]
                    cmd += ["-c:v", "libx264"]
                    cmd += ["-profile:v", "main", "-level:v", "3.1"]
                    cmd += ["-pix_fmt", "yuv420p"]
                    cmd += ["-sn"]
                    cmd += ["-map_metadata", "-1"]
                    if note["Video"].endswith('.webm'):
                        cmd += config["video encoding settings (webm)"].split()
                    else:
                        cmd += ['-movflags', '+faststart']
                    cmd += [note["Video"]]
                else:
                    cmd = [mpv_executable, note["Path"]]
                    # cmd += ["--include=%s" % self.mpvConf]
                    cmd += ["--start=%s" % ss, "--length=%s" % "{:.3f}".format(t)]
                    cmd += ["--sub=no"]
                    cmd += ["--no-ocopy-metadata"]
                    cmd += ["--aid=%d" % (audio_id + 1)]
                    cmd += ["--af=afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(time_start_seconds, af_d, time_end_seconds - af_d, af_d)]
                    cmd += ["--vf-add=lavfi-scale=%s:%s" % (-2, video_height)]
                    if note["Video"].endswith('.webm'):
                        cmd += ["--ovc=libvpx-vp9"]
                        cmd += ["--ovcopts=b=1400K,threads=4,crf=23,qmin=0,qmax=36,speed=2"]
                    else:
                        cmd += ["--ovc=libx264"]
                        cmd += ["--ovcopts=profile=main,level=31"]
                        cmd += ["--vf-add=format=yuv420p"]
                        cmd += ["--oac=aac"]
                        cmd += ["--ofopts=movflags=+faststart"]
                    cmd += ["--o=%s" % note["Video"]]
                logger.debug('export_video: {}'.format('Started'))
                logger.debug('export_video: {}'.format(join_and_add_double_quotes(cmd)))
                if with_bundled_libs:
                    self.fp = subprocess.Popen(cmd, startupinfo=info, cwd=mw.col.media.dir())
                    self.fp.wait()
                else:
                    with no_bundled_libs():
                        self.fp = subprocess.Popen(cmd, startupinfo=info, cwd=mw.col.media.dir())
                        self.fp.wait()
                logger.debug('export_video: {}'.format('Finished'))
                retcode = self.fp.returncode
                logger.debug('return code: {}'.format(retcode))
                if retcode != 0:
                    cmd_debug = ' '.join(['"' + c + '"' for c in cmd])
                    cmd_debug = cmd_debug.replace(' "-loglevel" "quiet" ', ' ')
                    cmd_debug = [cmd_debug]
                    raise CalledProcessError(retcode, cmd_debug)

                if self.canceled:
                    break

                self.updateNote.emit(str(note.id), "Video Sound", note["Video"])

        job_end = time.time()
        time_diff = (job_end - job_start)

        if not self.canceled:
            self.updateProgress.emit(100)
            self.jobFinished.emit(time_diff)

def cancelProgressDialog():
    global is_cancel
    is_cancel = True
    if hasattr(mw, 'worker'):
        mw.worker.cancel()

def setProgress(progress):
    logger.debug('progress: {:.2f}%'.format(progress))
    mw.progressDialog.setValue(progress)

def setProgressText(text):
    logger.debug('file: {}'.format(text))
    mw.progressDialog.setLabelText(text)

def saveNote(nid, fld, val):
    note = mw.col.get_note(int(nid))
    note[fld] = "[sound:%s]" % val
    note.flush()

def finishProgressDialog(time_diff):
    mw.progressDialog.done(0)
    minutes = int(time_diff / 60)
    seconds = int(time_diff % 60)
    message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
    QMessageBox.information(mw, "movies2anki", message)

class AudioInfo(QDialog):

    def __init__(self, map_ids, map_data, parent=None):
        super(AudioInfo, self).__init__(parent)

        self.map_data = map_data
        self.map_ids = map_ids
        self.initUI()

    def initUI(self):
        okButton = QPushButton("OK")
        okButton.clicked.connect(self.ok)

        vbox = QVBoxLayout()
        hbox = QHBoxLayout()

        grid = QGridLayout()
        grid.setSpacing(10)

        # grid.addWidget(reviewEdit, 1, 1, 1, 3)
        hbox.addStretch(1)
        hbox.addWidget(okButton)

        for idx, video_path in enumerate(self.map_data):
            video_filename = os.path.basename(video_path)
            audio_tracks = self.map_data[video_path]

            i_selected = 0
            btn_label = QLabel(video_filename)
            btn_cbox = QComboBox()
            # btn_cbox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            for i in audio_tracks:
                title = audio_tracks[i]['title']
                if title == '(unavailable)':
                    title = ''
                lang = audio_tracks[i]['lang']
                if not lang:
                    lang = '???'
                print('i:', i)
                if audio_tracks[i]['selected'] == 'yes':
                    i_selected = i - 1
                    print('selected:', i_selected)
                item_title = '{}: {}'.format(i, lang)
                if title:
                    item_title += ' ({})'.format(title)
                btn_cbox.addItem(item_title)
            btn_cbox.setCurrentIndex(i_selected)
            btn_cbox.currentIndexChanged.connect(lambda i: self.setAudioStream(video_path, i))
            grid.addWidget(btn_label, idx + 1, 1)
            grid.addWidget(btn_cbox, idx + 1, 2)

        grid.setColumnStretch(1,1)
        grid.setRowMinimumHeight(len(self.map_data)+1, 30)

        vbox.addLayout(grid)
        vbox.addLayout(hbox)

        self.setLayout(vbox)

        self.setWindowTitle('[movies2anki] Select Audio Streams')
        self.setModal(True)

        # self.setMinimumSize(400, 300)
        self.adjustSize()
        self.setMinimumWidth(450)

    def setAudioStream(self, video_path, i):
        print('setAudioStream:', video_path, i)
        self.map_ids[video_path] = i

    def ok(self):
        self.done(1)

    def cancel(self):
        self.done(0)

def update_media():
    global ffmpeg_executable

    if ffmpeg_executable is None:
        ffmpeg_executable = find_executable("ffmpeg")

    if is_mac and ffmpeg_executable is None:
        ffmpeg_executable = '/usr/local/bin/ffmpeg'
        if not os.path.exists(ffmpeg_executable):
            ffmpeg_executable = None

    # if not ffmpeg_executable:
    #     return showWarning(r"""<p>Please install <a href='https://www.ffmpeg.org'>FFmpeg</a>.</p>
    #     On Windows download FFmpeg and either update PATH environment variable or put ffmpeg.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)

    if hasattr(mw, 'worker') and mw.worker != None and mw.worker.isRunning():
        mw.progressDialog.setWindowState(mw.progressDialog.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        mw.progressDialog.activateWindow()
        return

    data = []
    for model_name in ["movies2anki (add-on)", "movies2anki - subs2srs", "movies2anki - subs2srs (video)", "movies2anki - subs2srs (audio)"]:
        m = mw.col.models.by_name(model_name)

        if m == None:
            continue

        mid = m['id']
        query = "mid:%s" % (mid)
        res = mw.col.find_notes(query)

        if len(res) == 0:
            continue


        if "Audio Sound" not in mw.col.models.field_names(m):
            mw.progress.start()
            fm = mw.col.models.new_field("Audio Sound")
            mw.col.models.addField(m, fm)
            mw.col.models.save(m)
            mw.progress.finish()

        if "Video Sound" not in mw.col.models.field_names(m) and m["name"] in ["movies2anki (add-on)", "movies2anki - subs2srs (video)"]:
            mw.progress.start()
            fm = mw.col.models.new_field("Video Sound")
            mw.col.models.addField(m, fm)
            mw.col.models.save(m)
            mw.progress.finish()

        nids = sorted(res)
        for nid in nids:
            note = mw.col.get_note(nid)

            if note["Audio Sound"] == "" or not os.path.exists(os.path.join(mw.col.media.dir(), note["Audio"])):
                data.append(note)
            elif m["name"] in ["movies2anki (add-on)", "movies2anki - subs2srs (video)"] and (note["Video Sound"] == "" or not os.path.exists(os.path.join(mw.col.media.dir(), note["Video"]))):
                data.append(note)

    if len(data) == 0:
        tooltip("Nothing to update")
        return

    if hasattr(mw, 'progressDialog'):
        del mw.progressDialog

    mw.progressDialog = QProgressDialog()
    mw.progressDialog.setWindowIcon(QIcon(":/icons/anki.png"))
    flags = mw.progressDialog.windowFlags()
    flags ^= Qt.WindowType.WindowMinimizeButtonHint
    mw.progressDialog.setWindowFlags(flags)
    # mw.progressDialog.setFixedSize(300, mw.progressDialog.height())
    mw.progressDialog.setMinimumWidth(450)
    mw.progressDialog.setFixedHeight(mw.progressDialog.height())
    mw.progressDialog.setCancelButtonText("Cancel")
    mw.progressDialog.setMinimumDuration(0)
    mw.progressDialog.canceled.connect(cancelProgressDialog)
    mw.progress_bar = QProgressBar(mw.progressDialog)
    mw.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    mw.progressDialog.setBar(mw.progress_bar)
    mw.progressDialog.setModal(True)
    mw.progressDialog.show()

    map_ids = {}
    map_data = {}

    is_multi_audio_streams = False

    mw.progressDialog.setWindowTitle("[movies2anki] Processing Audio Streams...")

    global is_cancel
    is_cancel = False

    # select the audio stream selected by mpv
    videos = []
    for idx, note in enumerate(data):
        if note["Path"] in videos:
            continue
        videos.append(note["Path"])

    for video_path in videos:
        QApplication.instance().processEvents()
        if is_cancel:
            break

        video_filename = os.path.basename(video_path)
        mw.progressDialog.setLabelText(video_filename)

        mw.progressDialog.setValue((idx * 1.0 / len(videos)) * 100)

        ffmpeg_audio_id = -1
        with no_bundled_libs():
            audio_tracks = {}
            try:
                cmd = [mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/count}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path]
                logger.debug('check_output: {}'.format('Started'))
                logger.debug('check_output: {}'.format(join_and_add_double_quotes(cmd)))
                QApplication.instance().processEvents()
                if is_cancel:
                    return
                with tempfile.TemporaryFile() as tmpfile:
                    subprocess.check_call(cmd, startupinfo=info, encoding='utf-8', stdout=tmpfile, timeout=5)
                    tmpfile.seek(0)
                    track_list_count = tmpfile.read().decode('utf-8').strip()
                logger.debug('check_output: {}, {}'.format('Finished', track_list_count))
                track_list_count = track_list_count.replace('term-msg:', '').replace('[term-msg]', '')
                track_list_count = int(track_list_count)
                for i in range(track_list_count):
                    QApplication.instance().processEvents()
                    if is_cancel:
                        return
                    track_type = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/type}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path], startupinfo=info, encoding='utf-8', timeout=3)
                    if track_type.strip() == 'audio':
                        audio_tracks[i] = {
                            'title': '',
                            'lang': '',
                            'selected': '',
                            'ffmpeg-index': ''
                        }
                for idx, i in enumerate(audio_tracks):
                    QApplication.instance().processEvents()
                    if is_cancel:
                        return
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/selected}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path], startupinfo=info, encoding='utf-8', timeout=3)
                    audio_tracks[i]['selected'] = output.strip()
                    QApplication.instance().processEvents()
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/title}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path], startupinfo=info, encoding='utf-8', timeout=3)
                    audio_tracks[i]['title'] = output.strip()
                    QApplication.instance().processEvents()
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/lang}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path], startupinfo=info, encoding='utf-8', timeout=3)
                    audio_tracks[i]['lang'] = output.strip()
                    QApplication.instance().processEvents()
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/ff-index}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", video_path], startupinfo=info, encoding='utf-8', timeout=3)
                    ffmpeg_audio_id = idx
                    audio_tracks[i]['ffmpeg-index'] = idx
                if len(audio_tracks) > 1:
                    is_multi_audio_streams = True
            except Exception as e:
                print(traceback.format_exc())
                if os.environ.get("ADDON_DEBUG"):
                    input('Press any key to continue...')
            if ffmpeg_audio_id == -1:
                # select the last audio stream
                audio_tracks = {}
                cmd = [ffprobe_executable, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", video_path]
                logger.debug('ffprobe audio_streams: {}'.format('Started'))
                logger.debug('ffprobe audio_streams: {}'.format(join_and_add_double_quotes(cmd)))
                QApplication.instance().processEvents()
                if is_cancel:
                    return
                output = check_output(cmd, startupinfo=info, encoding='utf-8')
                logger.debug('ffprobe audio_streams: {}, {}'.format('Finished', output))
                json_data = json.loads(output)
                for idx, stream in enumerate(json_data["streams"]):
                    ffmpeg_audio_id = idx
                    stream_tags = stream.get('tags', {})
                    audio_tracks[idx] = {
                        'title': stream_tags.get('title', ''),
                        'lang': stream_tags.get('language', ''),
                        'selected': '',
                        'ffmpeg-index': stream["index"]
                    }
                if len(json_data["streams"]):
                    is_multi_audio_streams = True
        if ffmpeg_audio_id < 0:
            ffmpeg_audio_id = 0

        map_ids[video_path] = ffmpeg_audio_id
        map_data[video_path] = audio_tracks
        logger.debug(f'audio_id: {ffmpeg_audio_id}')

    if is_cancel:
        return

    mw.progressDialog.setValue(100)
    mw.progressDialog.setLabelText('')

    QApplication.instance().processEvents()

    if is_multi_audio_streams:
        AudioInfo(map_ids, map_data).exec_()

    mw.progressDialog.setWindowTitle("[movies2anki] Generating Media...")
    mw.progressDialog.setValue(0)
    mw.progressDialog.setModal(False)

    QApplication.instance().processEvents()

    mw.worker = MediaWorker(data, map_ids)
    mw.worker.updateProgress.connect(setProgress)
    mw.worker.updateProgressText.connect(setProgressText)
    mw.worker.updateNote.connect(saveNote)
    mw.worker.jobFinished.connect(finishProgressDialog)
    mw.worker.start()

def stopWorker():
    if hasattr(mw, 'worker') and mw.worker != None:
        mw.worker.cancel()

addHook("unloadProfile", stopWorker)

# Fix if "Replay buttons on card" add-on isn't installed
def myLinkHandler(reviewer, url, _old):
    if url.startswith("ankiplay"):
        play(url[8:])
    else:
        return _old(reviewer, url)

Reviewer._linkHandler = wrap(Reviewer._linkHandler, myLinkHandler, "around")

update_media_action = QAction("Generate Mobile Cards...", mw)
update_media_action.triggered.connect(update_media)
mw.form.menuTools.addAction(update_media_action)


def on_card_answer(reviewer, card, ease):
    note = mw.col.get_note(card.nid)
    if not note.note_type()["name"].startswith("movies2anki"):
        return
    if note["Id"] != note["Audio"][:-4]:
        note["Id"] = note["Audio"][:-4]
        note.flush()

try:
    from aqt import gui_hooks
    gui_hooks.reviewer_did_answer_card.append(on_card_answer)
except:
    pass