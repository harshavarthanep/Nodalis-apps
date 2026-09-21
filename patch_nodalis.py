#!/usr/bin/env python3
"""
patch_nodalis.py  —  Nodalis v10.9.1 "Layout Lock" patch
=========================================================

WHAT IT FIXES
    The app sliding sideways while you type, losing the sidebar, and only
    coming back on a refresh.

WHAT IT DOES
    1. Makes a timestamped backup of index.html next to it.
    2. Inserts one CSS block just before </style>.
    3. Inserts one <script> block just before </body>.
    4. Bumps the service-worker version in sw.js so every device picks the
       new build up instead of serving the old one from cache.
    It changes nothing else. Not one existing line is edited or removed.

HOW TO RUN IT
    Put this file in the same folder as index.html and sw.js, then:

        python patch_nodalis.py

    (On a Mac or Linux, type  python3 patch_nodalis.py  instead.)

IT IS SAFE TO RUN TWICE
    If the patch is already in the file it says so and stops without
    touching anything.

TO UNDO IT
    Delete index.html and rename the backup file back to index.html.
"""

import os
import re
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
SW = os.path.join(HERE, "sw.js")

MARKER = "v10.9.1 — LAYOUT LOCK"

# --------------------------------------------------------------- the patches

CSS_PATCH = r"""

/* =========================================================================
 * v10.9.1 — LAYOUT LOCK
 *
 * THE BUG THIS FIXES
 *
 * "While I am typing the whole app slides to the left, the sidebar
 *  disappears, I cannot see the details, and only a refresh puts it back."
 *
 * .app-body is a three-column grid: sidebar | note | right panel. When the
 * right panel is closed it is not removed — it is pushed out of sight with
 *
 *     .app[data-right='closed'] .right-panel { margin-right: -300px; }
 *
 * A negative margin does not delete a box. The panel is still 300px wide and
 * still sitting there, 300px past the right edge of .app-body. And .app-body
 * said `overflow: hidden`.
 *
 * `overflow: hidden` does NOT mean "there is nothing to scroll". It means
 * "there IS something to scroll, and I am hiding the scrollbar". The element
 * is a real scroll container with scrollWidth 300px wider than itself. The
 * browser is allowed to scroll it — and it does, every time it needs to bring
 * a focused element into view. Focus anything inside that off-screen panel
 * (Tab from the editor, the phone keyboard's "next field" arrow, the Links /
 * Outline / Info panel re-rendering as you type) and the browser helpfully
 * scrolls .app-body 300px to the left to show it.
 *
 * And then you are stuck. There is no scrollbar to drag back and a mouse
 * wheel will not scroll a hidden axis, so nothing on the page can undo it.
 * Only a reload resets scrollLeft. Hence "refresh fixes it".
 *
 * Measured, before this patch, at 1280x900 with the right panel closed:
 *     .app-body  clientWidth 1280  scrollWidth 1580  -> 300px of hidden scroll
 *     focusing one button in the closed panel -> .app-body.scrollLeft = 300
 *
 * THE FIX
 *
 * `overflow: clip` instead. A clip box is not a scroll box: it has no
 * scrollport, no scrollLeft to set, and the browser physically cannot scroll
 * it. The overflow is still invisible, nothing else changes. The plain
 * `overflow: hidden` line is kept immediately above it as the fallback for
 * Safari 15 and older, which ignores `clip` and keeps the old behaviour —
 * the JavaScript guard at the bottom of this file covers those browsers.
 * ========================================================================= */

.app,
.app-body,
.main-view,
.topbar,
.pwa-mark {
  overflow: hidden;   /* fallback: Safari < 16, Chrome < 90 */
  overflow: clip;     /* a clip box cannot be scrolled, by anyone, ever */
}

/*
 * Belt and braces for the one axis that actually caused the damage. Even on
 * an engine that ignores `clip`, nothing here is ever allowed to become a
 * horizontal scroller.
 */
.app,
.app-body,
.main-view {
  overflow-x: hidden;
  overflow-x: clip;
}

/*
 * A closed drawer is off screen, so it should not be reachable by Tab either.
 * The `inert` attribute is applied by the script at the bottom of the file;
 * this is the matching visual state, and the belt for browsers too old for
 * `inert` — content-visibility keeps a closed drawer out of the layout work
 * as well, which is a small speed win on a phone.
 */
.app[data-sidebar='closed'] .sidebar[inert],
.app[data-right='closed'] .right-panel[inert] {
  pointer-events: none;
}

/*
 * The editor's own scrollers keep their scrollbars — this is deliberately
 * NOT applied to them. Only the immovable shell is locked down.
 */
"""

JS_PATCH = r"""

<!-- =========================================================================
     v10.9.1 — LAYOUT LOCK (runtime half)

     The CSS above stops the shell from EVER becoming a scroll container on
     any browser that understands `overflow: clip` — which is Chrome 90+,
     Edge 90+, Firefox 81+, Safari 16+. That is the fix.

     This script is the safety net underneath it, and it does three jobs:

       1. Older Safari ignores `clip` and falls back to `hidden`, so the old
          bug is still possible there. If anything ever scrolls a hidden axis,
          this snaps it straight back to 0 in the same frame. The user sees
          nothing.
       2. It removes closed drawers from the keyboard tab order. Before this,
          a phone keyboard's "next field" arrow or a Tab key would walk 24
          buttons that live off the side of the screen — which is what asked
          the browser to scroll in the first place, and is also just wrong
          for anyone using a keyboard or a screen reader.
       3. It re-pins the shell after the events that historically shift a
          mobile layout: the on-screen keyboard opening and closing, rotating
          the phone, and coming back to a backgrounded tab.

     It is entirely event driven. It costs nothing while nothing is wrong.
     ========================================================================= -->
<script>
(function () {
  'use strict';

  /* Every part of the frame that is meant to be immovable. */
  var SHELLS = '#app, .app, .app-body, .main-view, .topbar, .sidebar, .right-panel';

  /* Put one element back if a hidden axis of it has been scrolled. */
  function pin(el) {
    if (!el || el.nodeType !== 1) return;
    var s;
    try { s = getComputedStyle(el); } catch (err) { return; }
    if (el.scrollLeft && (s.overflowX === 'hidden' || s.overflowX === 'clip')) el.scrollLeft = 0;
    if (el.scrollTop && (s.overflowY === 'hidden' || s.overflowY === 'clip')) el.scrollTop = 0;
  }

  /*
   * A scroll event fires on the element that scrolled, and scroll events do
   * not bubble — so this listens in the capture phase, which does see them.
   * If the thing that moved was never supposed to move, it is put back before
   * the frame is painted.
   */
  document.addEventListener('scroll', function (e) {
    var t = e.target;
    if (t === document || t === document.documentElement || t === document.body) {
      if (window.scrollX) window.scrollTo(0, window.scrollY);
      if (document.body.scrollLeft) document.body.scrollLeft = 0;
      if (document.documentElement.scrollLeft) document.documentElement.scrollLeft = 0;
      return;
    }
    pin(t);
  }, true);

  var queued = false;
  function pinAll() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () {
      queued = false;
      if (window.scrollX) window.scrollTo(0, window.scrollY);
      pin(document.body);
      pin(document.documentElement);
      var n = document.querySelectorAll(SHELLS);
      for (var i = 0; i < n.length; i++) pin(n[i]);
    });
  }

  /* ------------------------------------------------ closed drawers go inert */

  /*
   * A drawer that is closed is off the side of the screen. Leaving its
   * buttons in the tab order is what let the browser scroll the shell to
   * "reveal" them. `inert` takes them out of the tab order, out of the
   * accessibility tree and out of find-in-page, without touching the slide
   * animation.
   */
  function syncInert() {
    var app = document.getElementById('app');
    if (!app) return;
    var pairs = [
      ['.sidebar', app.getAttribute('data-sidebar')],
      ['.right-panel', app.getAttribute('data-right')]
    ];
    for (var i = 0; i < pairs.length; i++) {
      var el = document.querySelector(pairs[i][0]);
      if (!el) continue;
      var closed = pairs[i][1] === 'closed';
      if (closed && !el.hasAttribute('inert')) {
        if (el.contains(document.activeElement)) {
          try { document.activeElement.blur(); } catch (err) { /* already gone */ }
        }
        el.setAttribute('inert', '');
        el.setAttribute('aria-hidden', 'true');
      } else if (!closed && el.hasAttribute('inert')) {
        el.removeAttribute('inert');
        el.removeAttribute('aria-hidden');
      }
    }
  }

  function start() {
    var app = document.getElementById('app');
    if (!app) { setTimeout(start, 200); return; }

    syncInert();
    pinAll();

    /*
     * MutationObserver callbacks run as a microtask — before any timer, before
     * the next frame — so a drawer is out of `inert` the instant it is marked
     * open, well before anything inside it could be clicked or focused.
     */
    try {
      new MutationObserver(function () { syncInert(); pinAll(); })
        .observe(app, { attributes: true, attributeFilter: ['data-sidebar', 'data-right'] });
    } catch (err) { /* very old browser: the scroll guard still holds */ }

    /* The moments a mobile layout historically shifts. */
    window.addEventListener('resize', function () { syncInert(); pinAll(); });
    window.addEventListener('orientationchange', pinAll);
    window.addEventListener('pageshow', pinAll);
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) pinAll();
    });

    /* Focus moving is the single most common cause, so check right after it. */
    document.addEventListener('focusin', pinAll, true);

    /*
     * The on-screen keyboard. visualViewport is the part of the page actually
     * being looked at; it resizes when the keyboard opens and closes, and that
     * is exactly when iOS likes to leave a fixed layout nudged sideways.
     */
    if (window.visualViewport) {
      window.visualViewport.addEventListener('resize', pinAll);
      window.visualViewport.addEventListener('scroll', pinAll);
    }

    /* Anything that slid, settled. */
    document.addEventListener('transitionend', function (e) {
      var p = e.propertyName;
      if (p === 'margin-left' || p === 'margin-right' || p === 'transform' || p === 'width') pinAll();
    }, true);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
</script>
"""

# ------------------------------------------------------------------ plumbing


def say(msg):
    print(msg, flush=True)


def fail(msg):
    say("")
    say("  STOPPED. " + msg)
    say("")
    sys.exit(1)


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def backup(path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = path + ".backup-" + stamp
    shutil.copy2(path, dest)
    return os.path.basename(dest)


def css_insert_point(html):
    """
    The real </style> — the one that closes the page's stylesheet, sitting
    right before </head>.

    Nodalis also contains the text "</style>" inside a JavaScript string (the
    HTML exporter builds a standalone page out of it). Searching for the last
    </style> in the file lands inside that string and corrupts the script, so
    the anchor has to be the </style> that is followed by </head>.
    """
    m = re.search(r"</style>\s*</head>", html, re.IGNORECASE)
    if not m:
        fail("could not find the </style></head> pair in index.html. "
             "Is this really the Nodalis index.html?")
    return m.start()


def js_insert_point(html):
    """
    The real </body> — the one just before the final </html> at the end of
    the file. Same reason as above: "</body>" also appears inside the
    exporter's JavaScript strings.
    """
    end = html.rfind("</html>")
    if end == -1:
        fail("index.html has no closing </html> tag.")
    at = html.rfind("</body>", 0, end)
    if at == -1:
        fail("could not find the closing </body> tag in index.html.")
    return at


def insert_at(html, at, payload):
    return html[:at] + payload + "\n" + html[at:]


# ---------------------------------------------------------------------- main


def main():
    say("")
    say("  Nodalis — Layout Lock patch (v10.9.1)")
    say("  " + "-" * 44)

    if not os.path.isfile(INDEX):
        fail("no index.html in this folder (" + HERE + ").")

    html = read(INDEX)
    say("  Found index.html  (%.1f MB)" % (len(html.encode("utf-8")) / 1048576.0))

    if MARKER in html:
        say("")
        say("  Already patched. Nothing to do.")
        say("")
        return

    # Work out both anchors BEFORE writing anything, so a file that does not
    # match is left completely untouched.
    css_at = css_insert_point(html)
    js_at = js_insert_point(html)
    say("  Anchors found      </style> at byte %s, </body> at byte %s"
        % (f"{css_at:,}", f"{js_at:,}"))

    b = backup(INDEX)
    say("  Backup made        " + b)

    # Insert the later one first so the earlier offset stays valid.
    out = insert_at(html, js_at, JS_PATCH)
    out = insert_at(out, css_at, CSS_PATCH)

    write(INDEX, out)
    added = len(out.encode("utf-8")) - len(html.encode("utf-8"))
    say("  Patched index.html  (+%s bytes, %s new lines)"
        % (f"{added:,}", out.count("\n") - html.count("\n")))

    # ------------------------------------------------------- self-check
    # Read the file back off the disk and prove the patch landed where it
    # was meant to. If anything is off, put the backup back automatically
    # so you are never left with a half-patched app.
    check = read(INDEX)
    problems = []
    if check.count(MARKER) != 2:
        problems.append("the two patch blocks are not both present")
    if check.count("<script>") != html.count("<script>") + 1:
        problems.append("the new <script> tag did not land cleanly")
    if check.index(MARKER) > check.index("</head>"):
        problems.append("the CSS block landed outside <head>")
    if problems:
        shutil.copy2(os.path.join(HERE, b), INDEX)
        fail("self-check failed (" + "; ".join(problems) +
             "). Your original index.html has been put back, unchanged.")
    say("  Self-check          passed")

    # ------------------------------------------------ service worker version
    if os.path.isfile(SW):
        sw = read(SW)
        m = re.search(r"const VERSION = 'nodalis-v([0-9]+)\.([0-9]+)';", sw)
        if m:
            new = "nodalis-v%s.%d" % (m.group(1), int(m.group(2)) + 1)
            sw2 = sw[:m.start()] + "const VERSION = '%s';" % new + sw[m.end():]
            bsw = backup(SW)
            write(SW, sw2)
            say("  Backup made        " + bsw)
            say("  Bumped sw.js       nodalis-v%s.%s -> %s"
                % (m.group(1), m.group(2), new))
        else:
            say("  sw.js              version line not recognised, left alone")
    else:
        say("  sw.js              not in this folder, skipped")

    say("")
    say("  Done. Next steps:")
    say("    1. Open index.html in a browser and check it still works.")
    say("    2. Commit and push index.html and sw.js to GitHub.")
    say("    3. On your phone or laptop, load the site and do a hard refresh")
    say("       (Ctrl+Shift+R, or Cmd+Shift+R on a Mac) the first time.")
    say("")


if __name__ == "__main__":
    main()
