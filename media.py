import os
import json

from aqt import mw, gui_hooks
from aqt.utils import getFile

media_db = None

media_db_path = os.path.join(os.path.dirname(__file__), "user_files", "media.db")

def get_media_db():
    global media_db
    if media_db is not None:
        return media_db
    with open(media_db_path, 'r', encoding='utf-8') as f_db:
        media_db = json.load(f_db)
    return media_db

def save_media_db():
    global media_db
    if media_db is None:
        return
    with open(media_db_path, 'w', encoding='utf-8') as f_db:
        json.dump(media_db, f_db, indent=4, ensure_ascii=False)

def addVideoFile(video_id, video_path, audio_id):
    media_db = get_media_db()
    if video_id not in media_db:
        media_db[video_id] = {}
    media_db[video_id]["path"] = video_path
    if audio_id != -1:
        media_db[video_id]["audio_id"] = audio_id
    save_media_db()

def getAudioId(video_id):
    media_db = get_media_db()
    d = media_db.get(video_id, {})
    if 'audio_id' in d:
        return d['audio_id']
    else:
        raise Exception("AUDIO ID NOT FOUND")

def setAudioId(video_id, audio_id):
    media_db = get_media_db()
    d = media_db.get(video_id, {})
    d['audio_id'] = audio_id
    save_media_db()

def get_path_in_media_db(video_id, parent=None, ask=True):
    media_db = get_media_db()
    try:
        fullpath = media_db[video_id]["path"]
        if not os.path.exists(fullpath):
            raise Exception("PATH DOESN'T EXIST")
    except:
        if not ask:
            raise Exception("PATH IS NOT FOUND: " + video_id)
        config = mw.addonManager.getConfig(__name__)
        if "~input_directory" in config:
            media_directory = config["~input_directory"]
        else:
            media_directory = None
        if parent is None:
            parent = mw
        fullpath = getFile(parent=parent, title="Select the source video file for '{}'".format(video_id), cb=None, dir=media_directory)
        if fullpath:
            if video_id not in media_db:
                media_db[video_id] = {}
            media_db[video_id]["path"] = fullpath
            save_media_db()
        else:
            print("PATH IS NOT SET:", video_id)
            raise Exception("PATH IS NOT SET: " + video_id)
    return fullpath

def move_old_media_db_from_config_to_user_folder():
    config = mw.addonManager.getConfig(__name__)
    media_db = get_media_db()
    if "~media" in config:
        for video_id in config["~media"]:
            if video_id not in media_db:
                media_db[video_id] = config["~media"][video_id]
        del config["~media"]
        mw.addonManager.writeConfig(__name__, config)
        save_media_db()

gui_hooks.main_window_did_init.append(move_old_media_db_from_config_to_user_folder)
