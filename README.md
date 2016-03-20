#  movies2anki

Convert movies with subtitles to watch them with [Anki](http://ankisrs.net). The movie will be splitted into separate scenes/phrases. I found it useful for improving my listening skills.

Inspired by [subs2srs](http://subs2srs.sourceforge.net/).

## Interface

<img src="https://dl.dropboxusercontent.com/u/58886000/GitHub/movies2anki.png" width="775" height="499">

* Second subtitle is optional
* Movie mode:
  * Change end times of phrases to the next phrase's start time
  * Add empty phrase if the first subtitle starts after 15 seconds

## Anki Card Example (Front & Back)

<img src="https://dl.dropboxusercontent.com/u/58886000/GitHub/front-back-hints.png" width="775" height="396">

This card template I use on my phone. To use on desktop it may be helpful to install addon ["Replay buttons on card"](https://ankiweb.net/shared/info/498789867).

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

#### Troubleshooting

Close movies2anki and look at "log.txt" in the movies2anki folder.

#### Sync between mobile devices and your computer

1. Use AnkiWeb to sync decks
2. Don't use AnkiWeb to sync media
  - Disable option "Fetch media on sync" both on mobile and computer version of Anki
  - Manually sync media via SSH (I use WinSCP for Windows 7 and SSHDroid for Android)

#### Additional Options

File config.ini contains:
* is_write_output_subtitles - write subtitles with phrases next to the video (default - False)
* is_ignore_sdh_subtitle - ignore SDH subtitles (default - True)
* is_add_dir_to_media_path - add "deck_name.media/" to media path in Audio and Video fields (default - False)
  - If this option is True then you will need to copy "deck_name.media" folder itself into collection.media
  - But "Check Media..." option in Anki won't working with this cards
