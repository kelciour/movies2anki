# !/usr/bin/env python 
# -*- coding: utf-8

import codecs
import glob
import os
import re
import shutil
import string

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

def format_filename(deck_name):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    filename = ''.join(c for c in deck_name if c in valid_chars)
    filename = filename.replace(' ','_')
    return filename

def write_tsv_file(deck_name, en_subs, ru_subs):
    prefix = format_filename(deck_name)
    f_out = open(prefix + ".tsv", 'w')

    ffmpeg_split_timestamps = []
    for idx in range(len(en_subs)):
        start_time = seconds_to_tsv_time(en_subs[idx][0])
        end_time = seconds_to_tsv_time(en_subs[idx][1])

        en_sub = en_subs[idx][2]
        en_sub = re.sub('\n', ' ', en_sub)
        ru_sub = ru_subs[idx][2]
        ru_sub = re.sub('\n', ' ', ru_sub)

        tag = prefix 
        sequence = str(idx + 1).zfill(3) + "_" + start_time
        sound = prefix + "_" + start_time + "-" + end_time + ".mp3"
        video = prefix + "_" + start_time + "-" + end_time + ".mp4"

        f_out.write(tag + "\t" + sequence + "\t[sound:" + sound + "]\t[sound:" + video + "]\t" + en_sub + "\t" + ru_sub)
        f_out.write('\n')

        ffmpeg_split_timestamps.append((prefix + "_" + start_time + "-" + end_time, 
            seconds_to_ffmpeg_time(en_subs[idx][0]), 
            seconds_to_ffmpeg_time(en_subs[idx][1])))

    f_out.close()

    return ffmpeg_split_timestamps

def create_or_clean_dir(directory):
    if os.path.exists(directory):
        print "Remove dir " + directory
        shutil.rmtree(directory)
    print "Create dir " + directory
    os.makedirs(directory)

def convert_video(video_file, ffmpeg_split_timestamps):
    for chunk in ffmpeg_split_timestamps:
        filename = chunk[0]
        ss = chunk[1]
        to = chunk[2]

        print ss
        
        call(["ffmpeg", "-ss", ss, "-i", video_file, "-strict", "-2", "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:v:0", "-map", "0:a:" + str(audio_id), "-c:v", "libx264",
                "-s", "480x320", "-c:a", "libmp3lame", "-ac", "2", "-copyts", "collection.media/" + filename + ".mp4"])
        call(["ffmpeg", "-ss", ss, "-i", video_file, "-loglevel", "quiet", "-ss", ss, "-to", to, "-map", "0:a:" + str(audio_id), "-copyts", "collection.media/" + filename + ".mp3"])

def guess_srt_file(video_file, mask_list, default_filename):
    for mask in mask_list:
        glob_result = glob.glob(video_file[:-4] + mask)
        if len(glob_result) == 1:
            print "Found subtitle: " + glob_result[0]
            return glob_result[0]
    else:
        return default_filename

if __name__ == '__main__':

    video_file = "02.Sharpes.Eagle.1993.720p.BluRay.x264-shortbrehd.mkv"
    deck_name = "Sharpes Rifles 02 (1993)"

    directory = "collection.media"

    time_delta = 1.75
    audio_id = 3 # start from 0

    # Имена файлов с английскими и русскими субтитры
    en_srt = guess_srt_file(video_file, ["*eng.srt", "*en.srt"], "en.srt")
    ru_srt = guess_srt_file(video_file, ["*rus.srt", "*ru.srt"], "ru.srt")

    out_en_srt = "out.en.srt"
    out_ru_srt = "out.ru.srt"

    # Загружаем английские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
    print "Loading English subtitles..."
    en_subs = load_subtitle(en_srt)
    print "English subtitles: %s" % len(en_subs)

    # Разбиваем субтитры на фразы
    en_subs_phrases = convert_into_phrases(en_subs, time_delta)
    print "English phrases: %s" % len(en_subs_phrases)

    # Загружаем русские субтитры в формате [(start_time, end_time, subtitle), (...), ...]
    print "Loading Russian subtitles..."
    ru_subs = load_subtitle(ru_srt)
    print "Russian subtitles: %s" % len(ru_subs)

    # Синхронизируем русские субтитры с получившимися английскими субтитрами
    ru_subs_phrases = sync_subtitles(en_subs_phrases, ru_subs)

    # Меняем длительность фраз в английских субтитрах
    change_subtitles_duration(en_subs_phrases)

    # Меняем длительность фраз в русских субтитрах
    change_subtitles_duration(ru_subs_phrases)

    # Записываем английские субтитры
    write_subtitles(out_en_srt, en_subs_phrases)

    # Записываем русские субтитры
    write_subtitles(out_ru_srt, ru_subs_phrases)

    # Формируем tsv файл для импорта в Anki
    ffmpeg_split_timestamps = write_tsv_file(deck_name, en_subs_phrases, ru_subs_phrases)

    # Создаем директорию collection.media
    create_or_clean_dir(directory)
    
    # Конвертируем видео
    convert_video(video_file, ffmpeg_split_timestamps)

