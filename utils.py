import subprocess
import re
import json
import unicodedata

from subprocess import check_output

from anki.utils import no_bundled_libs

try:
    from aqt.sound import si
except ImportError as e:
    from anki.sound import si

MAX_MEDIA_FILENAME_LENGTH = 120 - 30

def timeToSeconds(t):
    hours, minutes, seconds, milliseconds = t.split('.')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) * 0.001

def secondsToTime(seconds, sep="."):
    ms = (seconds * 1000) % 1000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d%s%02d%s%02d.%03d" % (h, sep, m, sep, s, ms)

def getSelectedAudioId(filepath, mpv_executable, ffprobe_executable):
    with no_bundled_libs():
        track_list_count = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/count}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", filepath], shell=False, stdin=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, encoding='utf-8')
        for i in range(int(track_list_count)):
            track_type = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/type}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", filepath], shell=False, stdin=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, encoding='utf-8')
            if track_type.strip() == 'audio':
                track_selected = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/selected}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", filepath], shell=False, stdin=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, encoding='utf-8')
                if track_selected.strip() == 'yes':
                    output = check_output([mpv_executable, "--msg-level=all=no,term-msg=info", '--term-playing-msg=${track-list/' + str(i) + '/ff-index}', "--vo=null", "--ao=null", "--frames=1", "--quiet", "--no-cache", "--", filepath], shell=False, stdin=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, encoding='utf-8')
                    audio_id = int(output.strip()) - 1
                    break
        else:
            # select the last audio stream
            output = check_output([ffprobe_executable, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "a", filepath], shell=False, stdin=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si, encoding='utf-8')
            json_data = json.loads(output)
            for index, stream in enumerate(json_data["streams"]):
                audio_id = index
        if audio_id < 0:
            audio_id = 0
    return audio_id

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
    s = unicodedata.normalize('NFC', s)
    s = re.sub(r'(?u)[^-\w.]', '', s)
    s = s[:MAX_MEDIA_FILENAME_LENGTH]
    s = s.rstrip('.')
    return s
