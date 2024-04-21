movies2anki_front_template = """
<div>{{play:Video}}</div>
"""

movies2anki_back_template = """
{{FrontSide}}

<hr id=answer>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}

<div>{{play:Audio}}</div>
"""

base_css = """
.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}

.expression {
 font-size: 20px;
 margin-top: 15px;
 margin-bottom: 9px;
}

.meaning {
 font-size: 18px;
 color: #000080;
 margin-bottom: 10px;
}

.nightMode .meaning {
 color: #9bc0dd;
}

.notes {
 font-size: 18px;
 color: #aaa;
 margin-bottom: 10px;
}

.snapshot {
 margin-bottom: 13px;
}

img {
 display: block;
 margin: auto;
 max-width: 100%;
 height: auto;
}

.media {
 margin: 4px;
 margin-top: 12px;
}

hr#answer {
 margin-top: 10px;
 margin-bottom: 16px;
 height: 1px;
 background-color: #9a9a9a;
 border: none;
}

.replay-button {
 height: 35px;
 width: 35px;
 outline: none;
 user-select: none;
 -webkit-tap-highlight-color: transparent;
 content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' class='playImage' viewBox='0 0 64 64' width='40px' height='40px' version='1.1'%3E%3Ccircle fill='%23fff' stroke='%23414141' cx='32' cy='32' r='29'%3E%3C/circle%3E%3Cpath fill='%23414141' d='M56.502,32.301l-37.502,20.101l0.329,-40.804l37.173,20.703Z'%3E%3C/path%3E%3C/svg%3E");
}

.nightMode .replay-button {
 filter: invert(85%);
}
"""

movies2anki_css = base_css + """
"""

#  ------------------------------------- #

subs2srs_front_template = """
<div class="snapshot">{{Snapshot}}</div>

<div class="media">{{play:Audio}}</div>
"""

subs2srs_back_template = """
<div class="snapshot">{{Snapshot}}</div>

<div class="media">{{play:Audio}}</div>

<hr id=answer>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}
"""

subs2srs_css = base_css + """
"""

#  ------------------------------------- #

subs2srs_video_front_template = """
<video poster="{{Id}}.jpg" autoplay playsinline onclick="playVideo(); return false;" controlsList="nodownload" disablepictureinpicture disableRemotePlayback>
  <source src="{{Id}}.mp4" type="video/mp4">
  <source src="{{Id}}.webm" type="video/webm">
</video>

<script>
var video = document.querySelector('video');
video.addEventListener('error', () => {
  if (typeof pycmd !== 'undefined') {
    pycmd("ankiplay{{Id}}.mp4");
  }  
});

function playVideo() {
  video.currentTime = 0;
  video.play();
}

if (!globalThis.jsReplayButtonHandler) {
  document.addEventListener("keyup", (event) => {
      if (event.code === "KeyR") {
        playVideo();
      }
  });
  globalThis.jsReplayButtonHandler = true;
}
</script>
"""

subs2srs_video_back_template = """
{{FrontSide}}

<hr class="hidden">

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}

<div class="media">{{play:Audio}}</div>
"""

subs2srs_video_css = base_css + """
body {
 height: 100vh;
 padding: 20px;
 margin: 0;
 box-sizing: border-box;
}

video {
 display: block;
 max-width: 100%;
 margin: auto;
}

.hidden {
 visibility: hidden;
 margin: 0;
}

.mobile body, .mobile #content {
 margin: 0;
 padding: 0;
}

.mobile #content .back {
 margin: 10px;
 margin-top: 5px;
}
"""

#  ------------------------------------- #

subs2srs_audio_front_template = """
<div class="media">{{play:Audio}}</div>
"""

subs2srs_audio_back_template = """
<div class="media">{{play:Audio}}</div>

<hr>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}
"""

subs2srs_audio_css = base_css + """
"""