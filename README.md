#  movies2anki

Convert movies with subtitles to watch them with [Anki](http://ankisrs.net). The movie will be splitted into separated scenes/phrases. I found it useful for improving my listening skills.

Inspired by [subs2srs](http://subs2srs.sourceforge.net/).

## Interface

<img src="http://i.imgur.com/Fv2FoLd.png" width="775" height="499">

* Second subtitle is optional
* Movie mode:
  * Change end time of phrases to the next phrase's start time
  * Add empty phrase if the first subtitle starts after 15 seconds
* Video Dimensions:  
  * If one of the values is -2 then a value that maintains the aspect ratio of the input image, calculated from the other specified dimension, will be used. If both of them are -2 (or -1), the input size is used.

## Anki Card Example (Front & Back)

<img src="http://i.imgur.com/iJibGML.png" width="775" height="396">

This card template I use on my phone. To use it on desktop it may be helpful to install addon ["Replay buttons on card"](https://ankiweb.net/shared/info/498789867) or better use [updated version](https://gist.github.com/kelciour/ce22e4d5908090f51dce537ccce35a5c). Because in the original add-on after clicking on the audio button media file will be added in queue and may not be played immediately.

## Usage

1. Install Anki (http://ankisrs.net/)

2. Download movies2anki and install dependencies (for Linux and MacOS)

3. Import movies2anki card template into Anki

  Open Anki, go to the menu File, select Import, open movies2anki-sample.apkg

4. Use movies2anki to generate cards

5. Import cards into Anki
  * Open Anki
  * Menu File, Import, open generated "deck_name.tsv" file
  * In the Import Dialog select:
    * Type - "movies2anki"
    * Deck
    * "Fields separated by: Tab"
    * Import even if existing note has same first field
    * Allow HTML in fields
  * Click "Import"
6. Copy all files from "deck_name.media" folder into [collection.media](http://ankisrs.net/docs/manual.html#files) folder.

  #### Video

  https://www.youtube.com/watch?v=Uu9oT5z08Is

### Batch Processing

1. Video name contains ```*``` or ```?``` symbols.
  
   ```*``` = Match zero or more characters  
   ```?``` = Match exactly zero or one character

2. Deck's name contains a pattern ```{##/start_number}```, for example "Avatar. The Last Airbender s01e{##/1}".

## Download

* Windows - https://github.com/kelciour/movies2anki/releases
* Linux and MacOS - [movies2anki-master.zip](https://github.com/kelciour/movies2anki/archive/master.zip)

> For Linux & MacOS users: Python 2.7, FFmpeg, Qt and PyQt4 installed is required to run movies2anki.

#### Instructions for Ubuntu 14.04

* Installing Python 2.7

    Nothing to do. Python 2.7 is already installed.

* Installing FFmpeg

    ```shell
    sudo add-apt-repository ppa:mc3man/trusty-media
    sudo apt-get update
    sudo apt-get install ffmpeg
    ```

* Installing Qt & PyQt4

    Nothing to do. Qt & PyQt4 is already installed.

* Open Terminal and run this command inside the movies2anki folder

    ```shell
    python movies2anki.py
    ```

#### Instructions for MacOS

1. Install [Homebrew](http://brew.sh/)
2. Install FFmpeg

    ```shell
    brew install ffmpeg
    ```
3. Install Qt & PyQt4

    ```shell
    brew install pyqt
    ```
4. Install Python 2.7

    ```shell
    brew install python
    ```
5. Run movies2anki

    ```shell
    python movies2anki.py
    ```

## Troubleshooting

Close movies2anki and look at "log.txt" in the movies2anki folder. (Note: "log.txt" contains information only from previous movies2anki run)

## Sync between mobile devices and your computer

1. Use AnkiWeb to sync decks (text information)
2. Don't use AnkiWeb to sync media
  - Disable option "Fetch media on sync" both on mobile and computer version of Anki
  - Manually sync media via USB or SSH (I use WinSCP for Windows 7 and SSHDroid for Android)

## Additional Options

File config.ini contains:
* is_write_output_subtitles - write subtitles with phrases that have been used to split video into clips next to the input video file. (default - False)
* is_ignore_sdh_subtitle - ignore SDH subtitles. All lines that has been ignored will be in 'log.txt'. (default - True)
* is_add_dir_to_media_path - add "deck_name.media/" to media path in Audio and Video fields. (default - False)
  - If this option is True then you will need to copy "deck_name.media" folder itself into collection.media
  - But "Check Media..." option in Anki won't working with this cards 
* is_write_output_subtitles_for_clips - write English subtitles next to the generated clips. (default - False)
* is_create_clips_with_softsub - embed English subtitles (softsubs) into the generated clips. (default - False)
  - On Windows you need to copy "Arial" font from "C:\Windows\Fonts" in "C:\Program Files\Anki\mplayer". Delete all "*.ttf" files except "arial.ttf" (if there is more than one). Rename "arial.ttf" in "subfont.ttf".
  - If subtitles looks blurry edit mplayer 'config' file inside that folder and replace line "vo=direct3d" with "vo=gl". (Note: you need to open notepad.exe with admin rigths (see [usage video](https://youtu.be/Uu9oT5z08Is?t=87)) or copy "config" file into your desktop, edit it and copy it back)
* is_create_clips_with_hardsub - burn English subtitles (hardsubs) into the generated clips. (default - False)
* hardsub_style - override default style of the hardsubs subtitles. It accepts a string containing ASS style format KEY=VALUE couples separated by ",". For more information see Section 5 in the ["ass-specs"](http://moodub.free.fr/video/ass-specs.doc) file. (default - FontName=Arial,FontSize=24,OutlineColour=&H5A000000,BorderStyle=3).
* is_separate_fragments_without_subtitles - split apart fragments between phrases in Movie mode instead of changing ending time of phrases. (default - False)

If there is no "config.ini" file then just open and close movies2anki. File "config.ini" will appear with default settings.

## Notes

* Audio on the back side will be played automatically with 250 ms delay ([reddit post](https://www.reddit.com/r/Anki/comments/5dygor/delayed_automatic_playback_of_audio/)). It is useful on AnkiDroid. If you don't need it you need to edit Back Template and delete ```[sound:_silence-0.25s.mp3]``` and ```<script>``` tag completely.  
Silence audio was generated with ffmpeg command: ```ffmpeg -f lavfi -i anullsrc -c:a mp3 -t 0.25 _silence-0.25s.mp3```.

## Related Projects

Projects similar to [subs2srs](http://subs2srs.sourceforge.net/):

* [SubtitleMemorize](https://github.com/ChangSpivey/SubtitleMemorize)
* [substudy](https://github.com/emk/substudy)