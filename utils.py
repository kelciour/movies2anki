import subprocess

from subprocess import check_output

from anki.utils import noBundledLibs

try:
    from aqt.sound import si
except ImportError as e:
    from anki.sound import si

def timeToSeconds(t):
    hours, minutes, seconds, milliseconds = t.split('.')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) * 0.001

def secondsToTime(seconds, sep="."):
    ms = (seconds * 1000) % 1000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return "%d%s%02d%s%02d.%03d" % (h, sep, m, sep, s, ms)

def getSelectedAudioId(filepath, mpv_executable, ffprobe_executable):
    with noBundledLibs():
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

