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

> For Linux & MacOS users: Python 2.7, FFmpeg, Qt and PySide installed is required to run movies2anki.

#### Instructions for Ubuntu 14.04

* Installing Python 2.7

Nothing to do. Python 2.7 is already installed.

* Installing FFmpeg

```shell
sudo add-apt-repository ppa:mc3man/trusty-media
sudo apt-get update
sudo apt-get install ffmpeg
```

* Installing Qt & PySide

```shell
sudo apt-get install build-essential git cmake libqt4-dev libphonon-dev python2.7-dev libxml2-dev libxslt1-dev qtmobility-dev libqtwebkit-dev python-pip
sudo pip install pyside
```

* Open Terminal and run this command inside the movies2anki folder

```shell
python movies2anki.py
```

#### Troubleshooting

Close movies2anki and look at "log.txt" in the movies2anki folder.

#### Additional Options

File config.ini contains:
* is_write_output_subtitles - write subtitles with phrases next to the video (default - False)
* is_ignore_sdh_subtitle - ignore SDH subtitles (default - True)
