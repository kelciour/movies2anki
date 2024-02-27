front_template = """
<div>[sound:{{Video}}]</div>
"""

back_template = """
{{FrontSide}}

<hr id=answer>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}

<div>[sound:{{Audio}}]</div>
"""

css = """
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
 margin-bottom: 10px;
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
 margin-bottom: 3px;
}

img {
 display: block;
 margin: auto;
 max-width: 100%;
 height: auto;
}

.media {
 margin: 4px;
}

hr#answer {
 margin-top: 10px;
 margin-bottom: 16px;
 height: 1px;
 background-color: #9a9a9a;
 border: none;
}

.replay-button {
 height: 40px;
 width: 40px;
 outline: none;
 user-select: none;
 content: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' class='playImage' viewBox='0 0 64 64' width='40px' height='40px' version='1.1'%3E%3Ccircle fill='%23fff' stroke='%23414141' cx='32' cy='32' r='29'%3E%3C/circle%3E%3Cpath fill='%23414141' d='M56.502,32.301l-37.502,20.101l0.329,-40.804l37.173,20.703Z'%3E%3C/path%3E%3C/svg%3E");
}

.nightMode .replay-button {
 filter: invert(85%);
}
"""

#  ------------------------------------- #

subs2srs_front_template = """
<div class="snapshot">{{Snapshot}}</div>

<div class="media">[sound:{{Audio}}]</div>
"""

subs2srs_back_template = """
<div class="snapshot">{{Snapshot}}</div>

<div class="media">[sound:{{Audio}}]</div>

<hr id=answer>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}
"""

subs2srs_css = css + """
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
    return pycmd("ankiplay{{Video}}");
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

  <hr id="answer">

  <div class="expression">{{Expression}}</div>

  {{#Meaning}}
  <div class="meaning">{{Meaning}}</div>
  {{/Meaning}}

  {{#Notes}}
  <div class="notes">{{Notes}}</div>
  {{/Notes}}

  <div class="media">[sound:{{Audio}}]</div>

</div>

<script>
var isVideoError = false;

var video = document.querySelector('video');
video.addEventListener('error', () => {
  isVideoError = true;
}, true);

function playVideo() {
  if (isVideoError && typeof pycmd !== 'undefined') {
    return pycmd("ankiplay{{Video}}");
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

subs2srs_video_css = css + """
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

hr#answer {
 visibility: hidden;
 margin-top: 0;
}

.mobile body, .mobile #content {
 margin: 0;
}

.mobile #content .back {
 margin: 20px;
}
"""

#  ------------------------------------- #

subs2srs_audio_front_template = """
<div class="media">[sound:{{Audio}}]</div>
"""

subs2srs_audio_back_template = """
<div class="media">[sound:{{Audio}}]</div>

<hr>

<div class="expression">{{Expression}}</div>

{{#Meaning}}
<div class="meaning">{{Meaning}}</div>
{{/Meaning}}

{{#Notes}}
<div class="notes">{{Notes}}</div>
{{/Notes}}
"""

subs2srs_audio_css = css + """
"""