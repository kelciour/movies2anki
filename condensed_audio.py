import json
import os
import time
import re
import subprocess

from collections import defaultdict
from distutils.spawn import find_executable
from subprocess import check_output

from aqt.qt import *
from aqt.utils import showWarning, isMac, tooltip, showText
from anki.hooks import addHook
from anki.utils import noBundledLibs, tmpdir, tmpfile

try:
    from aqt.sound import si
except ImportError:
    from anki.sound import si

from .utils import timeToSeconds, secondsToTime, getSelectedAudioId

from .forms import condensed_audio_exporter

if isMac and '/usr/local/bin' not in os.environ['PATH'].split(':'):
    # https://docs.brew.sh/FAQ#my-mac-apps-dont-find-usrlocalbin-utilities
    os.environ['PATH'] = "/usr/local/bin:" + os.environ['PATH']

mpv_executable = find_executable("mpv")
ffmpeg_executable = find_executable("ffmpeg")
ffprobe_executable = find_executable("ffprobe")

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
        output_directory = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    frm.outputDirBtn.clicked.connect(showOutputDirectoryDialog)

    if not d.exec_():
        return

    output_directory = frm.outputDir.text().strip()
    if not os.path.isdir(output_directory):
        showWarning("The output directory doesn't exist.")
        return

    is_collection_media = frm.mediaDir.isChecked()
    config["condensed_audio_collection.media"] = is_collection_media
    config["condensed_audio_output_directory"] = output_directory
    mw.addonManager.writeConfig(__name__, config)

    mw.checkpoint("Condensed Audio")

    data = []
    notes_to_process = defaultdict(list)
    errors = defaultdict(int)
    audio_map_ids = {}
    for c, nid in enumerate(sorted(nids), 1):
        note = mw.col.getNote(nid)
        m = note.model()

        if not m['name'].startswith('movies2anki'):
            errors["The note type is not supported"] += 1
            continue

        fields = mw.col.models.fieldNames(m)

        if "Audio Sound" not in fields and is_collection_media:
            mw.progress.start()
            fm = mw.col.models.newField("Audio Sound")
            mw.col.models.addField(m, fm)
            mw.col.models.save(m)
            mw.progress.finish()

        audio_file = None
        if "Audio Sound" in fields and not note["Audio Sound"]:
            match = re.fullmatch(r"\[sound:(.*?)\]", note["Audio Sound"])
            if match and os.path.exists(match.group(1)):
                audio_file = match.group(1)
            else:
                note["Audio Sound"] = ""
        
        if audio_file is None and "Audio" not in fields:
            errors["The Audio field doesn't exist"] += 1
            continue

        if audio_file is None and not note["Audio"]:
            errors["The Audio field is empty"] += 1
            continue

        if audio_file is None and "Path" not in fields:
            errors["The Path field doesn't exist"] += 1
            continue

        if audio_file is None and  not os.path.exists(note["Path"]):
            errors["Can't find the source file specified in the Path field"] += 1
            continue

        if "Audio Sound" in fields and (note["Audio Sound"] == "" or not os.path.exists(note["Audio"])):
            data.append(note)

        if os.path.exists(note["Audio"]) or is_collection_media:
            notes_to_process[note["Path"]].append(os.path.abspath(note["Audio"]))
        else:
            notes_to_process[note["Path"]].append(os.path.abspath(os.path.join(tmpdir(), note["Audio"])))

    if len(notes_to_process) == 0:
        if errors:
            showText("Nothing to export.\n\n" + \
            "A few notes were skipped with the following errors: " + \
                json.dumps(errors, sort_keys=True, indent=4))
        else:
            tooltip("Nothing to export")
        return

    global progressDialog
    global worker

    progressDialog = QProgressDialog(browser)
    progressDialog.setWindowIcon(QIcon(":/icons/anki.png"))
    progressDialog.setWindowTitle("Generating Media")
    flags = progressDialog.windowFlags()
    flags ^= Qt.WindowMinimizeButtonHint
    progressDialog.setWindowFlags(flags)
    progressDialog.setMinimumWidth(300)
    progressDialog.setFixedHeight(progressDialog.height())
    progressDialog.setCancelButtonText("Cancel")
    progressDialog.setMinimumDuration(0)
    progress_bar = QProgressBar(progressDialog)
    progress_bar.setAlignment(Qt.AlignCenter)
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
        note = mw.col.getNote(int(nid))
        note[fld] = "[sound:%s]" % val
        note.flush()

    def finishProgressDialog(time_diff):
        progressDialog.done(0)
        minutes = int(time_diff / 60)
        seconds = int(time_diff % 60)
        message = "Processing completed in %s minutes %s seconds." % (minutes, seconds)
        if not errors:
            QMessageBox.information(browser, "movies2anki", message)
        else:
            showText(message + '\n\n' + \
                "A few notes were skipped with the following errors: " + \
                json.dumps(errors, sort_keys=True, indent=4))
        browser.onReset()

    worker = AudioExporter(data, notes_to_process, output_directory, is_collection_media)
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

    def __init__(self, data, notes_to_process, output_directory, is_collection_media):
        QThread.__init__(self)

        self.data = data
        self.notes_to_process = notes_to_process
        self.output_directory = output_directory
        self.is_collection_media = is_collection_media
        self.canceled = False
        self.fp = None

    def cancel(self):
        self.canceled = True

        if self.fp != None:
            self.fp.terminate()

    def run(self):
        job_start = time.time()

        audio_map_ids = {}
        for idx, note in enumerate(self.data):
            if self.canceled:
                break

            self.updateProgress.emit((idx * 1.0 / len(self.data)) * 100)
            self.updateProgressText.emit(note["Audio"])

            fld = note["Audio"]

            time_start, time_end = re.match(r"^.*?_(\d+\.\d\d\.\d\d\.\d+)-(\d+\.\d\d\.\d\d\.\d+).*$", fld).groups()

            ss = secondsToTime(timeToSeconds(time_start), sep=":")
            se = secondsToTime(timeToSeconds(time_end), sep=":")
            t = timeToSeconds(time_end) - timeToSeconds(time_start)

            af_d = 0.1
            af_st = 0
            af_to = t - af_d
            af_params = "afade=t=in:st={:.3f}:d={:.3f},afade=t=out:st={:.3f}:d={:.3f}".format(af_st, af_d, af_to, af_d)

            if note["Path"] in audio_map_ids:
                audio_id = audio_map_ids[note["Path"]]
            else:
                audio_id = getSelectedAudioId(note["Path"], mpv_executable, ffprobe_executable)
                audio_map_ids[note["Path"]] = audio_id

            audio_file = note["Audio"]
            if not self.is_collection_media:
                audio_file = os.path.join(tmpdir(), note["Audio"])

            cmd = [ffmpeg_executable]
            cmd += ["-y", "-ss", ss, "-i", note["Path"], "-loglevel", "quiet", "-t", "{:.3f}".format(t)]
            cmd += ["-af", af_params]
            cmd += ["-map", "0:a:{}".format(audio_id), audio_file]
            with noBundledLibs():
                p = subprocess.Popen(cmd, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si)
                p.wait()

            if self.canceled:
                break

            if self.is_collection_media:
                self.updateNote.emit(str(note.id), "Audio Sound", note["Audio"])

        self.updateProgressTitle.emit("Exporting Condensed Audio Files")
        for idx, path in enumerate(self.notes_to_process):
            self.updateProgress.emit((idx * 1.0 / len(self.notes_to_process)) * 100)

            list_to_concatenate = tmpfile(suffix='.txt')
            output_file = os.path.splitext(os.path.basename(path))[0] + '.mp3'

            self.updateProgressText.emit(output_file)
            
            with open(list_to_concatenate, "w") as f:
                for audio_file in self.notes_to_process[path]:
                    audio_file = audio_file.replace("'", r"'\''")
                    f.write("file '{}'\n".format(audio_file))

            cmd = [ffmpeg_executable, "-y", "-f", "concat", "-safe", "0", "-i", list_to_concatenate, "-c", "copy", os.path.join(self.output_directory, output_file)]
            with noBundledLibs():
                p = subprocess.Popen(cmd, shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=si)
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
    updateNotes(browser, nids)


def setupMenu(browser):
    menu = browser.form.menuEdit
    menu.addSeparator()
    a = menu.addAction('Export Condensed Audio')
    a.triggered.connect(lambda _, b=browser: onCondensedAudio(b))


addHook("browser.setupMenus", setupMenu)