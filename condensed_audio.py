import json
import os
import time
import re
import subprocess
import traceback

from collections import defaultdict
from distutils.spawn import find_executable
from subprocess import check_output

from aqt import mw
from aqt.qt import *
from aqt.utils import showWarning, is_mac, tooltip, showText
from anki.hooks import addHook
from anki.utils import no_bundled_libs, tmpdir, tmpfile

from . import media

try:
    from aqt.sound import si
except ImportError:
    from anki.sound import si

from .utils import timeToSeconds, secondsToTime, getSelectedAudioId

try:
    from .forms import condensed_audio_exporter_qt6 as condensed_audio_exporter
except:
    from .forms import condensed_audio_exporter_qt5 as condensed_audio_exporter

if is_mac and '/usr/local/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/usr/local/bin:" + os.environ['PATH']

ffmpeg_executable = find_executable("ffmpeg")

def updateNotes(browser, nids):
    mw = browser.mw

    d = QDialog(browser)
    frm = condensed_audio_exporter.Ui_Dialog()
    frm.setupUi(d)

    config = mw.addonManager.getConfig(__name__)

    is_collection_media = config.get('condensed_audio_collection.media', False)
    frm.mediaDir.setChecked(is_collection_media)

    def showOutputDirectoryDialog():
        fname = QFileDialog.getExistingDirectory(directory = output_directory)
        if len(fname) != 0:
            frm.outputDir.setText(fname)

    output_directory = config.get('condensed_audio_output_directory', '')
    if output_directory:
        frm.outputDir.setText(output_directory)
    else:
        output_directory = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        )
    frm.outputDirBtn.clicked.connect(showOutputDirectoryDialog)

    if not d.exec():
        return

    output_directory = frm.outputDir.text().strip()
    if not os.path.isdir(output_directory):
        showWarning("The output directory doesn't exist.")
        return

    is_collection_media = frm.mediaDir.isChecked()
    config["condensed_audio_collection.media"] = is_collection_media
    config["condensed_audio_output_directory"] = output_directory
    mw.addonManager.writeConfig(__name__, config)

    data = []
    notes_to_process = defaultdict(list)
    errors = defaultdict(int)
    audio_map_ids = {}
    mw.progress.start(parent=browser)
    skipped = []
    for c, nid in enumerate(sorted(nids), 1):
        note = mw.col.get_note(nid)
        m = note.note_type()

        if not m['name'].startswith('movies2anki'):
            errors["The note type is not supported"] += 1
            continue

        fields = mw.col.models.field_names(m)

        if "Audio" not in fields:
            errors["The Audio field doesn't exist"] += 1
            continue

        if not note["Audio"]:
            errors["The Audio field is empty"] += 1
            continue

        audio_file = ""
        if "Audio" in note:
            audio_file = note["Audio"]
        if '[sound:' in audio_file:
            audio_file = audio_file.replace('[sound:', '')
            audio_file = audio_file.replace(']', '')

        m = re.match(r"^(.*?)_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", audio_file)
        video_id = m.group(1)
        if video_id in skipped:
            errors["Can't find the path to the source video file"] += 1
            continue
        try:
            if "Path" in note and note["Path"] != '':
                path = note["Path"]
            else:
                path = media.get_path_in_media_db(video_id, parent=browser)
        except:
            errors["Can't find the path to the source video file"] += 1
            skipped.append(video_id)
            continue

        try:
            audio_id = media.getAudioId(video_id)
            audio_map_ids[video_id] = audio_id
        except:
            errors["Can't find audio_id in user_files/media.db."] += 1
            continue

        if is_collection_media:
            audio_path = os.path.join(mw.col.media.dir(), audio_file)
            notes_to_process[path].append(audio_path)
            if not os.path.exists(audio_path):
                data.append((note, path, audio_path, audio_file))
        else:
            audio_path = os.path.abspath(os.path.join(tmpdir(), audio_file))
            notes_to_process[path].append(audio_path)
            data.append((note, path, audio_path, audio_file))
    mw.progress.finish()

    if len(notes_to_process) == 0:
        if errors:
            showText("Nothing to export.\n\n" + \
            "A few notes were skipped with the following errors: " + \
                json.dumps(errors, sort_keys=True, indent=4), parent=browser)
        else:
            tooltip("Nothing to export")
        return

    global progressDialog
    global worker

    progressDialog = QProgressDialog(browser)
    progressDialog.setWindowIcon(QIcon(":/icons/anki.png"))
    progressDialog.setWindowTitle("Generating Media")
    flags = progressDialog.windowFlags()
    flags ^= Qt.WindowType.WindowMinimizeButtonHint
    progressDialog.setWindowFlags(flags)
    progressDialog.setMinimumWidth(300)
    progressDialog.setFixedHeight(progressDialog.height())
    progressDialog.setCancelButtonText("Cancel")
    progressDialog.setMinimumDuration(0)
    progress_bar = QProgressBar(progressDialog)
    progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    progressDialog.setBar(progress_bar)

    def cancelProgressDialog():
        worker.cancel()

    def setProgress(progress):
        progressDialog.setValue(progress)

    def setProgressText(text):
        progressDialog.setLabelText(text)

    def setProgressTitle(text):
        progressDialog.setWindowTitle(text)

    def saveNote(nid, fld, val):
        note = mw.col.get_note(int(nid))
        note[fld] = "[sound:%s]" % val
        note.flush()

    def finishProgressDialog(time_diff):
        progressDialog.done(0)
        minutes = int(time_diff / 60)
        seconds = int(time_diff % 60)
        message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
        if not worker.errors:
            QMessageBox.information(browser, "movies2anki", message)
        else:
            msg = message + '\n\n' + \
                "A few notes were skipped with the following errors: " + \
                json.dumps(worker.errors, sort_keys=True, indent=4)
            if worker.ffmpeg_errors:
                msg += "\n\nFFmpeg encoding errors:\n" + '\n'.join(worker.ffmpeg_errors)
            showText(msg, parent=browser)
        browser.onReset()

    worker = AudioExporter(data, notes_to_process, config, errors, audio_map_ids)
    worker.updateProgress.connect(setProgress)
    worker.updateProgressText.connect(setProgressText)
    worker.updateProgressTitle.connect(setProgressTitle)
    worker.updateNote.connect(saveNote)
    worker.jobFinished.connect(finishProgressDialog)
    progressDialog.canceled.connect(cancelProgressDialog)
    worker.start()


class AudioExporter(QThread):
    updateProgress = pyqtSignal(int)
    updateProgressText = pyqtSignal(str)
    updateProgressTitle = pyqtSignal(str)
    updateNote = pyqtSignal(str, str, str)
    jobFinished = pyqtSignal(float)

    def __init__(self, data, notes_to_process, config, errors, audio_map_ids):
        QThread.__init__(self)

        self.data = data
        self.notes_to_process = notes_to_process
        self.output_directory = config["condensed_audio_output_directory"]
        self.is_collection_media = config["condensed_audio_collection.media"]
        self.audio_fade = config["audio fade in/out"]
        self.canceled = False
        self.errors = errors
        self.audio_map_ids = audio_map_ids
        self.fp = None
        self.ffmpeg_errors = []

    def cancel(self):
        self.canceled = True

        if self.fp != None:
            self.fp.terminate()

    def run(self):
        job_start = time.time()

        audio_path_errors = []
        for idx, (note, path, audio_path, audio_file) in enumerate(self.data):
            if self.canceled:
                break

            self.updateProgress.emit((idx * 1.0 / len(self.data)) * 100)
            self.updateProgressText.emit(audio_file)

            video_id, time_start, time_end = re.match(r"^(.+?)_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", audio_file).groups()

            ss = secondsToTime(timeToSeconds(time_start), sep=":")
            se = secondsToTime(timeToSeconds(time_end), sep=":")
            t = timeToSeconds(time_end) - timeToSeconds(time_start)

            if self.audio_fade:
                af_d = float(self.audio_fade)
                af_st = 0
                af_to = t - af_d
                af_params = "afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(af_st, af_d, af_to, af_d)
            else:
                af_params = ""

            audio_id = self.audio_map_ids[video_id]

            cmd = [ffmpeg_executable]
            cmd += ["-y", "-ss", ss, "-i", path, "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
            if af_params:
                cmd += ["-af", af_params]
            cmd += ["-map", "0:a:{}".format(audio_id-1), audio_path]
            with no_bundled_libs():
                p = subprocess.Popen(cmd, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=si)
                ret = p.wait()

            if ret != 0:
                audio_path_errors.append(audio_path)
                self.errors["Failed to encode the audio file"] += 1
                cmd_debug = " ".join([c if " " not in c else '"' + c + '"' for c in cmd])
                cmd_debug = cmd_debug.replace(' -loglevel quiet ', ' ')
                self.ffmpeg_errors.append(cmd_debug)

            if self.canceled:
                break

            if self.is_collection_media:
                if 'Audio Sound' in note:
                    self.updateNote.emit(str(note.id), "Audio Sound", audio_file)
                else:
                    self.updateNote.emit(str(note.id), "Audio", audio_file)

        if not self.canceled:
            self.updateProgressTitle.emit("Exporting Condensed Audio Files")

        for idx, path in enumerate(self.notes_to_process):
            if self.canceled:
                break

            self.updateProgress.emit((idx * 1.0 / len(self.notes_to_process)) * 100)

            list_to_concatenate = tmpfile(suffix='.txt')
            output_file = os.path.splitext(os.path.basename(path))[0] + '.mp3'

            self.updateProgressText.emit(output_file)

            with open(list_to_concatenate, "w", encoding="utf-8") as f:
                for audio_path in self.notes_to_process[path]:
                    if audio_path in audio_path_errors:
                        continue
                    audio_path = audio_path.replace("'", r"'\''")
                    f.write("file '{}'\n".format(audio_path))

            cmd = [ffmpeg_executable, "-y", "-f", "concat", "-safe", "0", "-i", list_to_concatenate, "-c", "copy", os.path.join(self.output_directory, output_file)]
            with no_bundled_libs():
                p = subprocess.Popen(cmd, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=si)
                p.wait()

        job_end = time.time()
        time_diff = (job_end - job_start)

        if not self.canceled:
            self.updateProgress.emit(100)
            self.jobFinished.emit(time_diff)


def onCondensedAudio(browser):
    nids = browser.selectedNotes()
    if not nids:
        tooltip("No cards selected.")
        return
    if not ffmpeg_executable:
        return showWarning(r"""<p>Export Condensed Audio depends on <a href='https://www.ffmpeg.org'>ffmpeg</a>
            to concatenate media files (<a href="https://trac.ffmpeg.org/wiki/Concatenate">https://trac.ffmpeg.org/wiki/Concatenate</a>),
            but couldn't find it in the PATH environment variable.</p>
            """)
    updateNotes(browser, nids)


def setupMenu(browser):
    menu = browser.form.menuEdit
    menu.addSeparator()
    a = menu.addAction('Export Condensed Audio')
    a.triggered.connect(lambda _, b=browser: onCondensedAudio(b))


addHook("browser.setupMenus", setupMenu)