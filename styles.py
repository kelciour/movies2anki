movies2anki_front_template = """
<div>{{play:Video}}</div>

<script>
if (document.documentElement.classList.contains("android")) {
  document.querySelectorAll("video").forEach(video => {
    let a = document.createElement("a");
    a.classList.add("replay-button");
    a.setAttribute("href", "#");
    a.onclick = function() {
      video.currentTime = 0;
      video.play();
    }
    video.insertAdjacentElement("afterend", a);

    video.addEventListener("playing", (event) => {
      document.body.style.opacity = 0;
      video.style.visibility = "visible";
      document.body.classList.add("darkify");
      video.requestFullscreen();
    });

    video.addEventListener("ended", (event) => {
      document.body.classList.remove("darkify");
      video.style.visibility = "hidden";
      document.exitFullscreen();
    });

    video.addEventListener("fullscreenchange", (event) => {
      if (!document.fullscreenElement) {
        document.body.classList.remove("darkify");
        document.body.style.opacity = 1;
      }
    });
  });

  onUpdateHook.push(function () {
    let video = document.querySelector("video");
    if (video && !document.querySelector("#answer")) {
      video.addEventListener("loadstart", (event) => {
        video.play();
      });
      video.load();
    }
  })
}
</script>
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
.android #qa {
 margin-top: 14px;
}

.android video {
 display: block;
 margin: 10px 0;
}

.android video::-webkit-media-controls {
 display: none !important;
}

.android video {
 position: absolute;
 top: -1000px;
}

.darkify {
 background: black;
}
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
<video poster="{{text:Id}}.jpg" autoplay playsinline onclick="playVideo(); return false;" controlsList="nodownload" disablepictureinpicture disableRemotePlayback>
  <source src="{{text:Id}}.webm" type="video/webm">
  <source src="{{text:Id}}.mp4" type="video/mp4">
</video>

<script>
var isVideoError = false;
var isAutoPlay = true;

var video = document.querySelector('video');
video.addEventListener('error', () => {
  isVideoError = true;
  if (isAutoPlay) {
    isAutoPlay = false;
    playVideo();
  }
}, true);

function playVideo() {
  if (isVideoError && typeof pycmd !== 'undefined') {
    return pycmd("ankiplay{{text:Id}}.mp4");
  } else {
    video.currentTime = 0;
    video.play();
  }
}

var isTextSelected = false;

function tapAction(event) {
  if (isTextSelected) return;
  if (!window.getSelection().isCollapsed) return;
  if (event.target.tagName == 'A') return;
  playVideo();
}

if (!document.body.hasAttribute('js-tap-on-screen-handler')) {
  document.body.setAttribute('js-tap-on-screen-handler', '');
  document.addEventListener('click', tapAction);
  document.addEventListener('mousedown', (event) => {
    isTextSelected = !window.getSelection().isCollapsed;
  });
}

function replaySound(event) {
  if (event.key != 'r') return;
  playVideo();
}

if (!document.body.hasAttribute('js-replay-button-handler')) {
  document.body.setAttribute('js-replay-button-handler', '');
  document.addEventListener('keyup', replaySound);
}
</script>
"""

subs2srs_video_back_template = """
<video poster="{{text:Id}}.jpg" playsinline onclick="playVideo(); return false;" controlsList="nodownload" disablepictureinpicture disableRemotePlayback>
  <source src="{{text:Id}}.webm" type="video/webm">
  <source src="{{text:Id}}.mp4" type="video/mp4">
</video>

<div class="back">

  <hr class="hidden">

  <div class="expression">{{Expression}}</div>

  {{#Meaning}}
  <div class="meaning">{{Meaning}}</div>
  {{/Meaning}}

  {{#Notes}}
  <div class="notes">{{Notes}}</div>
  {{/Notes}}

  <div class="media">{{play:Audio}}</div>

</div>

<script>
var isVideoError = false;

var video = document.querySelector('video');
video.addEventListener('error', () => {
  isVideoError = true;
}, true);

function playVideo() {
  if (isVideoError && typeof pycmd !== 'undefined') {
    return pycmd("ankiplay{{text:Id}}.mp4");
  } else {
    video.currentTime = 0;
    video.play();
  }
}

var isTextSelected = false;

function tapAction(event) {
  if (isTextSelected) return;
  if (!window.getSelection().isCollapsed) return;
  if (event.target.tagName == 'A') return;
  playVideo();
}

if (!document.body.hasAttribute('js-tap-on-screen-handler')) {
  document.body.setAttribute('js-tap-on-screen-handler', '');
  document.addEventListener('click', tapAction);
  document.addEventListener('mousedown', (event) => {
    isTextSelected = !window.getSelection().isCollapsed;
  });
}

function replaySound(event) {
  if (event.key != 'r') return;
  playVideo();
}

if (!document.body.hasAttribute('js-replay-button-handler')) {
  document.body.setAttribute('js-replay-button-handler', '');
  document.addEventListener('keyup', replaySound);
}
</script>
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
 margin-top: 0;
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