# -*- coding: utf-8 -*-

import subprocess, sys, json, time, re, os, atexit
try:
    from aqt.sound import play, _packagedCmd, si
    import aqt.sound as sound # Anki 2.1.17+
except ImportError:
    from anki.sound import play, _packagedCmd, si
    import anki.sound as sound

from anki.lang import _, ngettext
from anki.hooks import addHook, wrap
from anki.utils import noBundledLibs, stripHTML
from aqt.reviewer import Reviewer
from aqt import mw, browser
from aqt.utils import showWarning, showInfo, tooltip, isWin, isMac
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
if isWin:
    info = subprocess.STARTUPINFO()
    info.wShowWindow = subprocess.SW_HIDE
    info.dwFlags = subprocess.STARTF_USESHOWWINDOW

p = None

from distutils.spawn import find_executable

if isMac and '/usr/local/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/usr/local/bin:" + os.environ['PATH']

if isMac and '/opt/homebrew/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/opt/homebrew/bin:" + os.environ['PATH']

mpv_executable, env = find_executable("mpv"), os.environ

if mpv_executable is None and isMac:
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
if ffmpeg_executable is None:
    ffmpeg_executable = '/usr/local/bin/ffmpeg'

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

    path = stripHTML(path)

    # elif path.endswith(".mp3"): # workaround to fix replay button (R) without refreshing webview.
    #     path = fields["Audio"]
    # else:
    #     path = fields["Video"]

    # if mw.reviewer.state == "question" and mw.reviewer.card.model()["name"] == "movies2anki - subs2srs (video)":
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
        if isWin:
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
        if isMac and os.path.exists(IINA_DIR):
            args = [o.replace("--", "--mpv-") for o in args]
            cmd = [IINA_DIR] + args + [fullpath]
        else:
            cmd = [mpv_executable] + args + [fullpath]

    if p != None and p.poll() is None:
        p.kill()

    if with_bundled_libs:
        p = subprocess.Popen(cmd)
        return

    with noBundledLibs():
        p = subprocess.Popen(cmd)

def queueExternalAV(self, path):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.model()["name"] == "movies2anki (add-on)" or mw.reviewer.card.model()["name"].startswith("movies2anki - subs2srs")):
        queueExternal(path)
    else:
        _player(path)

def queueExternal(path):
    global p, _player

    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.model()["name"] == "movies2anki (add-on)" or mw.reviewer.card.model()["name"].startswith("movies2anki - subs2srs")):
        # if mw.reviewer.state == "answer" and path.endswith(".mp4"):
        #     return

        try:
            clearExternalQueue()
            ret = playVideoClip(path.filename if av_player else path)
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
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.model()["name"] == "movies2anki (add-on)" or mw.reviewer.card.model()["name"].startswith("movies2anki - subs2srs")):
        try:
            clearExternalQueue()
            playVideoClip(state=state, shift=shift)
        except OSError:
            return showWarning(r"""<p>Please install <a href='https://mpv.io'>mpv</a>.</p>
                On Windows download mpv and either update PATH environment variable or put mpv.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)

def selectVideoPlayer():
    global VLC_DIR
    try:
        if isMac and os.path.exists(IINA_DIR):
            return

        if mpv_executable is None:
            raise OSError()

        with noBundledLibs():
            p = subprocess.Popen([mpv_executable, "--version"], startupinfo=info)
        
        if p != None and p.poll() is None:
            p.kill()
    except OSError:
        if VLC_DIR != "":
            return
        
        if isWin:
            VLC_DIR = r"C:\Program Files\VideoLAN\VLC\vlc.exe"
            if os.path.exists(VLC_DIR):
                return

            VLC_DIR = r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            if os.path.exists(VLC_DIR):
                return
        elif isMac:
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
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.model()["name"] == "movies2anki (add-on)" or mw.reviewer.card.model()["name"].startswith("movies2anki - subs2srs")):
        clearExternalQueue()
        playVideoClip(isEnd=isEnd, isPrev=isPrev, isNext=isNext)

def joinCard(isPrev=False, isNext=False):
    if mw.state == "review" and mw.reviewer.card != None and (mw.reviewer.card.model()["name"] == "movies2anki (add-on)" or mw.reviewer.card.model()["name"].startswith("movies2anki - subs2srs")):
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

        c = mw.reviewer.card.note()
        for name, val in c.items():
            if name == "Id":
                c[name] = "%s_%s-%s" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end))
            elif name == "Audio":
                c[name] = "%s_%s-%s.mp3" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end))
            elif name == "Video":
                c[name] = "%s_%s-%s.mp4" % (card_prefix, secondsToTime(time_start), secondsToTime(time_end))
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

class MediaWorker(QThread):
    updateProgress = pyqtSignal(int)
    updateProgressText = pyqtSignal(str)
    updateNote = pyqtSignal(str, str, str)
    jobFinished = pyqtSignal(float)

    def __init__(self, data):
        QThread.__init__(self)

        self.data = data
        self.canceled = False
        self.fp = None

    def cancel(self):
        self.canceled = True

        if self.fp != None:
            self.fp.terminate()

    def run(self):
        job_start = time.time()

        mp3gain_executable = find_executable("mp3gain")

        map_ids = {}
        config = mw.addonManager.getConfig(__name__)
        for idx, note in enumerate(self.data):
            if self.canceled:
                break

            self.updateProgress.emit((idx * 1.0 / len(self.data)) * 100)

            fld = note["Audio"]

            time_start, time_end = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", fld).groups()

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

            # select the audio stream selected by mpv
            if note["Path"] not in map_ids:
                with noBundledLibs():
                    audio_id = 0
                    track_list_count = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/count}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", note["Path"]], startupinfo=info, encoding='utf-8')
                    track_list_count = track_list_count.replace('term-msg:', '').replace('[term-msg]', '')
                    track_list_count = int(track_list_count)
                    for i in range(track_list_count):
                        track_type = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/type}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", note["Path"]], startupinfo=info, encoding='utf-8')
                        if track_type.strip() == 'audio':
                            track_selected = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/selected}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", note["Path"]], startupinfo=info, encoding='utf-8')
                            if track_selected.strip() == 'yes':
                                output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/ff-index}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", note["Path"]], startupinfo=info, encoding='utf-8')
                                audio_id = int(output.strip()) - 1
                                break
                    else:
                        # select the last audio stream
                        output = check_output([ffprobe_executable, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", note["Path"]], startupinfo=info, encoding='utf-8')
                        json_data = json.loads(output)
                        for index, stream in enumerate(json_data["streams"]):
                            audio_id = index
                    if audio_id < 0:
                        audio_id = 0

                map_ids[note["Path"]] = audio_id
            
            audio_id = map_ids[note["Path"]]

            # TODO
            vf = "scale=-2:320"

            self.updateProgressText.emit(note["Source"] + "  " + ss)

            af_params = default_af_params
            if NORMALIZE_AUDIO and not (NORMALIZE_AUDIO_WITH_MP3GAIN and mp3gain_executable):
                cmd = [ffmpeg_executable, "-ss", ss, "-i", note["Path"], "-t", str(t), "-af", "loudnorm=%s:print_format=json" % NORMALIZE_AUDIO_FILTER, "-f", "null", "-"]
                with noBundledLibs():
                    output = check_output(cmd, startupinfo=info, encoding='utf-8')
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

            if note["Audio Sound"] == "" or not os.path.exists(note["Audio"]):
                self.fp = None
                cmd = [ffmpeg_executable, "-y", "-ss", ss, "-i", note["Path"], "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
                if af_params:
                    cmd += ["-af", af_params]
                cmd += ["-map", "0:a:{}".format(audio_id), note["Audio"]]

                with noBundledLibs():
                    self.fp = subprocess.Popen(cmd, startupinfo=info)
                    self.fp.wait()

                if NORMALIZE_AUDIO and NORMALIZE_AUDIO_WITH_MP3GAIN and mp3gain_executable:
                    cmd = [mp3gain_executable, "/f", "/q", "/r", "/k", note["Audio"]]
                    with noBundledLibs():
                        self.fp = subprocess.Popen(cmd, startupinfo = info)
                        self.fp.wait()

                if self.canceled:
                    break

                self.updateNote.emit(str(note.id), "Audio Sound", note["Audio"])

            if "Video Sound" in note and (note["Video Sound"] == "" or not os.path.exists(note["Video"])):
                self.fp = None
                cmd = [ffmpeg_executable, "-y", "-ss", ss, "-i", note["Path"], "-strict", "-2", "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
                if af_params:
                    cmd += ["-af", af_params]
                cmd += ["-map", "0:v:0", "-map", "0:a:{}".format(audio_id), "-c:v", "libx264", "-vf", vf, "-profile:v", "baseline", "-level", "3.0", "-c:a", "aac", "-ac", "2", note["Video"]]
                with noBundledLibs():
                    self.fp = subprocess.Popen(cmd, startupinfo=info)
                    self.fp.wait()
                    retcode = self.fp.returncode
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
    mw.worker.cancel()

def setProgress(progress):
    mw.progressDialog.setValue(progress)

def setProgressText(text):
    mw.progressDialog.setLabelText(text)

def saveNote(nid, fld, val):
    note = mw.col.getNote(int(nid))
    note[fld] = "[sound:%s]" % val
    note.flush()

def finishProgressDialog(time_diff):
    mw.progressDialog.done(0)
    minutes = int(time_diff / 60)
    seconds = int(time_diff % 60)
    message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
    QMessageBox.information(mw, "movies2anki", message)

def update_media():
    global ffmpeg_executable

    if ffmpeg_executable is None:
        ffmpeg_executable = find_executable("ffmpeg")

    if isMac and ffmpeg_executable is None:
        ffmpeg_executable = '/usr/local/bin/ffmpeg'

    if not ffmpeg_executable:
        return showWarning(r"""<p>Please install <a href='https://www.ffmpeg.org'>FFmpeg</a>.</p>
        On Windows download FFmpeg and either update PATH environment variable or put ffmpeg.exe in Anki installation folder (C:\Program Files\Anki).""", parent=mw)

    if hasattr(mw, 'worker') and mw.worker != None and mw.worker.isRunning():
        mw.progressDialog.setWindowState(mw.progressDialog.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        mw.progressDialog.activateWindow()
        return
    
    data = []
    for model_name in ["movies2anki (add-on)", "movies2anki - subs2srs", "movies2anki - subs2srs (video)", "movies2anki - subs2srs (audio)"]:
        m = mw.col.models.byName(model_name)

        if m == None:
            continue

        mid = m['id']
        query = "mid:%s" % (mid)
        res = mw.col.findNotes(query)

        if len(res) == 0:
            continue


        if "Audio Sound" not in mw.col.models.fieldNames(m):
            mw.progress.start()
            fm = mw.col.models.newField("Audio Sound")
            mw.col.models.addField(m, fm)
            mw.col.models.save(m)
            mw.progress.finish()

        if "Video Sound" not in mw.col.models.fieldNames(m) and m["name"] in ["movies2anki (add-on)", "movies2anki - subs2srs (video)"]:
            mw.progress.start()
            fm = mw.col.models.newField("Video Sound")
            mw.col.models.addField(m, fm)
            mw.col.models.save(m)
            mw.progress.finish()

        nids = sorted(res)
        for nid in nids:
            note = mw.col.getNote(nid)

            if note["Audio Sound"] == "" or not os.path.exists(note["Audio"]):
                data.append(note)
            elif m["name"] in ["movies2anki (add-on)", "movies2anki - subs2srs (video)"] and (note["Video Sound"] == "" or not os.path.exists(note["Video"])):
                data.append(note)

    if len(data) == 0:
        tooltip("Nothing to update")
        return

    if hasattr(mw, 'progressDialog'):
        del mw.progressDialog

    mw.progressDialog = QProgressDialog()
    mw.progressDialog.setWindowIcon(QIcon(":/icons/anki.png"))
    mw.progressDialog.setWindowTitle("Generating Media")
    flags = mw.progressDialog.windowFlags()
    flags ^= Qt.WindowMinimizeButtonHint
    mw.progressDialog.setWindowFlags(flags)
    # mw.progressDialog.setFixedSize(300, mw.progressDialog.height())
    mw.progressDialog.setMinimumWidth(300)
    mw.progressDialog.setFixedHeight(mw.progressDialog.height())
    mw.progressDialog.setCancelButtonText("Cancel")
    mw.progressDialog.setMinimumDuration(0)
    mw.progress_bar = QProgressBar(mw.progressDialog)
    mw.progress_bar.setAlignment(Qt.AlignCenter)
    mw.progressDialog.setBar(mw.progress_bar)

    mw.worker = MediaWorker(data)
    mw.worker.updateProgress.connect(setProgress)
    mw.worker.updateProgressText.connect(setProgressText)
    mw.worker.updateNote.connect(saveNote)
    mw.worker.jobFinished.connect(finishProgressDialog)
    mw.progressDialog.canceled.connect(cancelProgressDialog)
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
    note = mw.col.getNote(card.nid)
    if not note.model()["name"].startswith("movies2anki"):
        return
    if note["Id"] != note["Audio"][:-4]:
        note["Id"] = note["Audio"][:-4]
        note.flush()

try:
    from aqt import gui_hooks
    gui_hooks.reviewer_did_answer_card.append(on_card_answer)
except:
    pass
