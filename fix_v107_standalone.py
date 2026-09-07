#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nodalis v10.7.0 - the loading screen, the menus, read-along on a phone,
                  the selection bar, and the guest notifications.

Run it on your index.html in a Codespace:

    python3 fix_v107_standalone.py index.html --dry-run     # report only
    python3 fix_v107_standalone.py index.html               # apply

One file, standard library only. It refuses to run twice, refuses a file
that is not at v10.6.0, and writes NOTHING unless every single edit anchors
cleanly - so a failed run leaves your file exactly as it was.
"""

import io
import os
import sys

MARKER = 'v10.7: A MENU IS NEVER THE PAGE, AND NEVER TOUCHES THE EDGE'
REQUIRES = "v10.6: A MENU THAT MUST SCROLL DOES NOT ALSO NEED TO FILL THE SCREEN"
REQUIRES_NAME = 'v10.6.0'
PREV_PATCHER = 'fix_v106_standalone.py'

_BLOCKS = {}

_BLOCKS['menucap107.js'] = r'''    /*
     * v10.7: A MENU IS NEVER THE PAGE, AND NEVER TOUCHES THE EDGE.
     *
     * Reported: "the three dot drop down menu on the left side called note
     * action is not resolved ... there should be gap between the menu and
     * the app, it should not cover fully".
     *
     * Measured on the v10.6 build, note menu (629px of rows), right-clicked
     * at five heights in a 1280x800 window:
     *
     *     click y=  96 -> menu at  96..727   gap below  73px
     *     click y= 256 -> menu at 161..792   gap below   8px
     *     click y= 400 -> menu at 161..792   gap below   8px
     *     click y= 576 -> menu at 161..792   gap below   8px
     *     click y= 736 -> menu at 161..792   gap below   8px
     *
     * 79% of the window, pinned 8px off the bottom edge, at every click
     * below the first. Two faults, both here:
     *
     *   1. `openUp` was only ever consulted for a menu with an ANCHOR
     *      ELEMENT. A right-click passes a POINT, and the placement below
     *      read `o.y` directly - so a context menu never opened upward. It
     *      was placed at the click and then shoved up by the clamp until it
     *      sat on the bottom edge.
     *
     *   2. `room` fell back to `visH - 2 * pad` - the whole column - so the
     *      cap was computed from space the menu was never going to get.
     *
     * The rule now: measure the side the menu will actually open on; if the
     * menu cannot fit on that side, let it float free of the click and use
     * the column instead of scrolling inside a sliver; and keep GAP pixels
     * clear at the top and the bottom, always. A menu that must scroll is
     * still short - 560px, and never more than 72% of what is visible.
     */
    const GAP = 18;
    const hasAnchor = !!(o.anchor && o.anchor.getBoundingClientRect);
    const aRect = hasAnchor ? o.anchor.getBoundingClientRect() : null;
    const pointY = (o.y === undefined || o.y === null) ? null : o.y;

    const roomBelow = hasAnchor ? (visH - aRect.bottom - 4 - GAP)
      : (pointY === null ? (visH - 2 * GAP) : (visH - pointY - GAP));
    const roomAbove = hasAnchor ? (aRect.top - 4 - GAP)
      : (pointY === null ? (visH - 2 * GAP) : (pointY - GAP));

    /*
     * The height it WANTS, as a border box. scrollHeight is the padding box,
     * and --menu-max is a max-height on the border box, so comparing the two
     * directly is two pixels wrong - enough to hand a menu a ceiling exactly
     * its own content height and then show a scrollbar for the border.
     */
    const chrome = Math.max(0, menu.offsetHeight - menu.clientHeight);
    const natural = menu.scrollHeight + chrome;
    /* Upward when it does not fit below and there is genuinely more above -
       and now for a right-click too, not only for an anchored button. */
    const openUp = (hasAnchor || pointY !== null) &&
      natural > roomBelow && roomAbove > roomBelow;

    const column = Math.round(visH - 2 * GAP);
    const side = Math.round(openUp ? roomAbove : roomBelow);
    /* It does not fit on the side it opens on: let it leave the click and
       take the column. A menu that could have been whole should be whole,
       and one that has to scroll should scroll in the larger space. */
    const floating = natural > side;
    const roomCap = Math.max(200, floating ? column : Math.min(side, column));

    const MENU_HARD_CAP = 690;
    /* What the menu can actually use: the room, but never past the
       stylesheet's own ceiling - otherwise a tall window "fits" 875px of
       content into 1024px of room and the CSS clamp scrolls it at 690
       anyway, which is the takeover this is meant to stop. */
    const fitCap = Math.min(roomCap, MENU_HARD_CAP);
    const cap = natural <= fitCap
      ? roomCap
      : Math.max(220, Math.min(roomCap, 560, Math.round(visH * 0.72)));
    menu.style.setProperty('--menu-max', cap + 'px');
    /*
     * Re-measure - with offsetHeight, NOT a bounding rect.
     *
     * .menu opens on `menu-in`, which is a scale, and getBoundingClientRect
     * reports the TRANSFORMED box. Measured on a 1280x800 window: a menu
     * 631px tall reported 593px because it was two frames into a 0.94 scale,
     * so it was placed 38px too low and its last row ended up below the
     * bottom of the screen. offsetHeight is the layout box and does not move
     * while the menu animates in.
     */
    const mw = menu.offsetWidth;
    const mh = menu.offsetHeight;

    if (hasAnchor) {
      const a2 = o.anchor.getBoundingClientRect();
      x = o.align === 'right' ? a2.right - mw : a2.left;
      y = openUp ? a2.top - mh - 4 : a2.bottom + 4;
    } else if (pointY !== null) {
      y = openUp ? pointY - mh - 2 : pointY;
    }
    if (x === undefined) x = (vw - mw) / 2;
    if (y === undefined) y = (visH - mh) / 2;

    if (x + mw > vw - pad) x = vw - mw - pad;
    x = Math.max(pad, x);
    /*
     * v10.4: CLAMP AGAINST WHAT IS ON SCREEN, NOT THE LAYOUT VIEWPORT.
     *
     * v10.1 taught the max-height to use visualViewport and then clamped the
     * POSITION against vh anyway, so on a mobile browser whose toolbar is
     * covering the bottom of the page a menu could still be placed with its
     * last row underneath that toolbar. Same measurement for both now - and
     * from v10.7 with GAP rather than 8px, so there is air, not a hairline.
     */
    if (y + mh > visH - GAP) y = visH - mh - GAP;
    y = Math.max(GAP, y);
'''

_BLOCKS['readindex107.js'] = r'''  /*
   * v10.7: THE INDEX HAS TO SURVIVE THE PREVIEW BEING RE-RENDERED.
   *
   * This is the whole of "on voice or reading the text it is not
   * highlighting word by word but it is working in desktop".
   *
   * buildReadIndex() walks the pane once and keeps references to its TEXT
   * NODES. renderPreview() is `preview.innerHTML = html`, which throws every
   * one of those nodes away. Every Range built afterwards points at orphans:
   * CSS.highlights.set() accepts it without complaint and paints nothing.
   * The pane element itself survives, so `.is-reading` stays and the note
   * stays dimmed - a dimmed note with no highlight anywhere, which is
   * exactly what was reported and photographed.
   *
   * Why the phone and not the desktop: below 1024px 'split' has no preview
   * pane, so showReadable() switches the editor to read mode - and setMode()
   * calls renderPreview(). Measured on the v10.6 build, reading the same
   * note in the same second:
   *
   *     desktop 1280x800   0 re-renders   marks live   -> highlights
   *     phone   390x844    2 re-renders   marks DETACHED -> nothing
   *
   * 100% reproducible, every read, on every phone.
   *
   * The fix is to stop trusting the index: check it is still attached before
   * every mark, re-walk when it is not, and repaint the current marks the
   * moment the preview says it has re-rendered. Offsets are the contract
   * between the two sides, and offsets survive a re-render - only nodes do
   * not.
   */
  let lastLine = null;
  let lastWord = null;
  let watchingPreview = false;

  function nodeLive(n) {
    if (!n) return false;
    try { return n.isConnected !== undefined ? !!n.isConnected : document.contains(n); }
    catch (err) { return false; }
  }

  function indexIsLive() {
    if (!readNodes.length) return false;
    return nodeLive(readNodes[0].node) && nodeLive(readNodes[readNodes.length - 1].node);
  }

  /** Make sure the index points at nodes that are still in the document. */
  function ensureIndex() {
    if (indexIsLive()) return true;
    const before = readText;
    if (!walkReadIndex()) return false;
    /*
     * Same text in the same order means every offset still means what it
     * meant, so the marks simply land on the new nodes. Different text (the
     * note was edited while it was being read) means the offsets are
     * fiction: drop the chunk so the next one probes again.
     */
    if (readText !== before) { chunkSpan = null; readFrom = 0; lastLine = null; lastWord = null; }
    return true;
  }

  /** Put the marks back after the pane has been rebuilt underneath them. */
  function repaintMarks() {
    if (!lastLine && !lastWord) return;
    if (!ensureIndex()) return;
    if (lastLine) setHl(HL_LINE, rangeFor(lastLine.start, lastLine.end));
    if (lastWord) setHl(HL_WORD, rangeFor(lastWord.start, lastWord.end));
  }

  function watchPreview() {
    if (watchingPreview) return;
    watchingPreview = true;
    try {
      N.bus.on('preview:rendered', function () {
        try { repaintMarks(); } catch (err) { /* decoration only */ }
      });
    } catch (err) { /* no bus, no watching */ }
  }

  function buildReadIndex() {
    readFrom = 0; chunkSpan = null; lastLine = null; lastWord = null;
    if (!showReadable()) return false;
    watchPreview();
    return walkReadIndex();
  }

  function walkReadIndex() {
    readNodes = []; readText = '';
    const pane = readPane();
    if (!pane) return false;
'''

_BLOCKS['sethl107.js'] = r'''  /*
   * v10.7: A SECOND WAY TO DRAW THE MARK, FOR ENGINES THAT HAVE NO FIRST.
   *
   * The CSS Custom Highlight API is the right tool - it paints a range
   * without putting a single wrapper element into the note - but it is not
   * everywhere. Firefox only shipped it in 140, Safari in 17.2, and an
   * Android WebView can be years behind the Chrome on the same phone. On any
   * of those, canHighlight() is false and read-along used to draw nothing at
   * all while still claiming to be reading.
   *
   * So when the API is missing, or refuses a range, the mark is drawn as
   * boxes in a layer behind the text - measured from the same Range, so it
   * lands in the same place. Still no wrapper elements in the note: the
   * layer is one empty div that contributes no text of its own, which is
   * what keeps the index and the offsets honest.
   */
  const BOX_CLASS = {};
  BOX_CLASS[HL_LINE] = 'nd-hl-line';
  BOX_CLASS[HL_WORD] = 'nd-hl-word';

  function hlLayer(pane) {
    let layer = null;
    for (let i = 0; i < pane.children.length; i++) {
      if (pane.children[i].className === 'nd-hl-layer') { layer = pane.children[i]; break; }
    }
    if (!layer) {
      layer = document.createElement('div');
      layer.className = 'nd-hl-layer';
      layer.setAttribute('aria-hidden', 'true');
      try {
        if (getComputedStyle(pane).position === 'static') pane.style.position = 'relative';
      } catch (err) { /* the default is fine */ }
      /*
       * Appended, not inserted first. An out-of-flow first child still stops
       * the pane from collapsing its first heading's top margin: measured, a
       * 47px jump the moment the layer appeared. Last costs nothing that
       * shows, and the text still paints over the boxes because the boxes
       * sit at z-index 0 and everything else at 1.
       */
      pane.appendChild(layer);
      /* The boxes ARE the mark here, so the note must not also be dimmed -
         dimmed text on a coloured box is worse than either alone. */
      pane.classList.add('has-hl-boxes');
    }
    return layer;
  }

  function clearBoxes() {
    try {
      Array.prototype.forEach.call(document.querySelectorAll('.nd-hl-layer'),
        function (l) {
          if (l.parentNode) {
            l.parentNode.classList.remove('has-hl-boxes');
            l.parentNode.removeChild(l);
          }
        });
    } catch (err) { /* nothing to clear */ }
  }

  function paintBoxes(name, range) {
    const pane = readPane();
    if (!pane) return;
    const cls = BOX_CLASS[name] || 'nd-hl-word';
    const layer = hlLayer(pane);
    Array.prototype.forEach.call(layer.querySelectorAll('.' + cls),
      function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    if (!range) return;
    let rects;
    try { rects = range.getClientRects(); } catch (err) { return; }
    if (!rects || !rects.length) return;
    const pr = pane.getBoundingClientRect();
    /* The layer scrolls with the pane's content, so the boxes are placed in
       the pane's own scroll space rather than the viewport's. */
    const ox = pr.left - pane.scrollLeft;
    const oy = pr.top - pane.scrollTop;
    for (let i = 0; i < rects.length; i++) {
      const r = rects[i];
      if (!(r.width > 0 && r.height > 0)) continue;
      const box = document.createElement('span');
      box.className = 'nd-hl-box ' + cls;
      box.style.left = Math.round(r.left - ox) + 'px';
      box.style.top = Math.round(r.top - oy) + 'px';
      box.style.width = Math.ceil(r.width) + 'px';
      box.style.height = Math.ceil(r.height) + 'px';
      layer.appendChild(box);
    }
  }

  function setHl(name, range) {
    if (canHighlight()) {
      try {
        if (!range) { CSS.highlights.delete(name); return; }
        CSS.highlights.set(name, new Highlight(range));
        return;
      } catch (err) { /* the engine refused it; draw it instead */ }
    }
    paintBoxes(name, range);
  }

'''

_BLOCKS['clearreading107.js'] = r'''  function clearReading() {
    if (canHighlight()) {
      try { CSS.highlights.delete(HL_LINE); CSS.highlights.delete(HL_WORD); } catch (err) {}
    }
    /* v10.7: and the drawn fallback, wherever it was drawn. */
    try { clearBoxes(); } catch (err) {}
    try {
      Array.prototype.forEach.call(document.querySelectorAll('.prose.is-reading'),
        function (e) { e.classList.remove('is-reading'); });
    } catch (err) {}
    readNodes = []; readText = ''; readFrom = 0; chunkSpan = null;
    lastLine = null; lastWord = null;
  }
'''

_BLOCKS['css107.css'] = r'''
/* ===== v10.7: the read-along mark, drawn where it cannot be highlighted ===== */

.nd-hl-layer {
  position: absolute;
  left: 0; top: 0;
  width: 100%; height: 0;
  pointer-events: none;
  z-index: 0;
}
.nd-hl-box {
  position: absolute;
  border-radius: 3px;
  pointer-events: none;
}
.nd-hl-box.nd-hl-line { background: color-mix(in srgb, var(--accent) 15%, transparent); }
.nd-hl-box.nd-hl-word { background: color-mix(in srgb, var(--accent) 38%, transparent); }
.prose.has-hl-boxes > .nd-hl-layer { margin: 0; }
/* The text has to sit above its own mark. */
.prose.has-hl-boxes > *:not(.nd-hl-layer) { position: relative; z-index: 1; }
/* The boxes are the mark, so the note is not also dimmed - dimmed text over
   a coloured box reads worse than either on its own. */
.prose.is-reading.has-hl-boxes { color: inherit; }

/* ===== v10.7: the selection bar fills the bar it is in =====
 *
 * Reported as "the menu on top is not aligned and there is a gap at right
 * side". Measured on v10.6, the strip of controls against the window:
 *
 *     360px window -> controls end at 317, dock ends at 360   43px of nothing
 *     390px window -> controls end at 351, dock ends at 390   39px
 *     412px window -> controls end at 373, dock ends at 412   39px
 *
 * The cause is one line: the scroller carried
 *
 *     max-width: min(620px, calc(100vw - 190px))
 *
 * where 190px was a guess at the width of the tail beside it. The real tail
 * is 139-141px on a phone, so the guess reserved forty pixels that nothing
 * was ever put in - and because it is a max-width rather than a margin, the
 * space sat empty at the right-hand end.
 *
 * Inside the dock the guess is not needed at all: the tail is `flex: none`
 * and the scroller is `flex: 1 1 auto; min-width: 0`, so the layout already
 * reserves exactly the tail's real width, at every window size, with no
 * arithmetic. Removing the cap hands those forty pixels back to the buttons.
 */
.sel-dock .sel-scroll { max-width: none; }

/* ===== v10.7: the guest notifications stack instead of covering each other =====
 *
 * All three of guest mode's bottom bars - "the author has updated this
 * note", the saved-copy/rate-limit notice, and the one piece of promotion -
 * were `position: fixed; left: 50%; bottom: <almost the same>`. Measured on
 * a 390x844 phone with all three showing:
 *
 *     update  x= 98..293  y=702..828
 *     saved   x=  8..382  y=752..828
 *     cta     x=  8..382  y=753..832
 *
 * Three bars, one place: whichever had the higher z-index covered the rest,
 * and the update bar was a different width from the other two into the
 * bargain. They share one column now, newest at the bottom, with a gap
 * between them and the same width for all three.
 */
#nd-guest-stack {
  position: fixed;
  left: 50%;
  bottom: calc(var(--sp-5) + var(--safe-bottom, 0px));
  transform: translateX(-50%);
  z-index: 60;
  width: min(560px, calc(100vw - var(--sp-6) * 2));
  max-height: calc(100vh - var(--sp-8) * 2);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--sp-3);
  pointer-events: none;
}
#nd-guest-stack > * { pointer-events: auto; }
/* Inside the stack they are ordinary blocks: the column does the placing. */
#nd-guest-stack > .guest-update,
#nd-guest-stack > .guest-note-bar,
#nd-guest-stack > .guest-cta-bar {
  position: relative;
  left: auto; right: auto; bottom: auto;
  width: auto; max-width: none;
  margin: 0;
  animation: none;
}
#nd-guest-stack > .guest-update,
#nd-guest-stack > .guest-note-bar { transform: translateY(10px); }
#nd-guest-stack > .guest-cta-bar { transform: translateY(14px); }
#nd-guest-stack > .guest-update.is-in,
#nd-guest-stack > .guest-note-bar.is-in,
#nd-guest-stack > .guest-cta-bar.is-in { transform: none; }
@media (max-width: 760px) {
  #nd-guest-stack { width: calc(100vw - var(--sp-4) * 2); }
}
'''


def block(name):
    return _BLOCKS[name]


BANNER = '=' * 80


def main(argv):
    if len(argv) < 2:
        print('usage: python3 fix_v107_standalone.py <index.html> [--dry-run]')
        return 2
    path = argv[1]
    dry = '--dry-run' in argv[2:]

    if not os.path.isfile(path):
        print('ERROR: no such file: %s' % path)
        return 1

    with io.open(path, encoding='utf-8') as fh:
        src = fh.read()

    print(BANNER)
    print(' Nodalis v10.7.0 - loading screen, menus, mobile read-along,')
    print('                   selection bar, guest notifications')
    print(BANNER)
    print(' file: %s  (%d bytes)' % (path, len(src.encode('utf-8'))))
    print('')

    if MARKER in src:
        print('ERROR: v10.7.0 is already installed in this file.')
        return 1
    if REQUIRES not in src:
        print('ERROR: this file is not at %s. Run %s first.' % (REQUIRES_NAME, PREV_PATCHER))
        return 1

    state = {'src': src, 'edits': 0, 'fail': 0}

    def once(old, new, label):
        s = state['src']
        n = s.count(old)
        if n != 1:
            print('   ! anchor for "%s" found %d times (need exactly 1)' % (label, n))
            return False
        state['src'] = s.replace(old, new)
        return True

    def exactly(old, new, want, label):
        s = state['src']
        n = s.count(old)
        if n != want:
            print('   ! anchor for "%s" found %d times (need exactly %d)' % (label, n, want))
            return False
        state['src'] = s.replace(old, new)
        return True

    def report(label, ok):
        if ok:
            state['edits'] += 1
            print('   %-56s ok' % label)
        else:
            print('   %-56s FAILED' % label)
            state['fail'] += 1

    report('loading screen: the Skip button is gone', once("    const skip = el('button.loader-skip', { type: 'button' }, 'Skip');\n    skip.addEventListener('click', function (e) { e.stopPropagation(); requestSkip(); });\n    root.appendChild(skip);", '    /*\n     * v10.7: NO SKIP BUTTON.\n     *\n     * Asked for, and right: the sequence is 2.35 seconds and the button was\n     * the only thing on the screen competing with the mark for attention.\n     * Skipping itself stays - a tap, a key or a scroll still cuts the rest\n     * short, which is the affordance that actually matters and costs no\n     * pixels. requestSkip() is untouched and is still what the app listens\n     * for, so nothing downstream changes.\n     */', 'skip button'))

    report('menus: a gap at the edge, and never the whole page', once('    const roomBelow = (o.anchor && o.anchor.getBoundingClientRect)\n      ? visH - o.anchor.getBoundingClientRect().bottom - 4 - pad\n      : visH - (o.y === undefined ? 0 : o.y) - pad;\n    const roomAbove = (o.anchor && o.anchor.getBoundingClientRect)\n      ? o.anchor.getBoundingClientRect().top - 4 - pad\n      : (o.y === undefined ? visH : o.y) - pad;\n    const openUp = (o.anchor && o.anchor.getBoundingClientRect)\n      ? (rect.height > roomBelow && roomAbove > roomBelow)\n      : false;\n    const room = Math.max(160, openUp ? roomAbove : Math.max(roomBelow, roomAbove, visH - 2 * pad));\n    /*\n     * v10.6: A MENU THAT MUST SCROLL DOES NOT ALSO NEED TO FILL THE SCREEN.\n     *\n     * Measured on the More menu: 875px of rows. v10.4 raised the ceiling to\n     * 690px so the NOTE menu (629px) would stop hiding Delete behind a\n     * scroll - which was right for that menu and wrong for this one. On a\n     * window with 743px of usable height, a 690px menu is the page.\n     *\n     * So the ceiling now depends on whether the content fits:\n     *\n     *   fits in the room available  ->  keep the room, no scrolling\n     *   longer than that            ->  short, and scroll: 560px at most,\n     *                                   and never more than 72% of what is\n     *                                   visible, with 220px as the floor\n     *\n     * The note menu is unaffected (629px, it fits). The More menu becomes a\n     * menu again instead of a takeover: 560px of a 800px window, sixteen\n     * rows deep, with the app still visible around it. Scrolling only ever\n     * happens for menus that could not have fitted anyway.\n     */\n    const MENU_HARD_CAP = 690;\n    const roomCap = Math.round(Math.min(room, visH - 2 * pad));\n    /* What the menu could actually use: the room, but never past the\n       stylesheet\'s own ceiling - otherwise a tall window "fits" 875px of\n       content into 1024px of room and the CSS clamp scrolls it at 690\n       anyway, which is the takeover this is meant to stop. */\n    const fitCap = Math.min(roomCap, MENU_HARD_CAP);\n    const natural = menu.scrollHeight;\n    const cap = natural <= fitCap\n      ? roomCap\n      : Math.max(220, Math.min(roomCap, 560, Math.round(visH * 0.72)));\n    menu.style.setProperty(\'--menu-max\', cap + \'px\');\n    /* Re-measure: --menu-max may have changed the height we are about to place. */\n    const sized = menu.getBoundingClientRect();\n    const mh = sized.height;\n\n    if (o.anchor && o.anchor.getBoundingClientRect) {\n      const a2 = o.anchor.getBoundingClientRect();\n      x = o.align === \'right\' ? a2.right - sized.width : a2.left;\n      y = openUp ? a2.top - mh - 4 : a2.bottom + 4;\n    }\n    if (x === undefined) x = (vw - sized.width) / 2;\n    if (y === undefined) y = (vh - mh) / 2;\n\n    if (x + sized.width > vw - pad) x = vw - sized.width - pad;\n    /*\n     * v10.4: CLAMP AGAINST WHAT IS ON SCREEN, NOT THE LAYOUT VIEWPORT.\n     *\n     * v10.1 taught the max-height to use visualViewport and then clamped the\n     * POSITION against vh anyway, so on a mobile browser whose toolbar is\n     * covering the bottom of the page a menu could still be placed with its\n     * last row underneath that toolbar. Same measurement for both now.\n     */\n    if (y + mh > visH - pad) y = Math.max(pad, visH - mh - pad);\n    x = Math.max(pad, x);\n    y = Math.max(pad, y);', block('menucap107.js').rstrip('\n'), 'menu placement'))

    report('menus: measured again once they are really laid out', once('''    menu.style.left = Math.round(x) + 'px';
    menu.style.top = Math.round(y) + 'px';
    menu.style.setProperty('--menu-origin', (y < (o.y || y) ? 'bottom' : 'top') + ' left');
    menu.style.visibility = '';''', '''    menu.style.left = Math.round(x) + 'px';
    menu.style.top = Math.round(y) + 'px';
    menu.style.setProperty('--menu-origin', (y < (o.y || y) ? 'bottom' : 'top') + ' left');
    menu.style.visibility = '';

    /*
     * v10.7: AND ONE LAST LOOK, WITH THE MENU REALLY LAID OUT.
     *
     * The height read a moment ago is the height at that instant, and it is
     * not always the final one - an icon that has just been inserted, a web
     * font that arrives, a row that grows by a line. Measured on a 1280x800
     * window: the same menu placed from a height of 593px and then painted
     * at 631px, which put its last row 20px BELOW the bottom of the screen.
     *
     * So the gap is enforced once more against the height it actually has,
     * and again on the next frame. It is idempotent - if nothing moved,
     * nothing is written.
     */
    const settle = function () {
      if (!menu.parentNode) return;
      const nowH = menu.offsetHeight;   /* layout, not the animating transform */
      const was = parseFloat(menu.style.top) || 0;
      let ny = was;
      if (nowH + 2 * GAP >= visH) ny = GAP;
      else if (ny + nowH > visH - GAP) ny = visH - nowH - GAP;
      if (ny < GAP) ny = GAP;
      if (Math.abs(ny - was) > 0.5) menu.style.top = Math.round(ny) + 'px';
    };
    settle();
    try { requestAnimationFrame(settle); } catch (err) { setTimeout(settle, 16); }''', 'menu settle'))

    report('read-along: the index survives a re-render', once("  function buildReadIndex() {\n    readNodes = []; readText = ''; readFrom = 0; chunkSpan = null;\n    if (!showReadable()) return false;\n    const pane = readPane();\n    if (!pane) return false;\n", block('readindex107.js').rstrip('\n'), 'read index'))

    report('read-along: marks are remembered so they can be repainted', once('    chunkSpan.at = i;\n    const s = chunkSpan.sentences[i];\n    setHl(HL_LINE, rangeFor(s.start, s.end));', '    chunkSpan.at = i;\n    const s = chunkSpan.sentences[i];\n    lastLine = s;      /* v10.7: remembered, so a re-render can put it back */\n    setHl(HL_LINE, rangeFor(s.start, s.end));', 'sentence mark'))

    report('read-along: and the word mark too', once('    const w = chunkSpan.words[idx];\n    if (w) setHl(HL_WORD, rangeFor(w.start, w.end));', '    const w = chunkSpan.words[idx];\n    if (w) { lastWord = w; setHl(HL_WORD, rangeFor(w.start, w.end)); }', 'word mark'))

    report('read-along: a new chunk starts with no word marked', once('    setHl(HL_WORD, null);\n    markSentence(0);', '    lastWord = null;\n    setHl(HL_WORD, null);\n    markSentence(0);', 'chunk start'))

    report('read-along: every range is built against live nodes', once('  function rangeFor(start, end) {\n    if (!(end > start) || !readNodes.length) return null;', '  function rangeFor(start, end) {\n    /* v10.7: the pane may have been rebuilt since the index was walked. */\n    if (!(end > start)) return null;\n    if (!ensureIndex()) return null;\n    if (!readNodes.length) return null;', 'rangeFor'))

    report('read-along: a mark can be drawn where it cannot be highlighted', once('  function setHl(name, range) {\n    if (!canHighlight()) return;\n    try {\n      if (!range) { CSS.highlights.delete(name); return; }\n      CSS.highlights.set(name, new Highlight(range));\n    } catch (err) { /* the engine refused; reading still works */ }\n  }\n\n', block('sethl107.js').rstrip('\n'), 'setHl'))

    report('read-along: the chunk is marked even without the API', once('''  /** Find this chunk in the pane, mark the sentence, and bring it into view. */
  function markReadingChunk(piece) {
    if (!canHighlight()) return;
    if (!readNodes.length && !buildReadIndex()) return;''', '''  /** Find this chunk in the pane, mark the sentence, and bring it into view. */
  function markReadingChunk(piece) {
    /* v10.7: no canHighlight() gate. Where the API is missing the mark is
       drawn instead, and a gate here would have stopped it before it began -
       which is why the drawn fallback showed nothing on its first outing. */
    if (!readNodes.length && !buildReadIndex()) return;''', 'markReadingChunk gate'))

    report('read-along: and the word too', once('''  function markReadingWord(piece, charIndex) {
    if (!canHighlight() || !chunkSpan || !chunkSpan.words.length) return;''', '''  function markReadingWord(piece, charIndex) {
    if (!chunkSpan || !chunkSpan.words.length) return;''', 'markReadingWord gate'))

    report('read-along: stopping clears both kinds of mark', once("  function clearReading() {\n    if (canHighlight()) {\n      try { CSS.highlights.delete(HL_LINE); CSS.highlights.delete(HL_WORD); } catch (err) {}\n    }\n    try {\n      Array.prototype.forEach.call(document.querySelectorAll('.prose.is-reading'),\n        function (e) { e.classList.remove('is-reading'); });\n    } catch (err) {}\n    readNodes = []; readText = ''; readFrom = 0; chunkSpan = null;\n  }\n", block('clearreading107.js').rstrip('\n'), 'clearReading'))

    report('read aloud: a full stop is not read twice', once(
        """      .replace(/\\n{2,}/g, '.\\n')""",
        """      /*
       * v10.7: a blank line becomes a full stop only where there was not one
       * already. "First paragraph ends here." followed by a blank line was
       * turning into "here.." - measured on every note in the app since the
       * feature shipped. Inaudible, but it is also what the read-along probe
       * has to bridge, and one fewer difference between the two sides is one
       * fewer way for the mark to miss.
       */
      .replace(/([.!?\\u2026\\u3002\\uff01\\uff1f\\u0964\\u0965]["'\\u2019\\u201d)\\]]*)[ \\t]*\\n{2,}/g, '$1\\n')
      .replace(/\\n{2,}/g, '.\\n')""", 'paragraph breaks'))

    report('read aloud: a table is content, not noise', once(
        """      .replace(/^\\s*\\|.*\\|\\s*$/gm, ' ')                        // tables read as noise""",
        """      /*
       * v10.7: A TABLE IS CONTENT, NOT NOISE.
       *
       * Every table row used to be deleted outright, so a note that is
       * mostly a table was read as silence and a note that is ONLY a table
       * answered "Nothing to read." - measured, and reported as a dead end.
       * Cells become a short list and the row becomes a sentence, which is
       * how a person reads a table out loud. The alignment row is the one
       * line that really does carry nothing.
       *
       * The closing pipe is optional because this renderer accepts a table
       * without one - checked - and a rule that did not would have read
       * "vertical bar a vertical bar b" for a table on screen.
       */
      .replace(/^[ \\t]*\\|[ \\t:|-]*\\|?[ \\t]*(?:\\r?\\n|$)/gm, '')  // |---|---|, newline and all
      .replace(/^[ \\t]*\\|(.*?)\\|?[ \\t]*$/gm, function (_, row) {
        const cells = row.split('|').map(function (c) { return c.trim(); }).filter(Boolean);
        return cells.length ? cells.join(', ') + '.' : ' ';
      })""", 'tables read aloud'))

    report('selection bar: the strip fills the bar', once('  max-width: min(620px, calc(100vw - 190px));', '  max-width: min(620px, calc(100vw - 190px));   /* v10.7: overridden inside .sel-dock */', 'sel-scroll max-width'))

    report('guest: the notifications share one column', exactly("    if (root) root.appendChild(bar);\n    requestAnimationFrame(function () { bar.classList.add('is-in'); });", "    guestStack().appendChild(bar);\n    requestAnimationFrame(function () { bar.classList.add('is-in'); });", 2, 'guest bars'))

    report('guest: and so does the promotion', once("      document.body.appendChild(bar);\n      requestAnimationFrame(function () { bar.classList.add('is-in'); });", "      guestStack().appendChild(bar);\n      requestAnimationFrame(function () { bar.classList.add('is-in'); });", 'guest cta'))

    report('guest: the column itself', once('  function countdownText(ms) {', "  /*\n   * v10.7: ONE COLUMN FOR EVERY BOTTOM NOTIFICATION.\n   *\n   * The update bar, the saved-copy notice and the promotion were three\n   * fixed elements pinned to almost the same bottom coordinate, so on a\n   * phone they landed on top of one another and only the highest z-index\n   * was readable. They go in here instead, newest at the bottom, and the\n   * stylesheet gives the column its width and its gaps.\n   */\n  function guestStack() {\n    let stack = document.getElementById('nd-guest-stack');\n    if (!stack) {\n      stack = el('div#nd-guest-stack');\n      (root || document.body).appendChild(stack);\n    }\n    return stack;\n  }\n\n  function countdownText(ms) {", 'guest stack'))

    report('the stylesheet', once('\n</style>\n</head>', '\n' + block('css107.css') + '\n</style>\n</head>', 'v10.7 css'))

    report('the build label and date', once(
        "  N.versionName = 'v10.6';\n  N.built = '2026-09-02';",
        "  N.versionName = 'v10.7';\n  N.built = '2026-09-05';", 'build label'))

    report('version 10.7.0', once("  N.version = '10.6.0';", "  N.version = '10.7.0';", 'version'))


    print('')
    print(BANNER)
    if state['fail']:
        print(' %d edit(s) FAILED - nothing was written.' % state['fail'])
        print(' Your file is untouched. Send me the file and I will re-anchor.')
        print(BANNER)
        return 1

    out = state['src']
    print(' %d edits applied cleanly.' % state['edits'])
    print(' %d -> %d bytes (+%d)' % (len(src.encode('utf-8')),
                                     len(out.encode('utf-8')),
                                     len(out.encode('utf-8')) - len(src.encode('utf-8'))))
    print('')

    if dry:
        print(' --dry-run: %s was NOT modified.' % path)
        print(BANNER)
        return 0

    backup = path + '.bak'
    with io.open(backup, 'w', encoding='utf-8', newline='') as fh:
        fh.write(src)
    with io.open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    print(' wrote  %s' % path)
    print(' backup %s' % backup)
    print(BANNER)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
