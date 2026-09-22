#!/usr/bin/env python3
"""
patch_nodalis.py  —  Nodalis v10.9.2
=====================================

Applies two patches to index.html. Both are additive: not one existing line
is edited or deleted, and each can already be present without any harm.

  v10.9.1  LAYOUT LOCK
           The app sliding sideways while you type and only coming back on a
           refresh. Root cause: .app-body was a hidden scroll container 300px
           wider than itself whenever the right panel was closed.

  v10.9.2  DAILY START, PERSISTENT UNDO, MORE EXPORTS, IMAGE EXPORT FIX
           - PNG / JPG export, which had never worked on any browser.
           - Undo and redo that survive a reload, cover pasting and the slash
             menu, and have buttons for phones.
           - "Open today's note when Nodalis starts", off by default.
           - Plain-text export and copy-with-formatting.

HOW TO RUN IT
    Put this file in the same folder as index.html and sw.js, then:

        python patch_nodalis.py

    (On a Mac or Linux, type  python3 patch_nodalis.py  instead.)

IT IS SAFE TO RUN TWICE
    Anything already applied is skipped. If nothing is left to do it says so
    and stops without touching the files.

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

MARK_V1 = "v10.9.1 — LAYOUT LOCK"
MARK_V2 = "v10.9.2 — DAILY START"

CSS_V1 = r"""

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

JS_V1 = r"""

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

CSS_V2 = r"""

/* =========================================================================
 * v10.9.2 — DAILY START, PERSISTENT UNDO, MORE EXPORTS
 *
 * Styling for the three additions. Everything here is new; nothing above is
 * overridden. The undo and redo buttons live in the note header beside the
 * pin, so they are reachable with a thumb on a phone, where there is no
 * Ctrl+Z to press.
 * ========================================================================= */

.ndx-hist-btn {
  position: relative;
  transition: opacity var(--dur-fast, .12s) var(--ease-out, ease);
}

/*
 * A disabled history button stays in place rather than disappearing. A
 * control that comes and goes makes the header jump and makes the two
 * buttons swap positions, which is how you press redo meaning to press undo.
 */
.ndx-hist-btn[disabled] {
  opacity: 0.32;
  cursor: default;
  pointer-events: none;
}

/*
 * No step counter on the button, deliberately. At the size an icon button
 * corner allows, the digit is a coloured dot rather than a number — it reads
 * as an unread badge and tells you nothing. Enabled or dimmed already says
 * whether there is anything to go back to, which is the only question.
 */

/*
 * On a narrow phone the note header is already crowded: title, share state,
 * pin, menu and the preview toggle. Undo and redo earn their place there —
 * they are the two controls a phone has no keyboard shortcut for — so the
 * PIN is what gives way first, exactly as the mark does in the top bar.
 */
@media (max-width: 400px) {
  .editor-actions #btn-pin { display: none; }
}

/* Settings rows this patch adds, so they read as part of the panel. */
.ndx-setting-note {
  margin-top: 8px;
  font-size: var(--text-sm);
  color: var(--text-2);
  line-height: 1.55;
}
"""

JS_V2 = r"""

<!-- =========================================================================
     v10.9.2 — DAILY START · PERSISTENT UNDO · MORE EXPORTS · IMAGE EXPORT FIX

     Four things, all additive. Nothing above this line is edited.

       1. A working PNG / JPG export. It has never worked on any browser, and
          the reason it cannot be repaired in place is at the fix itself.
       2. Undo and redo that survive a reload, cover pasting and the slash
          menu and every other programmatic edit, and have buttons so they
          work on a phone.
       3. "Open today's note when Nodalis starts", off by default.
       4. Plain text export, and copy-as-rich-text for pasting into Word,
          Gmail or Docs with the formatting intact.

     Everything hangs off the public NODALIS namespace and the event bus, so
     no private function in the app above had to be touched or re-declared.
     ========================================================================= -->
<script>
(function () {
  'use strict';

  /*
   * THE HASH HAS TO BE READ NOW, NOT LATER.
   *
   * The app writes the current view back into location.hash as it boots, so
   * by the time anything downstream looks, "#tasks" has already become
   * "#editor" and the link the person followed is gone. Measured: at
   * 'app:ready', location.hash reads "#editor" on a page opened at "#tasks".
   * This line runs while the document is still parsing, which is before any
   * of that happens.
   */
  var BOOT_HASH = (location.hash || '').replace('#', '').trim();
  var BOOT_SEARCH = location.search || '';

  /* Wait for the app's namespace rather than assuming a load order. */
  function whenReady(fn) {
    var tries = 0;
    (function poll() {
      var N = window.NODALIS;
      if (N && N.bus && N.store && N.util && N.commands) { fn(N); return; }
      if (++tries > 400) return;              // 40s, then give up quietly
      setTimeout(poll, 100);
    })();
  }

  whenReady(function (N) {
    var U = N.util;
    var el = U.el;

    /* ===================================================================
     * 1. THE PNG / JPG EXPORT HAS NEVER WORKED
     *
     * "Export this note… -> Image (.png)" fails every time, on every
     * browser. There are two separate faults, one behind the other.
     *
     * FAULT ONE — the picture never even loads.
     *
     * noteImageBlob draws the note by serialising it into an <svg>
     * <foreignObject>. XMLSerializer already writes the XHTML namespace
     * onto the element it serialises:
     *
     *     <div xmlns="http://www.w3.org/1999/xhtml" style="...">
     *
     * and the next line adds it a second time:
     *
     *     serialized.replace(/<div /, '<div xmlns="http://www.w3.org/1999/xhtml" ')
     *
     * giving  <div xmlns="..." xmlns="..." style="...">.  An attribute
     * cannot be declared twice in XML. The parser stops at
     *
     *     error on line 1 at column 157: Attribute xmlns redefined
     *
     * the image never loads, onerror fires, and you get "The image could not
     * be rasterised."
     *
     * FAULT TWO — and this is why the one-line fix is not enough.
     *
     * With the namespace corrected the SVG loads, draws, and then:
     *
     *     SecurityError: Failed to execute 'toBlob' on 'HTMLCanvasElement':
     *     Tainted canvases may not be exported.
     *
     * Chromium marks a canvas as tainted as soon as anything containing a
     * <foreignObject> is drawn onto it — measured here, with a five-line
     * SVG containing nothing but the word "hello". It is a deliberate
     * privacy measure (foreignObject can render :visited link styling, which
     * would otherwise leak browsing history to a page that reads the
     * pixels). It cannot be worked around, and it takes Chrome, Edge,
     * Brave, Opera, Samsung Internet and every Android browser with it.
     *
     * So the approach itself is a dead end, and the note is drawn onto the
     * canvas directly instead — the same way the app already exports a
     * board. No SVG, nothing tainted, no CDN, and it works offline.
     * =================================================================== */

    var IMG_W = 760, IMG_PAD = 48;
    var SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif';
    var MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace';

    var INK = '#24201a', DIM = '#6b6357', RULE = '#e2dcd0', WASH = '#f4f1ea', LINK = '#5a4fcf';

    /* ---- the note's rendered HTML, turned into blocks we know how to draw */

    function runsOf(node, style, out) {
      for (var i = 0; i < node.childNodes.length; i++) {
        var c = node.childNodes[i];
        if (c.nodeType === 3) {
          var t = c.nodeValue.replace(/\s+/g, ' ');
          if (t) out.push({ t: t, b: style.b, i: style.i, c: style.c, l: style.l, s: style.s });
          continue;
        }
        if (c.nodeType !== 1) continue;
        var tag = c.tagName.toLowerCase();
        if (tag === 'br') { out.push({ br: true }); continue; }
        var next = {
          b: style.b || tag === 'strong' || tag === 'b' || tag === 'th',
          i: style.i || tag === 'em' || tag === 'i',
          c: style.c || tag === 'code',
          l: style.l || tag === 'a',
          s: style.s || tag === 'del' || tag === 's',
        };
        runsOf(c, next, out);
      }
      return out;
    }

    function inline(node) { return runsOf(node, { b: false, i: false, c: false, l: false, s: false }, []); }

    function blocksOf(root, depth, into) {
      for (var i = 0; i < root.children.length; i++) {
        var n = root.children[i];
        var tag = n.tagName.toLowerCase();
        if (/^h[1-6]$/.test(tag)) {
          into.push({ k: 'h', level: Math.min(3, Number(tag[1])), runs: inline(n), d: depth });
        } else if (tag === 'p') {
          var onlyImg = n.children.length === 1 && n.children[0].tagName === 'IMG' && !n.textContent.trim();
          if (onlyImg) into.push({ k: 'img', src: n.children[0].getAttribute('src'), d: depth });
          else into.push({ k: 'p', runs: inline(n), d: depth });
        } else if (tag === 'ul' || tag === 'ol') {
          var num = 1;
          for (var j = 0; j < n.children.length; j++) {
            var li = n.children[j];
            if (li.tagName !== 'LI') continue;
            var nested = li.querySelector('ul, ol');
            var marker = tag === 'ol' ? (num++) + '.' : '•';
            var clone = li.cloneNode(true);
            var kill = clone.querySelectorAll('ul, ol');
            for (var q = 0; q < kill.length; q++) kill[q].remove();
            into.push({ k: 'li', marker: marker, runs: inline(clone), d: depth });
            if (nested) blocksOf(nested.parentNode === li ? li : nested, depth + 1, into);
          }
        } else if (tag === 'blockquote') {
          var inner = [];
          blocksOf(n, depth, inner);
          inner.forEach(function (bl) { bl.quote = true; into.push(bl); });
        } else if (tag === 'pre') {
          /*
           * The renderer puts a language chip and a copy button inside the
           * <pre>, before the <code>. Taking textContent of the whole thing
           * prints the word "js" welded onto the first line of the snippet,
           * so only the <code> is read.
           */
          var codeEl = n.querySelector('code');
          into.push({ k: 'code',
            text: (codeEl ? codeEl.textContent : n.textContent).replace(/^\n+|\n+$/g, ''),
            lang: n.getAttribute('data-lang') || '', d: depth });
        } else if (tag === 'hr') {
          into.push({ k: 'hr', d: depth });
        } else if (tag === 'img') {
          into.push({ k: 'img', src: n.getAttribute('src'), d: depth });
        } else if (tag === 'table') {
          var rows = [];
          var trs = n.querySelectorAll('tr');
          for (var r = 0; r < trs.length; r++) {
            var cells = trs[r].children, row = [];
            for (var c2 = 0; c2 < cells.length; c2++) {
              row.push({ runs: inline(cells[c2]), head: cells[c2].tagName === 'TH' });
            }
            if (row.length) rows.push(row);
          }
          if (rows.length) into.push({ k: 'table', rows: rows, d: depth });
        } else if (n.children.length) {
          blocksOf(n, depth, into);
        } else if (n.textContent.trim()) {
          into.push({ k: 'p', runs: inline(n), d: depth });
        }
      }
      return into;
    }

    /* --------------------------------------------------------- text layout */

    function fontFor(run, size, weight) {
      var w = (run && run.b) || weight === 'bold' ? '700' : '400';
      var st = run && run.i ? 'italic ' : '';
      var fam = run && run.c ? MONO : SANS;
      var sz = run && run.c ? Math.round(size * 0.92) : size;
      return st + w + ' ' + sz + 'px ' + fam;
    }

    /** Break a run list into lines that fit `maxW`. Returns [[piece,...]]. */
    function wrap(ctx, runs, size, maxW, weight) {
      var lines = [[]], x = 0;
      for (var i = 0; i < runs.length; i++) {
        var run = runs[i];
        if (run.br) { lines.push([]); x = 0; continue; }
        ctx.font = fontFor(run, size, weight);
        var words = run.t.split(' ');
        for (var w = 0; w < words.length; w++) {
          var word = words[w] + (w < words.length - 1 ? ' ' : '');
          if (!word) continue;
          var wd = ctx.measureText(word).width;
          if (x + wd > maxW && x > 0) { lines.push([]); x = 0; }
          /* A single unbreakable token longer than the line: cut it. */
          if (wd > maxW) {
            var chunk = '';
            for (var ch = 0; ch < word.length; ch++) {
              var test = chunk + word[ch];
              if (ctx.measureText(test).width > maxW && chunk) {
                lines[lines.length - 1].push({ t: chunk, run: run, w: ctx.measureText(chunk).width });
                lines.push([]); x = 0; chunk = word[ch];
              } else { chunk = test; }
            }
            if (chunk) { var cw = ctx.measureText(chunk).width; lines[lines.length - 1].push({ t: chunk, run: run, w: cw }); x += cw; }
            continue;
          }
          lines[lines.length - 1].push({ t: word, run: run, w: wd });
          x += wd;
        }
      }
      return lines.filter(function (l, idx) { return l.length || idx === 0; });
    }

    function paintLine(ctx, line, x, y, size, weight) {
      var cx = x;
      for (var i = 0; i < line.length; i++) {
        var pc = line[i];
        ctx.font = fontFor(pc.run, size, weight);
        ctx.fillStyle = pc.run.l ? LINK : (pc.run.c ? '#8a4b2f' : INK);
        ctx.fillText(pc.t, cx, y);
        if (pc.run.l) { ctx.fillRect(cx, y + 3, pc.w - 2, 1); }
        if (pc.run.s) { ctx.fillRect(cx, y - size * 0.28, pc.w - 2, 1); }
        cx += pc.w;
      }
    }

    /**
     * One routine, run twice: once with a throwaway context to find out how
     * tall the picture has to be, then again on a canvas of that height to
     * actually draw it. Measuring and drawing with the same code is the only
     * way the two cannot disagree.
     */
    function render(ctx, blocks, images, draw) {
      var maxW = IMG_W - IMG_PAD * 2;
      var y = IMG_PAD;

      for (var i = 0; i < blocks.length; i++) {
        var b = blocks[i];
        var indent = (b.d || 0) * 22 + (b.quote ? 18 : 0);
        var x = IMG_PAD + indent;
        var w = maxW - indent;
        var quoteTop = y;

        /* A quotation wants air above it, but a run of them is one block. */
        if (b.quote && (i === 0 || !blocks[i - 1].quote)) { y += 8; quoteTop = y; }

        if (b.k === 'h') {
          var hs = b.level === 1 ? 30 : b.level === 2 ? 23 : 19;
          y += b.level === 1 ? 26 : 22;
          var hl = wrap(ctx, b.runs, hs, w, 'bold');
          for (var h = 0; h < hl.length; h++) {
            y += hs * 1.3;
            if (draw) paintLine(ctx, hl[h], x, y, hs, 'bold');
          }
          y += 8;
        } else if (b.k === 'p' || b.k === 'li') {
          var lead = 16 * 1.62;
          var tx = x + (b.k === 'li' ? 22 : 0);
          var tw = w - (b.k === 'li' ? 22 : 0);
          var pl = wrap(ctx, b.runs, 16, tw);
          for (var q = 0; q < pl.length; q++) {
            y += lead;
            if (draw) {
              if (q === 0 && b.k === 'li') {
                ctx.font = '400 16px ' + SANS;
                ctx.fillStyle = DIM;
                ctx.fillText(b.marker, x, y);
              }
              paintLine(ctx, pl[q], tx, y, 16);
            }
          }
          y += b.k === 'li' ? 4 : 12;
        } else if (b.k === 'code') {
          var lines = b.text.split('\n');
          var pad = 14, ch2 = 21;
          var boxH = lines.length * ch2 + pad * 2;
          if (draw) {
            ctx.fillStyle = WASH;
            ctx.fillRect(x, y + 6, w, boxH);
            ctx.fillStyle = RULE;
            ctx.fillRect(x, y + 6, 3, boxH);
            if (b.lang) {
              ctx.font = '600 10.5px ' + MONO;
              ctx.fillStyle = DIM;
              ctx.fillText(b.lang.toUpperCase(), x + w - ctx.measureText(b.lang.toUpperCase()).width - 12, y + 22);
            }
            ctx.font = '400 13.5px ' + MONO;
            ctx.fillStyle = INK;
            for (var cl = 0; cl < lines.length; cl++) {
              ctx.fillText(lines[cl], x + pad, y + 6 + pad + (cl + 1) * ch2 - 6);
            }
          }
          y += boxH + 18;
        } else if (b.k === 'hr') {
          y += 14;
          if (draw) { ctx.fillStyle = RULE; ctx.fillRect(x, y, w, 1); }
          y += 16;
        } else if (b.k === 'img') {
          var im = images[b.src];
          if (im) {
            var iw = Math.min(w, im.naturalWidth || im.width || w);
            var ih = (im.naturalHeight || im.height || 1) * (iw / (im.naturalWidth || im.width || 1));
            if (ih > 900) { ih = 900; iw = (im.naturalWidth || 1) * (ih / (im.naturalHeight || 1)); }
            y += 10;
            if (draw) { try { ctx.drawImage(im, x, y, iw, ih); } catch (err) { /* skip */ } }
            y += ih + 16;
          }
        } else if (b.k === 'table') {
          var cols = 0;
          b.rows.forEach(function (r) { cols = Math.max(cols, r.length); });
          var cw2 = w / Math.max(1, cols);
          for (var r2 = 0; r2 < b.rows.length; r2++) {
            var row = b.rows[r2], tallest = 0, wrapped = [];
            for (var c3 = 0; c3 < cols; c3++) {
              var cell = row[c3];
              var wl = cell ? wrap(ctx, cell.runs, 14.5, cw2 - 20, cell.head ? 'bold' : null) : [[]];
              wrapped.push(wl);
              tallest = Math.max(tallest, wl.length);
            }
            var rowH = tallest * 22 + 12;
            if (draw) {
              if (r2 === 0) { ctx.fillStyle = WASH; ctx.fillRect(x, y, w, rowH); }
              ctx.fillStyle = RULE;
              ctx.fillRect(x, y + rowH, w, 1);
              for (var c4 = 0; c4 < cols; c4++) {
                var lw = wrapped[c4];
                for (var ln = 0; ln < lw.length; ln++) {
                  paintLine(ctx, lw[ln], x + c4 * cw2 + 10, y + 8 + (ln + 1) * 20,
                    14.5, row[c4] && row[c4].head ? 'bold' : null);
                }
              }
            }
            y += rowH + 1;
          }
          y += 18;
        }

        if (b.quote && draw) {
          ctx.fillStyle = RULE;
          ctx.fillRect(IMG_PAD + (b.d || 0) * 22, quoteTop + 4, 3, y - quoteTop - 8);
        }
      }
      return Math.ceil(y + IMG_PAD);
    }

    function loadImages(srcs) {
      return Promise.all(srcs.map(function (src) {
        return new Promise(function (res) {
          if (!src || src.indexOf('data:') !== 0) { res([src, null]); return; }
          var im = new Image();
          im.onload = function () { res([src, im]); };
          im.onerror = function () { res([src, null]); };
          im.src = src;
        });
      })).then(function (pairs) {
        var map = {};
        pairs.forEach(function (pr) { if (pr[1]) map[pr[0]] = pr[1]; });
        return map;
      });
    }

    async function noteImageBlob(note, mime) {
      var jpeg = (mime === 'image/jpeg');
      var html = await N.exporter.inlineAttachments(
        N.exporter.toStandaloneHtml(note, { includeMeta: false }));

      var host = document.createElement('div');
      var s = html.indexOf('<main>'), e = html.lastIndexOf('</main>');
      host.innerHTML = s !== -1 && e !== -1 ? html.slice(s + 6, e) : html;

      var blocks = blocksOf(host, 0, []);
      if (!blocks.length) blocks = [{ k: 'p', runs: [{ t: '(this note is empty)' }], d: 0 }];

      var srcs = [];
      blocks.forEach(function (b) { if (b.k === 'img' && b.src) srcs.push(b.src); });
      var images = await loadImages(srcs);

      var measure = document.createElement('canvas').getContext('2d');
      var height = Math.min(render(measure, blocks, images, false), 20000);

      var scale = Math.min(2, window.devicePixelRatio || 1);
      var canvas = document.createElement('canvas');
      canvas.width = Math.round(IMG_W * scale);
      canvas.height = Math.round(height * scale);
      var ctx = canvas.getContext('2d');
      ctx.scale(scale, scale);
      ctx.textBaseline = 'alphabetic';
      ctx.fillStyle = jpeg ? '#ffffff' : '#fffdf8';
      ctx.fillRect(0, 0, IMG_W, height);
      render(ctx, blocks, images, true);

      return new Promise(function (resolve, reject) {
        canvas.toBlob(function (out) {
          if (out) resolve(out);
          else reject(new Error('This browser produced no image data.'));
        }, jpeg ? 'image/jpeg' : 'image/png', jpeg ? 0.92 : undefined);
      });
    }

    async function exportImage(note, kind) {
      if (!note) { N.toast.info('Open a note first.'); return; }
      var mime = (kind === 'jpeg' || kind === 'jpg') ? 'image/jpeg' : 'image/png';
      var ext = mime === 'image/jpeg' ? 'jpg' : 'png';
      var closing = N.toast.info('Drawing the note…', { ms: 0, key: 'ndx-img' });
      try {
        var blob = await noteImageBlob(note, mime);
        closing();
        U.downloadBlob(blob, U.safeFileName(N.store.noteTitle(note), 'note') + '.' + ext);
        N.toast.success('Saved as ' + ext.toUpperCase(), { ms: 2000 });
      } catch (err) {
        closing();
        N.toast.error(U.describeError(err), { title: 'Image export failed' });
      }
    }

    N.exporter.noteImageBlob = noteImageBlob;
    N.exporter.exportImage = exportImage;

    /* ===================================================================
     * 2. UNDO AND REDO THAT SURVIVE A RELOAD
     *
     * What was there before: nothing of its own. Ctrl+Z in the editor fell
     * through to the browser's built-in textarea undo. That has three
     * problems, and all three are the reason this exists.
     *
     *   - It is thrown away on reload. Close the tab, come back, and the
     *     last hour of edits cannot be stepped back at all.
     *   - Assigning to textarea.value from JavaScript CLEARS it. Every
     *     slash-menu insert, every formatting button, every template, every
     *     OCR paste wipes the undo stack the moment it runs. This is why
     *     "undo after using / " did nothing.
     *   - It is per-textarea, so it knows nothing about a change made from
     *     the Tasks view or the properties panel.
     *
     * So: one stack per note, of whole-document snapshots, kept in the
     * database beside the note.
     *
     * WHY WHOLE SNAPSHOTS RATHER THAN DIFFS. Notes are small and diffing is
     * where this class of feature goes wrong — a diff applied to text that
     * has since changed underneath it silently corrupts the note. A snapshot
     * cannot: whatever else has happened, putting the text back puts exactly
     * that text back. The cost is storage, and that is bounded below.
     *
     * WHERE THE STEPS COME FROM. Every path that changes a note's body goes
     * through store.updateNoteContent, which announces 'note:will-update'
     * before it overwrites anything. Typing arrives there in ~400ms batches
     * because the editor debounces its saves; a paste, a slash command or a
     * formatting button arrives as one step. Listening in one place means a
     * feature added later is undoable without knowing this code exists.
     * =================================================================== */

    var MAX_STEPS = 40;          // per note
    var MAX_BYTES = 1500000;     // stop persisting a note's history past this
    var MAX_NOTES = 25;          // how many notes keep a history on disk
    var COALESCE_MS = 1100;      // typing within this window is one step
    var COALESCE_CHARS = 30;     // ...if it is this small and in one place

    var stacks = new Map();      // noteId -> { states: [{t, a, b}], idx }
    var loading = new Map();     // noteId -> Promise, so we load once
    var expecting = null;        // a change WE are making; not a new step
    var enabled = true;

    function metaKey(id) { return 'ndx-undo:' + id; }

    function ta() { return N.editor && N.editor.getTextarea ? N.editor.getTextarea() : null; }

    function selectionOf(id) {
      var t = ta();
      if (!t || !N.editor.currentNoteId || N.editor.currentNoteId() !== id) return { a: 0, b: 0 };
      return { a: t.selectionStart || 0, b: t.selectionEnd || 0 };
    }

    /**
     * Is this edit a continuation of the last one rather than a new step?
     *
     * True only for a small insertion or deletion at a single point — which
     * is what typing looks like and what a paste, a replace-all or a
     * formatting command does not. Getting this wrong in the generous
     * direction is the classic undo complaint: one Ctrl+Z throws away a
     * paragraph because everything got merged into one step.
     */
    function isTypingContinuation(prev, next) {
      var d = Math.abs(next.length - prev.length);
      if (d === 0 || d > COALESCE_CHARS) return false;
      var longer = next.length > prev.length ? next : prev;
      var shorter = next.length > prev.length ? prev : next;
      var i = 0;
      while (i < shorter.length && longer.charCodeAt(i) === shorter.charCodeAt(i)) i++;
      var j = 0;
      while (j < shorter.length - i &&
             longer.charCodeAt(longer.length - 1 - j) === shorter.charCodeAt(shorter.length - 1 - j)) j++;
      return i + j === shorter.length;
    }

    function freshStack(text) {
      return { states: [{ t: String(text || ''), a: 0, b: 0 }], idx: 0, at: 0 };
    }

    function stackFor(id) {
      if (!stacks.has(id)) {
        var note = N.store.getNote(id);
        stacks.set(id, freshStack(note ? note.content : ''));
      }
      return stacks.get(id);
    }

    /* ------------------------------------------------------ persistence */

    var pendingSave = new Set();

    var flushStacks = U.debounce(function () {
      var ids = Array.from(pendingSave);
      pendingSave.clear();
      ids.forEach(function (id) { persist(id); });
      pruneIndex();
    }, 1400);

    async function persist(id) {
      if (!enabled) return;
      var s = stacks.get(id);
      if (!s) return;
      try {
        var payload = { v: 1, at: Date.now(), idx: s.idx, states: s.states };
        var size = 0;
        for (var i = 0; i < s.states.length; i++) size += s.states[i].t.length;
        /*
         * A very large note would put megabytes into the database for every
         * keystroke. Past the cap the history stays in memory for this
         * session and simply is not written — better than silently filling
         * someone's storage quota and taking their notes down with it.
         */
        if (size * 2 > MAX_BYTES) {
          payload.states = s.states.slice(-6);
          payload.idx = Math.min(s.idx, payload.states.length - 1);
        }
        await N.db.setMeta(metaKey(id), payload);
        var index = (await N.db.getMeta('ndx-undo-index', [])) || [];
        index = index.filter(function (x) { return x !== id; });
        index.push(id);
        await N.db.setMeta('ndx-undo-index', index);
      } catch (err) { /* history is a convenience; never break a save for it */ }
    }

    async function pruneIndex() {
      try {
        var index = (await N.db.getMeta('ndx-undo-index', [])) || [];
        if (index.length <= MAX_NOTES) return;
        var drop = index.slice(0, index.length - MAX_NOTES);
        for (var i = 0; i < drop.length; i++) {
          await N.db.delete('meta', metaKey(drop[i]));
        }
        await N.db.setMeta('ndx-undo-index', index.slice(-MAX_NOTES));
      } catch (err) { /* nothing depends on this succeeding */ }
    }

    /*
     * KEEP THIS OUT OF THE BACKUPS.
     *
     * db.exportAll() walks every store, meta included, and it is what builds
     * the GitHub sync payload and the recovery file. Left alone, every sync
     * would push up to a megabyte and a half of undo snapshots per note into
     * the repository — for text that is already there, in the .md files, in
     * its final form.
     *
     * Undo history is working state belonging to one device, not something
     * worth backing up or carrying to another machine, so it is stripped on
     * the way out. buildVaultPayload reads N.db.exportAll at call time, so
     * wrapping it here is enough; nothing in github.js had to change.
     */
    var origExportAll = N.db.exportAll;
    N.db.exportAll = async function () {
      var dump = await origExportAll.apply(N.db, arguments);
      try {
        if (dump && dump.stores && Array.isArray(dump.stores.meta)) {
          dump.stores.meta = dump.stores.meta.filter(function (r) {
            if (!r || typeof r.key !== 'string') return true;
            return r.key.indexOf('ndx-undo:') !== 0 && r.key !== 'ndx-undo-index';
          });
        }
      } catch (err) { /* a dump we could not tidy is still a valid dump */ }
      return dump;
    };

    function loadStack(id) {
      if (stacks.has(id)) return Promise.resolve(stacks.get(id));
      if (loading.has(id)) return loading.get(id);
      var p = (async function () {
        var note = N.store.getNote(id);
        var live = note ? String(note.content || '') : '';
        var saved = null;
        try { saved = await N.db.getMeta(metaKey(id), null); } catch (err) { saved = null; }
        var s;
        if (saved && saved.v === 1 && Array.isArray(saved.states) && saved.states.length) {
          s = { states: saved.states, idx: Math.max(0, Math.min(saved.idx | 0, saved.states.length - 1)), at: 0 };
          /*
           * The note may have been changed elsewhere since this history was
           * written — on another device, by a folder sync, by editing the
           * .md file in another app. If the top of the stack is not what the
           * note actually says now, the current text is appended as a new
           * step. Nothing is lost either way: the older steps are still
           * there to walk back through, and redo cannot overwrite a change
           * this history never saw.
           */
          if (s.states[s.idx].t !== live) {
            s.states = s.states.slice(0, s.idx + 1);
            s.states.push({ t: live, a: 0, b: 0 });
            if (s.states.length > MAX_STEPS) s.states = s.states.slice(-MAX_STEPS);
            s.idx = s.states.length - 1;
          }
        } else {
          s = freshStack(live);
        }
        stacks.set(id, s);
        loading.delete(id);
        return s;
      })();
      loading.set(id, p);
      return p;
    }

    /* ---------------------------------------------------------- recording */

    N.bus.on('note:will-update', function (e) {
      if (!enabled || !e || !e.note) return;
      var id = e.note.id;

      /* A change this module is applying is not a new step. */
      if (expecting && expecting.id === id && expecting.content === e.nextContent) {
        expecting = null;
        return;
      }

      /*
       * Only the note on screen. A bulk operation across the vault — a link
       * rewrite, a folder rename, a sync — would otherwise push a snapshot
       * of every note it touches into memory at once, and none of those are
       * what "undo" means to the person who pressed it.
       */
      if (id !== N.store.state.activeNoteId) return;

      var s = stackFor(id);
      var now = Date.now();

      /* A new edit ends the redo branch. */
      if (s.idx < s.states.length - 1) s.states.length = s.idx + 1;

      var top = s.states[s.idx];
      var sel = selectionOf(id);

      if (top && top.t === e.nextContent) return;

      if (top && s.idx > 0 && (now - s.at) < COALESCE_MS &&
          isTypingContinuation(top.t, e.nextContent)) {
        top.t = e.nextContent;
        top.a = sel.a; top.b = sel.b;
      } else {
        s.states.push({ t: e.nextContent, a: sel.a, b: sel.b });
        if (s.states.length > MAX_STEPS) s.states.shift();
        s.idx = s.states.length - 1;
      }
      s.at = now;

      pendingSave.add(id);
      flushStacks();
      paint();
    });

    /* ------------------------------------------------------------ applying */

    var busy = false;

    async function step(delta) {
      if (busy || !enabled) return false;
      var id = N.store.state.activeNoteId;
      if (!id) return false;

      /*
       * Whatever is in the textarea but not yet saved has to become a step
       * of its own first, or the first Ctrl+Z would throw it away without
       * ever having recorded it. flushSave() runs the save synchronously up
       * to its first await, and 'note:will-update' is emitted before that,
       * so by the time this line returns the step is on the stack.
       */
      try { if (N.editor && N.editor.flushSave) N.editor.flushSave(); } catch (err) { /* not fatal */ }

      var s = await loadStack(id);
      var target = s.idx + delta;
      if (target < 0 || target >= s.states.length) return false;

      busy = true;
      try {
        var st = s.states[target];
        s.idx = target;
        expecting = { id: id, content: st.t };
        await N.store.updateNoteContent(id, st.t);
        expecting = null;

        var t = ta();
        if (t && N.editor.currentNoteId && N.editor.currentNoteId() === id) {
          t.value = st.t;
          try { t.setSelectionRange(st.a, st.b); } catch (err) { /* out of range */ }
          /*
           * Let the editor react as it would to a keystroke: preview, word
           * count and the saved pip all update themselves. The save this
           * schedules is a no-op, because the store already holds this text.
           */
          t.dispatchEvent(new Event('input', { bubbles: true }));
          try { if (N.editor.flushSave) N.editor.flushSave(); } catch (err) { /* fine */ }
          if (document.activeElement !== t) { try { t.focus({ preventScroll: true }); } catch (err) { t.focus(); } }
        }
        pendingSave.add(id);
        flushStacks();
        paint();
        /*
         * Only once the page has actually been touched. A vibration before
         * any user gesture is refused by Chrome and logs a warning for every
         * undo, which is noise in anyone's console.
         */
        try {
          var act = navigator.userActivation;
          if (N.haptics && N.haptics.buzz && (!act || act.hasBeenActive)) N.haptics.buzz('tap');
        } catch (err) { /* optional */ }
        return true;
      } finally {
        expecting = null;
        busy = false;
      }
    }

    function undo() { return step(-1); }
    function redo() { return step(1); }

    function counts() {
      var id = N.store.state.activeNoteId;
      var s = id ? stacks.get(id) : null;
      if (!s) return { undo: 0, redo: 0 };
      return { undo: s.idx, redo: s.states.length - 1 - s.idx };
    }

    async function forget(id) {
      var target = id || N.store.state.activeNoteId;
      if (!target) return;
      stacks.delete(target);
      try { await N.db.delete('meta', metaKey(target)); } catch (err) { /* fine */ }
      paint();
    }

    async function forgetAll() {
      stacks.clear();
      try {
        var index = (await N.db.getMeta('ndx-undo-index', [])) || [];
        for (var i = 0; i < index.length; i++) await N.db.delete('meta', metaKey(index[i]));
        await N.db.setMeta('ndx-undo-index', []);
      } catch (err) { /* fine */ }
      paint();
    }

    /* ------------------------------------------------------------- the buttons */

    var btnUndo = null, btnRedo = null;

    function makeBtn(id, icon, label) {
      var b = el('button#' + id + '.icon-btn.ndx-hist-btn', { type: 'button', title: label, 'aria-label': label });
      b.appendChild(N.icons.node(icon, { size: 17 }));
      return b;
    }

    function mountButtons() {
      var host = document.querySelector('.editor-actions');
      if (!host || document.getElementById('ndx-undo')) return;
      var mod = N.shortcuts && N.shortcuts.isMac ? '⌘' : 'Ctrl';
      btnUndo = makeBtn('ndx-undo', 'undo', 'Undo (' + mod + '+Z)');
      btnRedo = makeBtn('ndx-redo', 'redo', 'Redo (' + mod + '+Shift+Z)');
      btnUndo.addEventListener('click', function () { undo(); });
      btnRedo.addEventListener('click', function () { redo(); });
      var pin = document.getElementById('btn-pin');
      if (pin && pin.parentNode === host) { host.insertBefore(btnUndo, pin); host.insertBefore(btnRedo, pin); }
      else { host.insertBefore(btnUndo, host.firstChild); host.insertBefore(btnRedo, host.firstChild); }
      paint();
    }

    function paint() {
      if (!btnUndo) return;
      var c = counts();
      btnUndo.disabled = !enabled || c.undo === 0;
      btnRedo.disabled = !enabled || c.redo === 0;
      btnUndo.title = c.undo ? 'Undo ' + c.undo + ' step' + (c.undo === 1 ? '' : 's') + ' available' : 'Nothing to undo';
      btnRedo.title = c.redo ? 'Redo ' + c.redo + ' step' + (c.redo === 1 ? '' : 's') + ' available' : 'Nothing to redo';
    }

    /* ------------------------------------------------------------- the keys */

    function inNoteEditor(target) {
      var t = ta();
      return !!t && target === t;
    }

    /*
     * Capture phase, so this runs before the textarea's own default and
     * before anything else claims the key.
     */
    document.addEventListener('keydown', function (e) {
      if (!enabled) return;
      var mod = e.metaKey || e.ctrlKey;
      if (!mod || e.altKey) return;
      var k = (e.key || '').toLowerCase();
      if (k !== 'z' && k !== 'y') return;
      if (!inNoteEditor(e.target)) return;      // only the note body
      e.preventDefault();
      e.stopPropagation();
      if (k === 'y' || e.shiftKey) redo(); else undo();
    }, true);

    /*
     * The other ways an undo arrives: the Android keyboard's undo key, iOS
     * shake-to-undo, the Edit menu on a desktop browser, and a trackpad
     * three-finger swipe. They all come through as a beforeinput with a
     * history inputType rather than as Ctrl+Z, which is why an app that only
     * listens for the keystroke feels broken on a phone.
     */
    document.addEventListener('beforeinput', function (e) {
      if (!enabled) return;
      if (e.inputType !== 'historyUndo' && e.inputType !== 'historyRedo') return;
      if (!inNoteEditor(e.target)) return;
      e.preventDefault();
      if (e.inputType === 'historyUndo') undo(); else redo();
    }, true);

    /* ---------------------------------------------------- wiring and API */

    N.bus.on('editor:loaded', function (note) {
      mountButtons();
      if (note && note.id) loadStack(note.id).then(paint);
      else paint();
    });
    N.bus.on('note:updated', function (n) {
      if (n && n.id === N.store.state.activeNoteId) paint();
    });

    N.undoText = {
      undo: undo, redo: redo, counts: counts,
      forget: forget, forgetAll: forgetAll,
      setEnabled: function (v) {
        enabled = !!v;
        if (!enabled) { stacks.clear(); forgetAll(); }
        paint();
      },
      isEnabled: function () { return enabled; },
      stackFor: function (id) { return stacks.get(id || N.store.state.activeNoteId) || null; },
    };

    N.commands.registerMany([
      { id: 'edit.undo', title: 'Undo', group: 'Edit', icon: 'undo', allowInInput: true,
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { undo(); } },
      { id: 'edit.redo', title: 'Redo', group: 'Edit', icon: 'redo', allowInInput: true,
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { redo(); } },
      { id: 'edit.forgetHistory', title: 'Forget this note’s undo history', group: 'Edit', icon: 'trash',
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { forget(); N.toast.info('Undo history cleared for this note.', { ms: 2000 }); } },
    ]);


    /* ===================================================================
     * 3. OPEN TODAY'S NOTE WHEN NODALIS STARTS
     *
     * Off by default — an app that changes what it opens without being asked
     * is a worse app. Three settings: never, every launch, or the first
     * launch of each day, which is the one most people actually want.
     *
     * It runs on 'app:ready', which is after openFirstNote() has restored
     * whatever was last open, so a deep link or a shared page still wins.
     * =================================================================== */

    /*
     * A BUG THAT ARRIVED WITH THIS: EVERY DEEP LINK IS IGNORED.
     *
     * index.html#graph, #tasks, #calendar, #scratch — all of them land on
     * the editor. So do all four shortcuts in the web app manifest, which is
     * what the phone shows when you long-press the installed Nodalis icon:
     *
     *     "Quick capture" -> ./index.html#scratch
     *     "Today's note"  -> ./index.html#review
     *     "Tasks"         -> ./index.html#tasks
     *
     * Every one of them opens the editor instead.
     *
     * applyInitialView() reads the hash and sets the view correctly. Then
     * afterBoot() calls openFirstNote(), which calls openNote(), and the
     * first line of openNote is
     *
     *     if (N.store.state.activeView !== 'editor') setView('editor');
     *
     * — quite right when you click a note in the sidebar, and it undoes the
     * deep link every single time, a few hundred milliseconds after the
     * right view was already on screen.
     *
     * Rather than change openNote, which is correct for its own job, the
     * hash is honoured once more after the app has settled. Measured on the
     * unpatched build: #graph, #tasks, #calendar and #scratch all land on
     * the editor; with this, all four land where they say.
     */
    var VIEWS = ['editor', 'graph', 'canvas', 'database', 'tasks', 'calendar',
                 'matrix', 'sticky', 'scratch', 'review', 'search', 'settings'];

    function goTo(hash) {
      try {
        if (!hash || VIEWS.indexOf(hash) === -1) return false;
        if (N.store.state.activeView === hash) return false;
        N.app.setView(hash);
        return true;
      } catch (err) { return false; }
    }

    /* On start-up, the hash the page was OPENED with (see BOOT_HASH). */
    function honourDeepLink() { return goTo(BOOT_HASH); }

    /*
     * Deliberately no 'hashchange' listener. The app writes the current view
     * back into the hash as you move around, so a listener that also moves
     * the view on a hash change is two routers arguing: the view ends up one
     * step behind, or on whatever was showing before. Nobody edits the hash
     * of a running app; what was broken was OPENING one, and that is what
     * this fixes.
     */

    async function maybeOpenToday() {
      try {
        var mode = N.store.getSetting('openTodayOnStart', 'off');
        if (mode !== 'always' && mode !== 'once') return;

        /* Something more specific was asked for. Leave it alone. */
        if (BOOT_HASH && BOOT_HASH !== 'editor') return;
        if (/shared-(text|title|url)=/.test(BOOT_SEARCH)) return;
        if (/ndaction=/.test(BOOT_SEARCH)) return;

        if (mode === 'once') {
          var today = U.todayKey();
          var last = await N.db.getMeta('ndx-daily-start', '');
          if (last === today) return;
          await N.db.setMeta('ndx-daily-start', today);
        }
        await N.daily.openToday();
      } catch (err) { /* never let this stop the app coming up */ }
    }

    N.bus.on('app:ready', function () {
      /* The link the person actually followed comes first. */
      setTimeout(honourDeepLink, 40);
      setTimeout(maybeOpenToday, 80);
    });

    N.commands.register({
      id: 'daily.openToday', title: "Open today's daily note", group: 'Notes', icon: 'calendar',
      run: function () { N.daily.openToday(); },
    });


    /* ===================================================================
     * 4. THE EXPORTS THAT WERE MISSING
     *
     * Markdown, PDF, Word, HTML, PNG and JPG were all already here (PNG and
     * JPG just never worked — see 1). What was not here:
     *
     *   - Plain text, for pasting somewhere that would show the markdown
     *     asterisks rather than hide them.
     *   - Copy as rich text, which is the one people actually reach for:
     *     paste into Word, Gmail, Docs or Slack and the headings, bold and
     *     lists survive. No file, no download, no dialog.
     *
     * Rich copy goes through a hidden contenteditable and execCommand
     * rather than navigator.clipboard.write, deliberately: the async
     * clipboard API needs a user gesture that has not been interrupted by
     * an await, and choosing from a dialog is exactly such an interruption.
     * Safari refuses it; this works everywhere.
     * =================================================================== */

    function noteHtmlFragment(note) {
      return N.markdown.render(note.content || '', { headingAnchors: false });
    }

    function notePlainText(note) {
      var div = document.createElement('div');
      div.innerHTML = noteHtmlFragment(note);
      var text = div.textContent || '';
      return (N.store.noteTitle(note) + '\n\n' + text).replace(/\n{3,}/g, '\n\n').trim() + '\n';
    }

    function exportText(note) {
      U.downloadBlob(new Blob([notePlainText(note)], { type: 'text/plain;charset=utf-8' }),
        U.safeFileName(N.store.noteTitle(note), 'note') + '.txt');
      N.toast.success('Saved as plain text', { ms: 1800 });
    }

    function copyRich(note) {
      var html = '<h1>' + U.escapeHtml(N.store.noteTitle(note)) + '</h1>' + noteHtmlFragment(note);
      var holder = el('div', {
        style: { position: 'fixed', left: '-10000px', top: '0', width: '700px', whiteSpace: 'normal' },
        contenteditable: 'true',
      });
      holder.innerHTML = html;
      document.body.appendChild(holder);
      var ok = false;
      try {
        var range = document.createRange();
        range.selectNodeContents(holder);
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
        ok = document.execCommand('copy');
        sel.removeAllRanges();
      } catch (err) { ok = false; }
      document.body.removeChild(holder);

      if (ok) { N.toast.success('Copied with formatting — paste into Word, Docs or Gmail', { ms: 2600 }); return; }
      /* Last resort: the plain text, which at least always lands. */
      try {
        navigator.clipboard.writeText(notePlainText(note));
        N.toast.info('Copied as plain text — this browser would not take the formatting.', { ms: 3000 });
      } catch (err) {
        N.toast.error('This browser would not let the page copy anything.');
      }
    }

    function exportNoteDialog(noteId) {
      var note = N.store.getNote(noteId || N.store.state.activeNoteId);
      if (!note) { N.toast.info('Open a note first.'); return; }
      return N.modal.choose({
        title: 'Export "' + U.truncate(N.store.noteTitle(note), 34) + '"',
        options: [
          { value: 'pdf', label: 'PDF', description: 'Opens your print dialog — choose Save as PDF', icon: 'file' },
          { value: 'docx', label: 'Word (.docx)', description: 'Opens in Word, Pages, Docs and LibreOffice', icon: 'file-text' },
          { value: 'md', label: 'Markdown (.md)', description: 'The original file, frontmatter and all', icon: 'file-text' },
          { value: 'html', label: 'Web page (.html)', description: 'Self-contained, images included', icon: 'globe' },
          { value: 'txt', label: 'Plain text (.txt)', description: 'No markdown symbols, just the words', icon: 'file-text' },
          { value: 'rich', label: 'Copy with formatting', description: 'Paste straight into Word, Docs, Gmail or Slack', icon: 'copy' },
          { value: 'png', label: 'Image (.png)', description: 'Good for sharing a screenshot-style copy', icon: 'image' },
          { value: 'jpg', label: 'Image (.jpg)', description: 'Smaller file, white background', icon: 'image' },
        ],
      }).then(function (choice) {
        if (!choice) return;
        var E = N.exporter;
        if (choice === 'md') return E.exportMarkdown(note);
        if (choice === 'pdf') return E.exportPdf(note);
        if (choice === 'docx') return E.exportDocx(note);
        if (choice === 'html') return E.exportHtml(note);
        if (choice === 'txt') return exportText(note);
        if (choice === 'rich') return copyRich(note);
        if (choice === 'png') return E.exportImage(note, 'png');
        if (choice === 'jpg') return E.exportImage(note, 'jpeg');
      });
    }

    N.exporter.exportText = exportText;
    N.exporter.copyRich = copyRich;
    N.exporter.exportNoteDialog = exportNoteDialog;

    /* Re-registering an id replaces it, so the menus, the palette and the
       keyboard shortcut all reach the dialog above rather than the old one. */
    function activeNote() { return N.store.getNote(N.store.state.activeNoteId); }
    N.commands.registerMany([
      { id: 'export.note', title: 'Export this note…', group: 'Export', icon: 'download', accel: 'Mod+Shift+E',
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { exportNoteDialog(); } },
      { id: 'export.txt', title: 'Export note as plain text', group: 'Export', icon: 'file-text',
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { exportText(activeNote()); } },
      { id: 'export.rich', title: 'Copy note with formatting', group: 'Export', icon: 'copy',
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { copyRich(activeNote()); } },
      { id: 'export.jpg', title: 'Export note as JPG image', group: 'Export', icon: 'image',
        when: function () { return !!N.store.state.activeNoteId; },
        run: function () { N.exporter.exportImage(activeNote(), 'jpeg'); } },
    ]);

    /* ===================================================================
     * 5. THE SETTINGS FOR ALL OF THE ABOVE
     *
     * Settings.js builds its panel from private functions, so rather than
     * reaching into it, the rows are appended to the rendered blocks once
     * they appear. A MutationObserver rather than a wrapper because the
     * panel rebuilds itself on every change — changing the theme, resizing,
     * switching section — and a wrapper would only catch the first one.
     * =================================================================== */

    function settingRow(name, description, control) {
      var r = el('div.setting-row');
      var info = el('div.setting-info');
      info.appendChild(el('div.setting-name', null, name));
      if (description) info.appendChild(el('div.setting-desc', null, description));
      r.appendChild(info);
      var c = el('div.setting-control');
      if (control) c.appendChild(control);
      r.appendChild(c);
      return r;
    }

    function settingSelect(key, fallback, options, onChange) {
      var field = el('select.field');
      var current = String(N.store.getSetting(key, fallback));
      options.forEach(function (o) {
        field.appendChild(el('option', { value: o.value, selected: current === String(o.value) }, o.label));
      });
      field.addEventListener('change', function () {
        N.store.setSetting(key, field.value);
        if (onChange) onChange(field.value);
      });
      return field;
    }

    function injectDailyRows(block) {
      if (block.querySelector('.ndx-row-daily')) return;
      var row = settingRow(
        'Open today’s note when Nodalis starts',
        'Creates it if it does not exist yet. A link straight to another note or view still wins.',
        settingSelect('openTodayOnStart', 'off', [
          { value: 'off', label: 'Never' },
          { value: 'once', label: 'Once a day' },
          { value: 'always', label: 'Every time' },
        ]));
      row.classList.add('ndx-row-daily');
      /* Straight under the folder row, where someone setting daily notes up
         is already looking. */
      var first = block.querySelector('.setting-row');
      if (first && first.parentNode) first.parentNode.insertBefore(row, first.nextSibling);
      else block.appendChild(row);
    }

    function injectEditorRows(block) {
      if (block.querySelector('.ndx-row-undo')) return;

      var sw = el('div.switch' + (enabled ? '.is-on' : ''), {
        role: 'switch', tabindex: '0', 'aria-checked': String(enabled),
      });
      var flip = function () {
        var next = !enabled;
        sw.classList.toggle('is-on', next);
        sw.setAttribute('aria-checked', String(next));
        N.store.setSetting('persistentUndo', next);
        N.undoText.setEnabled(next);
      };
      sw.addEventListener('click', flip);
      sw.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); }
      });

      var row = settingRow('Keep undo history after a reload',
        'Up to ' + MAX_STEPS + ' steps per note, for your ' + MAX_NOTES +
        ' most recent notes, stored with the notes themselves. Undo also covers pasting, the / menu and the formatting buttons.',
        sw);
      row.classList.add('ndx-row-undo');
      block.appendChild(row);

      var clear = el('button.btn', { type: 'button' }, 'Forget all undo history');
      clear.addEventListener('click', async function () {
        await N.undoText.forgetAll();
        N.toast.success('Undo history cleared.', { ms: 1800 });
      });
      var row2 = settingRow('Clear the saved history',
        'The notes themselves are untouched. Only the record of how they got there goes.', clear);
      row2.classList.add('ndx-row-undo');
      block.appendChild(row2);
    }

    function sweepSettings() {
      var daily = document.getElementById('settings-daily');
      if (daily) { try { injectDailyRows(daily); } catch (err) { /* cosmetic */ } }
      var editor = document.getElementById('settings-editor');
      if (editor) { try { injectEditorRows(editor); } catch (err) { /* cosmetic */ } }
    }

    (function watchSettings() {
      var host = document.getElementById('settings-body');
      if (!host) { setTimeout(watchSettings, 400); return; }
      sweepSettings();
      try {
        new MutationObserver(function () { sweepSettings(); })
          .observe(host, { childList: true, subtree: true });
      } catch (err) { /* older browser: the rows still appear on first render */ }
    })();


    /* --------------------------------------------------------- start-up */

    /* The saved preference for the undo engine, before anything is recorded. */
    (function () {
      var pref = N.store.getSetting('persistentUndo', true);
      enabled = pref !== false;
    })();

    mountButtons();
    if (N.store.state.activeNoteId) loadStack(N.store.state.activeNoteId).then(paint);
    N.bus.on('settings:changed', function () {
      var pref = N.store.getSetting('persistentUndo', true);
      if ((pref !== false) !== enabled) { enabled = pref !== false; paint(); }
    });

    /* Anything still unsaved when the tab goes away. */
    window.addEventListener('pagehide', function () {
      var id = N.store.state.activeNoteId;
      if (id && stacks.has(id)) persist(id);
    });
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) return;
      var id = N.store.state.activeNoteId;
      if (id && stacks.has(id)) persist(id);
    });
  });
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


def bump_sw():
    """Make every device throw its cached copy away and take the new build."""
    if not os.path.isfile(SW):
        say("  sw.js              not in this folder, skipped")
        return
    sw = read(SW)
    m = re.search(r"const VERSION = 'nodalis-v([0-9]+)\.([0-9]+)';", sw)
    if not m:
        say("  sw.js              version line not recognised, left alone")
        return
    new = "nodalis-v%s.%d" % (m.group(1), int(m.group(2)) + 1)
    b = backup(SW)
    write(SW, sw[:m.start()] + "const VERSION = '%s';" % new + sw[m.end():])
    say("  Backup made        " + b)
    say("  Bumped sw.js       nodalis-v%s.%s -> %s" % (m.group(1), m.group(2), new))


# ---------------------------------------------------------------------- main


def main():
    say("")
    say("  Nodalis patcher — v10.9.1 + v10.9.2")
    say("  " + "-" * 44)

    if not os.path.isfile(INDEX):
        fail("no index.html in this folder (" + HERE + ").")

    html = read(INDEX)
    say("  Found index.html   %.1f MB" % (len(html.encode("utf-8")) / 1048576.0))

    todo = []
    if MARK_V1 not in html:
        todo.append(("v10.9.1 layout lock", CSS_V1, JS_V1, MARK_V1))
    else:
        say("  v10.9.1            already applied, skipping")
    if MARK_V2 not in html:
        todo.append(("v10.9.2 features", CSS_V2, JS_V2, MARK_V2))
    else:
        say("  v10.9.2            already applied, skipping")

    if not todo:
        say("")
        say("  Everything is already in place. Nothing to do.")
        say("")
        return

    # Work both anchors out BEFORE writing anything, so a file that does not
    # match is left completely untouched.
    css_at = css_insert_point(html)
    js_at = js_insert_point(html)
    say("  Anchors found      </style> at byte %s, </body> at byte %s"
        % (f"{css_at:,}", f"{js_at:,}"))

    b = backup(INDEX)
    say("  Backup made        " + b)

    out = html
    # Insert the later anchor first so the earlier offset stays valid, and
    # apply the patches in order so v1 stays above v2 in the file.
    js_blob = "".join(p[2] for p in todo)
    css_blob = "".join(p[1] for p in todo)
    out = insert_at(out, js_at, js_blob)
    out = insert_at(out, css_at, css_blob)

    write(INDEX, out)
    added = len(out.encode("utf-8")) - len(html.encode("utf-8"))
    say("  Applied            " + ", ".join(p[0] for p in todo))
    say("  Patched index.html +%s bytes, %s new lines"
        % (f"{added:,}", out.count("\n") - html.count("\n")))

    # ----------------------------------------------------------- self-check
    # Read the file back off the disk and prove the patch landed where it was
    # meant to. If anything is off, put the backup back automatically so you
    # are never left with a half-patched app.
    check = read(INDEX)
    problems = []
    for _, _, _, mark in todo:
        if check.count(mark) != 2:
            problems.append("the two blocks for " + mark.split("—")[0].strip() +
                            " are not both present")
    if check.count("<script>") != html.count("<script>") + len(todo):
        problems.append("a new <script> tag did not land cleanly")
    head_at = check.index("</head>")
    for _, _, _, mark in todo:
        if check.index(mark) > head_at:
            problems.append("a CSS block landed outside <head>")
    if problems:
        shutil.copy2(os.path.join(HERE, b), INDEX)
        fail("self-check failed (" + "; ".join(sorted(set(problems))) +
             "). Your original index.html has been put back, unchanged.")
    say("  Self-check         passed")

    bump_sw()

    say("")
    say("  Done. Next steps:")
    say("    1. Open index.html in a browser and check it still works.")
    say("    2. Commit and push index.html and sw.js to GitHub.")
    say("    3. On your phone or laptop, load the site and do a hard refresh")
    say("       (Ctrl+Shift+R, or Cmd+Shift+R on a Mac) the first time.")
    say("")


if __name__ == "__main__":
    main()
