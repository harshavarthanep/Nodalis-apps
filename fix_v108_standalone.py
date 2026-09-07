#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nodalis v10.8.0 - a canvas attached to anything, the save that only looked
                  like it had failed, and one duplicate setting fewer.

Run it on your index.html in a Codespace:

    python3 fix_v108_standalone.py index.html --dry-run     # report only
    python3 fix_v108_standalone.py index.html               # apply

One file, standard library only. It refuses to run twice, refuses a file
that is not at v10.7.0, and writes NOTHING unless every single edit anchors
cleanly - so a failed run leaves your file exactly as it was.
"""

import io
import os
import sys

MARKER = 'v10.8: A NEWER SAVE MUST NOT MAKE AN OLDER ONE LOOK LIKE A FAILURE'
REQUIRES = 'v10.7: THE INDEX HAS TO SURVIVE THE PREVIEW BEING RE-RENDERED'
REQUIRES_NAME = 'v10.7.0'
PREV_PATCHER = 'fix_v107_standalone.py'

_BLOCKS = {}

_BLOCKS['savefix.js'] = r'''  /*
   * v10.8: A NEWER SAVE MUST NOT MAKE AN OLDER ONE LOOK LIKE A FAILURE.
   *
   * This is the "sometimes the app crashes" report, and it is a false alarm
   * that ends in a red permanent toast telling you to copy your text
   * somewhere safe.
   *
   * doSave() captures the text, awaits the write, then verifies that the
   * store holds exactly that text. Two saves for the same note can be in
   * flight at once - typing schedules one on a 400ms debounce, and switching
   * notes calls flushSave() which starts another immediately - and the
   * newer one usually lands first because it has less to do. The older one
   * then wakes up, compares its text against the NEWER text, and throws.
   *
   * Measured, switching between two notes while typing on a phone:
   *
   *   NDSAVE MISMATCH wanted 18 got 19  tail(wanted)="...note\nyy"
   *                                     tail(got)   ="...note\nyyy"
   *   [editor] save failed (attempt 1) Error: The browser did not keep the change.
   *   ... attempts 2, 3, 4, 5 ...
   *   then: "Could not save - your text is still on screen, copy it
   *          somewhere safe."
   *
   * Nothing failed. The verification was comparing against a moving target.
   *
   * So each save now takes a ticket for its note. If a newer ticket exists
   * by the time this one returns, this save has been superseded: it is a
   * success that no longer speaks for the note, so it neither throws nor
   * touches the dirty flag. The check still catches what it was written for -
   * a private window that accepts the write and drops the row - because in
   * that case there IS no newer ticket and the content really is missing.
   */
  let saveTicket = 0;
  const latestTicket = new Map();

  async function doSave() {
    if (!currentId || !dirty) return;
    const note = current();
    if (!note) { setDirty(false); return; }
    const id = currentId;
    const text = ta.value;
    const ticket = ++saveTicket;
    latestTicket.set(id, ticket);
    saving = true;
    setDirty(true);
    try {
      await N.store.updateNoteContent(id, text);

      const superseded = latestTicket.get(id) !== ticket;
      if (!superseded) {
        // Verify rather than assume. A private window can accept the promise
        // and drop the row; if the note in the store does not carry what we
        // just typed, the save did not happen.
        const back = N.store.getNote(id);
        if (!back || back.content !== text) {
          throw new Error('The browser did not keep the change.');
        }
      }

      saving = false;
      saveAttempt = 0;
      clearTimeout(retryTimer);
      retryTimer = null;
      N.toast.dismiss('save-fail');
      /*
       * v8 BUG FIX: THE EDITOR COULD GET STUCK ON "UNSAVED" FOR EVER.
       *
       * `dirty` is one flag for the editor, not one per note. A save can only
       * speak for the note it belongs to: if we have navigated away, this
       * result says nothing about what is on screen now.
       *
       * v10.8: but the pip still has to be REPAINTED, because setDirty() is
       * what draws it and the last thing it drew said "Saving…". Leaving that
       * word on screen for the rest of the session is how a finished save
       * came to look like a stuck one.
       */
      if (currentId === id) setDirty(ta.value !== text);
      else setDirty(dirty);
      if (!superseded) updateWordCount(N.store.getNote(id));
'''

_BLOCKS['cvlink.js'] = r'''/* ===== js/features/cvlink.js ===== */
/* =========================================================================
 * Nodalis — features/cvlink.js
 *
 * A canvas, attached to the thing it belongs to.
 *
 * A board is where you think something through; the note, the sticky or the
 * task is what came out of it. Until now the two could only be joined from
 * the canvas side, by embedding a note in a board. This is the other
 * direction: anything can carry a link to a canvas, show it as a chip with
 * an eye, and open a real picture of that board in a dialog without leaving
 * what you are doing.
 *
 * The preview is not a mock-up of the canvas. It is the SAME renderer the
 * PNG export uses, so a sticky, a shape, a photograph, a connector and a
 * pen stroke all appear exactly as they do on the board, and the preview can
 * never drift from the thing it is previewing.
 *
 * WHERE THE LINK LIVES, per surface, and why:
 *
 *   note      note.properties.canvas   - frontmatter, so it travels with the
 *                                        file to disk and to GitHub and back
 *   sticky    sticky.canvasId          - a record field; stickies are not files
 *   task      task.canvasId            - on a standalone task's record; a task
 *                                        written inside a note inherits its
 *                                        note's canvas, because the alternative
 *                                        is inventing markdown syntax for a
 *                                        single checkbox line
 * ========================================================================= */
(function (N) {
  'use strict';

  const U = N.util;
  const el = U.el;

  /* --------------------------------------------------------------- model */

  function all() {
    try { return Array.from(N.store.state.canvases.values()); }
    catch (err) { return []; }
  }

  function get(id) {
    if (!id) return null;
    try { return N.store.state.canvases.get(id) || null; }
    catch (err) { return null; }
  }

  function titleOf(id) {
    const c = get(id);
    return c ? (c.title || 'Untitled canvas') : null;
  }

  /** What a canvas holds, in words, for the chip's tooltip and the dialog. */
  function summary(id) {
    const c = get(id);
    if (!c) return '';
    const items = Array.isArray(c.items) ? c.items.length : 0;
    const ink = Array.isArray(c.strokes) ? c.strokes.length : 0;
    const bits = [];
    if (items) bits.push(U.pluralize(items, 'item'));
    if (ink) bits.push(U.pluralize(ink, 'stroke'));
    return bits.length ? bits.join(' · ') : 'Empty board';
  }

  /* --------------------------------------------------------------- pick */

  /**
   * Choose a canvas. Offers to make one when there are none, because
   * "link a canvas" with nothing to link is a dead end.
   */
  async function pick(opts) {
    const o = opts || {};
    const list = all().sort(function (a, b) { return (b.updatedAt || 0) - (a.updatedAt || 0); });
    if (!list.length) {
      const make = await N.modal.confirm({
        title: 'No canvases yet',
        message: 'A canvas is an infinite board for cards, stickies, shapes and ink.',
        detail: 'Make one now and link it to this?',
        confirmLabel: 'Make a canvas',
      });
      if (!make) return null;
      if (!N.canvas || !N.canvas.createCanvas) return null;
      const made = await N.canvas.createCanvas('Board for ' + (o.forName || 'this'));
      return made ? made.id : null;
    }
    const options = list.slice(0, 60).map(function (c) {
      return {
        value: c.id, icon: 'canvas',
        label: c.title || 'Untitled canvas',
        description: summary(c.id),
      };
    });
    options.push({ value: '__new__', icon: 'plus', label: 'Make a new canvas…',
      description: 'And link it to this' });
    const chosen = await N.modal.choose({
      title: o.title || 'Link which canvas?',
      message: o.message || null,
      options: options,
    });
    if (chosen === '__new__') {
      if (!N.canvas || !N.canvas.createCanvas) return null;
      const made = await N.canvas.createCanvas('Board for ' + (o.forName || 'this'));
      return made ? made.id : null;
    }
    return chosen || null;
  }

  /* ------------------------------------------------------------ preview */

  /**
   * The dialog. One picture, the board's name, what is on it, and two ways
   * out: close, or open the board for real.
   */
  async function preview(id, opts) {
    const o = opts || {};
    const canvas = get(id);
    if (!canvas) {
      N.toast.warn('That canvas no longer exists.', { ms: 3000 });
      return null;
    }
    let shot = null;
    const api = N.modal.open({
      title: canvas.title || 'Untitled canvas',
      size: 'lg',
      dismissValue: null,
      showClose: true,
      render: function () {
        const box = el('div.cvprev');
        const meta = el('div.cvprev-meta');
        meta.appendChild(N.icons.node('canvas', { size: 14 }));
        meta.appendChild(el('span', null, summary(id)));
        if (o.fromLabel) {
          meta.appendChild(el('span.cvprev-dot', null, '·'));
          meta.appendChild(el('span.dim', null, 'linked from ' + U.truncate(o.fromLabel, 40)));
        }
        box.appendChild(meta);

        const stage = el('div.cvprev-stage');
        stage.appendChild(el('div.cvprev-loading', null, 'Drawing the board…'));
        box.appendChild(stage);

        /* The same renderer the PNG export uses. */
        const draw = function () {
          if (!N.exporter || !N.exporter.canvasImage) {
            U.clear(stage);
            stage.appendChild(el('p.dim.small', null, 'This build cannot draw a preview.'));
            return;
          }
          N.exporter.canvasImage(canvas, 1600).then(function (url) {
            U.clear(stage);
            if (!url) {
              const empty = el('div.cvprev-empty');
              empty.appendChild(N.icons.node('canvas', { size: 38 }));
              empty.appendChild(el('div', null, 'Nothing on this board yet.'));
              stage.appendChild(empty);
              return;
            }
            shot = url;
            const img = el('img.cvprev-img', { alt: 'Preview of ' + (canvas.title || 'the canvas'), src: url });
            stage.appendChild(img);
          }).catch(function () {
            U.clear(stage);
            stage.appendChild(el('p.dim.small', null, 'The preview could not be drawn.'));
          });
        };
        /* After the dialog is laid out, so the image is measured against a
           stage that has its real width. */
        setTimeout(draw, 30);
        return box;
      },
      footer: function (a) {
        const out = [];
        const openBtn = el('button.btn.btn-primary', { type: 'button' }, 'Open this canvas');
        openBtn.addEventListener('click', function () {
          a.close('open');
          if (N.canvas && N.canvas.open) N.canvas.open(id);
          else N.app.setView('canvas');
          if (N.haptics) N.haptics.buzz('select');
        });
        out.push(el('button.btn', { type: 'button', onclick: function () { a.close(null); } }, 'Close'));
        if (shot !== undefined) {
          const copy = el('button.btn', { type: 'button', title: 'Put the picture on the clipboard' }, 'Copy picture');
          copy.addEventListener('click', async function () {
            try {
              if (!shot) throw new Error('nothing drawn');
              const blob = await (await fetch(shot)).blob();
              if (navigator.clipboard && window.ClipboardItem) {
                await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
                N.toast.success('Picture copied', { ms: 1600 });
              } else throw new Error('no clipboard');
            } catch (err) {
              N.toast.info('This browser will not let a page copy an image. Use Export as PNG on the board.', { ms: 4000 });
            }
          });
          out.push(copy);
        }
        out.push(openBtn);
        return out;
      },
    });
    return api.promise;
  }

  /* --------------------------------------------------------------- chip */

  /**
   * The chip: the board's name and an eye. Small, quiet, and the same shape
   * wherever it appears - a note's header, a sticky's head, a task's meta row.
   */
  function chip(id, opts) {
    const o = opts || {};
    const title = titleOf(id);
    const node = el('span.cvchip' + (o.compact ? '.is-compact' : ''), {
      dataset: { canvas: id || '' },
    });
    if (!title) {
      /* A link to a board that has been deleted says so rather than
         pretending, and offers the only useful action left. */
      node.classList.add('is-missing');
      node.appendChild(N.icons.node('canvas', { size: 12 }));
      node.appendChild(el('span.cvchip-name', null, 'Canvas deleted'));
      if (o.onClear) {
        const x = el('button.cvchip-btn', { type: 'button', title: 'Remove this link' });
        x.appendChild(N.icons.node('close', { size: 11 }));
        x.addEventListener('click', function (e) { e.stopPropagation(); o.onClear(); });
        node.appendChild(x);
      }
      return node;
    }
    node.appendChild(N.icons.node('canvas', { size: 12 }));
    if (!o.compact) node.appendChild(el('span.cvchip-name', { title: title }, U.truncate(title, 22)));
    const eye = el('button.cvchip-btn.cvchip-eye', {
      type: 'button',
      title: 'Preview "' + title + '"',
      'aria-label': 'Preview the linked canvas',
    });
    eye.appendChild(N.icons.node('eye', { size: 13 }));
    eye.addEventListener('click', function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (N.haptics) N.haptics.buzz('tap');
      preview(id, { fromLabel: o.fromLabel });
    });
    node.appendChild(eye);
    node.title = title + ' · ' + summary(id);
    return node;
  }

  /* --------------------------------------------------------- menu items */

  /**
   * The three rows every surface needs, built from a getter and a setter so
   * notes, stickies and tasks all behave identically.
   */
  function menuItems(o) {
    const current = o.get();
    const items = [];
    if (current && titleOf(current)) {
      items.push({
        label: 'Preview the canvas', icon: 'eye',
        description: titleOf(current),
        onClick: function () { preview(current, { fromLabel: o.name }); },
      });
      items.push({
        label: 'Open the canvas', icon: 'canvas',
        onClick: function () { if (N.canvas && N.canvas.open) N.canvas.open(current); },
      });
      items.push({
        label: 'Link a different canvas…', icon: 'refresh',
        onClick: async function () {
          const id = await pick({ forName: o.name, title: 'Link which canvas?' });
          if (id) { await o.set(id); N.toast.success('Canvas linked', { ms: 1600 }); }
        },
      });
      items.push({
        label: 'Unlink the canvas', icon: 'unlink',
        onClick: async function () {
          await o.set(null);
          N.toast.success('Canvas unlinked', { ms: 1600 });
        },
      });
    } else {
      items.push({
        label: current ? 'Link a canvas (the old one is gone)…' : 'Link a canvas…',
        icon: 'canvas',
        description: 'Preview it from here with the eye',
        onClick: async function () {
          const id = await pick({ forName: o.name });
          if (id) { await o.set(id); N.toast.success('Canvas linked', { ms: 1600 }); }
        },
      });
    }
    return items;
  }

  /* ------------------------------------------------------- the surfaces */

  /* --- notes: frontmatter, so it survives a round trip to disk --- */
  function ofNote(note) {
    if (!note || !note.properties) return null;
    const v = note.properties.canvas;
    return v ? String(v) : null;
  }
  async function setOnNote(note, id) {
    if (!note) return;
    await N.store.updateNoteProperties(note.id, { canvas: id || undefined });
    N.bus.emit('cvlink:changed', { kind: 'note', id: note.id });
  }

  /* --- stickies --- */
  function ofSticky(sticky) { return sticky && sticky.canvasId ? String(sticky.canvasId) : null; }
  async function setOnSticky(sticky, id) {
    if (!sticky) return;
    const rec = N.store.state.stickies.get(sticky.id) || sticky;
    if (id) rec.canvasId = id; else delete rec.canvasId;
    await N.store.saveRecord('stickies', rec);
    N.bus.emit('cvlink:changed', { kind: 'sticky', id: sticky.id });
    N.bus.emit('stickies:changed');
  }

  /* --- tasks: a standalone task carries its own; one written in a note
         inherits the note's, which is the honest answer for a checkbox --- */
  function ofTask(task) {
    if (!task) return null;
    if (task.source === 'note') {
      const note = N.store.getNote(task.noteId);
      return ofNote(note);
    }
    const rec = N.store.state.tasks.get(task.id);
    return rec && rec.canvasId ? String(rec.canvasId) : null;
  }
  function taskLinkIsInherited(task) {
    return !!(task && task.source === 'note');
  }
  async function setOnTask(task, id) {
    if (!task) return;
    if (task.source === 'note') {
      const note = N.store.getNote(task.noteId);
      await setOnNote(note, id);
      return;
    }
    const rec = N.store.state.tasks.get(task.id);
    if (!rec) return;
    if (id) rec.canvasId = id; else delete rec.canvasId;
    await N.store.saveRecord('tasks', rec);
    N.bus.emit('cvlink:changed', { kind: 'task', id: task.id });
    N.bus.emit('vault:changed');
  }

  /* ------------------------------------------------------------ commands */

  function init() {
    N.commands.registerMany([
      {
        id: 'cvlink.note',
        title: 'Link a canvas to this note',
        group: 'Canvas',
        icon: 'canvas',
        when: function () { return !!N.store.state.activeNoteId; },
        run: async function () {
          const note = N.store.getNote(N.store.state.activeNoteId);
          if (!note) { N.toast.info('Open a note first.', { ms: 2000 }); return; }
          const id = await pick({ forName: N.store.noteTitle(note) });
          if (id) { await setOnNote(note, id); N.toast.success('Canvas linked', { ms: 1600 }); }
        },
      },
      {
        id: 'cvlink.preview',
        title: "Preview this note's canvas",
        group: 'Canvas',
        icon: 'eye',
        when: function () {
          const note = N.store.getNote(N.store.state.activeNoteId);
          return !!ofNote(note);
        },
        run: function () {
          const note = N.store.getNote(N.store.state.activeNoteId);
          const id = ofNote(note);
          if (id) preview(id, { fromLabel: N.store.noteTitle(note) });
          else N.toast.info('This note has no canvas linked.', { ms: 2200 });
        },
      },
    ]);
  }

  N.cvlink = {
    init: init,
    pick: pick, preview: preview, chip: chip, menuItems: menuItems,
    titleOf: titleOf, summary: summary, get: get,
    ofNote: ofNote, setOnNote: setOnNote,
    ofSticky: ofSticky, setOnSticky: setOnSticky,
    ofTask: ofTask, setOnTask: setOnTask, taskLinkIsInherited: taskLinkIsInherited,
  };
})(window.NODALIS = window.NODALIS || {});

'''

_BLOCKS['css108.css'] = r'''
/* ===== v10.8: a canvas, attached to the thing it belongs to ===== */

.cvchip {
  display: inline-flex; align-items: center; gap: 4px;
  flex: none;
  max-width: 100%;
  min-width: 0;
  height: 24px;
  padding: 0 3px 0 7px;
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  color: var(--text-2);
  font-size: var(--text-xs);
  line-height: 1;
  vertical-align: middle;
}
.cvchip svg { color: var(--accent); flex: none; }
.cvchip-name {
  min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.cvchip.is-compact { padding: 0 3px; }
.cvchip.is-missing {
  background: color-mix(in srgb, #e0245e 9%, transparent);
  border-color: color-mix(in srgb, #e0245e 34%, var(--border));
}
.cvchip.is-missing svg { color: #e0245e; }
.cvchip-btn {
  flex: none;
  width: 20px; height: 20px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 0; background: transparent; padding: 0;
  border-radius: var(--r-pill);
  color: var(--text-2);
  cursor: pointer;
}
.cvchip-btn:hover, .cvchip-btn:focus-visible {
  background: var(--bg-0);
  color: var(--text-0);
}
.cvchip-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.cvchip-eye svg { color: inherit; }
/* A finger needs more than 20px, and the chip grows to match rather than the
   button spilling out of it. */
@media (hover: none) {
  .cvchip { height: 30px; padding-right: 2px; }
  .cvchip-btn { width: 28px; height: 28px; }
}

/* --- the preview dialog --- */
.cvprev { display: flex; flex-direction: column; gap: var(--sp-4); min-width: 0; }
.cvprev-meta {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  font-size: var(--text-xs); color: var(--text-2);
}
.cvprev-dot { color: var(--text-3); }
.cvprev-stage {
  display: flex; align-items: center; justify-content: center;
  min-height: 220px;
  max-height: min(62vh, 620px);
  padding: var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-md, 12px);
  background: var(--bg-1);
  overflow: auto;
  overscroll-behavior: contain;
}
.cvprev-img {
  display: block;
  max-width: 100%;
  max-height: min(58vh, 580px);
  width: auto; height: auto;
  border-radius: var(--r-sm, 8px);
  box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.14));
  background: #fff;
}
.cvprev-loading, .cvprev-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: var(--sp-3);
  color: var(--text-3);
  font-size: var(--text-sm);
  text-align: center;
  padding: var(--sp-6) var(--sp-4);
}
.cvprev-empty svg { color: var(--text-3); }
@media (max-width: 520px) {
  .cvprev-stage { min-height: 160px; padding: var(--sp-2, 6px); }
}

/* The note header carries the chip beside the share state, and has to be
   allowed to give it room rather than squeezing the title to nothing. */
.editor-actions .cvchip { margin-right: 2px; }
@media (max-width: 620px) {
  .editor-actions .cvchip .cvchip-name { display: none; }
}
/* On a sticky the chip sits in the head, which is 22px of vertical space. */
.sticky-head .cvchip { height: 19px; padding: 0 2px 0 5px; font-size: 10px; }
.sticky-head .cvchip .cvchip-name { display: none; }
.sticky-head .cvchip-btn { width: 17px; height: 17px; }
/* And in a task's meta row, in line with the due date and the tags. */
.task-meta .cvchip { height: 22px; }

/* ===== v10.8: two touch targets that missed the 30px floor =====
 *
 * Measured on a 390x844 phone, in the audit that clicks every button in
 * every view: the task checkbox came out 28px tall and the calendar's legend
 * chips 18px. Everything else in the app already clears it.
 */
@media (hover: none), (max-width: 620px) {
  .task-check { width: 34px; height: 34px; }
  .cal-legend-chip { min-height: 32px; padding-top: 4px; padding-bottom: 4px; }
}
'''

_BLOCKS['canvascss.css'] = r'''
/* ===== v10.8: a board can point at a sticky and at a task ===== */
.canvas-item[data-kind='stickyref'] .canvas-item-body,
.canvas-item[data-kind='taskref'] .canvas-item-body {
  cursor: default;
  font-size: 12px;
  line-height: 1.45;
  overflow: auto;
  overscroll-behavior: contain;
}
.canvas-ref-body { display: flex; flex-direction: column; gap: 3px; }
.canvas-ref-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.canvas-ref-todo { display: flex; align-items: flex-start; gap: 6px; }
.canvas-ref-todo.is-done { color: var(--text-3); text-decoration: line-through; }
.canvas-ref-box {
  flex: none;
  width: 13px; height: 13px; margin-top: 2px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid currentColor;
  border-radius: 3px;
  font-size: 10px; line-height: 1;
  opacity: 0.75;
}
.canvas-ref-where {
  margin-top: 4px;
  font-size: 10px;
  color: var(--text-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* v10.8: the sticky a canvas card just sent you to says "here I am". */
.sticky-note.is-found {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  animation: nd-found calc(1200ms * var(--motion-scale)) var(--ease-out) 1;
}
@keyframes nd-found {
  0%   { box-shadow: 0 0 0 0 color-mix(in srgb, var(--accent) 60%, transparent); }
  60%  { box-shadow: 0 0 0 12px color-mix(in srgb, var(--accent) 0%, transparent); }
  100% { box-shadow: none; }
}
'''

_BLOCKS['exporttail.js'] = r'''    return canvas;
  }

  /**
   * Draw the board, then hand it over as a download. Split out in v10.8 so
   * the preview dialog can use the same renderer: a preview drawn by a second
   * implementation is a preview that eventually disagrees with the board.
   */
  async function exportCanvasPng(doc) {
    // A board with nothing but ink on it is not empty. The old guard refused to
    // export it, which looked like a broken button.
    if (!doc || (!doc.items.length && !(doc.strokes || []).length)) { N.toast.info('This canvas is empty.'); return; }
    const canvas = await renderCanvas(doc);
    if (!canvas) { N.toast.error('Could not render the canvas.'); return; }
    canvas.toBlob(function (blob) {
      if (!blob) { N.toast.error('Could not render the canvas.'); return; }
      U.downloadBlob(blob, U.safeFileName(doc.title, 'canvas') + '.png');
      N.toast.success('Canvas exported as PNG', { ms: 1800 });
    }, 'image/png');
  }

  /**
   * The same picture as a data URL, scaled to fit `maxPx` on its long side.
   * Returns null for a board with nothing on it, so the caller can say so in
   * its own words rather than being handed a blank rectangle.
   */
  async function canvasImage(doc, maxPx) {
    const full = await renderCanvas(doc);
    if (!full) return null;
    const limit = Math.max(240, Math.min(4000, maxPx || 1400));
    const long = Math.max(full.width, full.height);
    if (long <= limit) {
      try { return full.toDataURL('image/png'); } catch (err) { return null; }
    }
    const k = limit / long;
    const small = document.createElement('canvas');
    small.width = Math.max(1, Math.round(full.width * k));
    small.height = Math.max(1, Math.round(full.height * k));
    try {
      const ctx = small.getContext('2d');
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(full, 0, 0, small.width, small.height);
      return small.toDataURL('image/png');
    } catch (err) { return null; }
  }
'''

_BLOCKS['canvasref.js'] = r'''    } else if (kind === 'noteref') {
      const noteId = await pickNote();
      if (!noteId) return;
      base.noteId = noteId;
      base.w = 240; base.h = 170;
    } else if (kind === 'stickyref') {
      /*
       * v10.8: A BOARD CAN POINT AT A STICKY AND AT A TASK, NOT ONLY A NOTE.
       *
       * Embedding a note has been here since the canvas shipped, and the two
       * other things this app keeps loose thoughts in could not be reached
       * from a board at all. Same shape as noteref: the board holds only an
       * id, the card shows the live text, and double-clicking goes to the
       * real thing. Nothing is copied, so nothing can go stale.
       */
      const stickyId = await pickSticky();
      if (!stickyId) return;
      base.stickyId = stickyId;
      base.w = 200; base.h = 160;
    } else if (kind === 'taskref') {
      const taskId = await pickTask();
      if (!taskId) return;
      base.taskId = taskId;
      base.w = 240; base.h = 120;
'''

_BLOCKS['canvaspick.js'] = r'''  /* v10.8: the pickers for the two new reference kinds. */

  function stickyLabel(sticky) {
    if (!sticky) return 'Sticky';
    if (sticky.kind === 'todo') {
      const items = Array.isArray(sticky.items) ? sticky.items : [];
      const first = items.filter(function (i) { return i && i.text; })[0];
      const done = items.filter(function (i) { return i && i.done; }).length;
      return (first ? String(first.text) : 'Checklist') + (items.length ? '  ' + done + '/' + items.length : '');
    }
    if (sticky.kind === 'draw') return 'Sketch';
    const t = String(sticky.text || '').replace(/\s+/g, ' ').trim();
    return t || 'Empty sticky';
  }

  function pickSticky() {
    let list = [];
    try { list = Array.from(N.store.state.stickies.values()); } catch (err) { list = []; }
    const options = list
      .sort(function (a, b) { return (b.updatedAt || b.createdAt || 0) - (a.updatedAt || a.createdAt || 0); })
      .slice(0, 60)
      .map(function (s) {
        return { value: s.id, icon: s.kind === 'todo' ? 'list-check' : (s.kind === 'draw' ? 'pen' : 'sticky'),
          label: U.truncate(stickyLabel(s), 46),
          description: s.kind === 'todo' ? 'Checklist' : (s.kind === 'draw' ? 'Sketch' : 'Sticky note') };
      });
    if (!options.length) {
      N.toast.info('Add a sticky on the Sticky wall first, then you can put it here.', { ms: 3600 });
      return Promise.resolve(null);
    }
    return N.modal.choose({ title: 'Which sticky?', options: options });
  }

  function allTasksForPicker() {
    const out = [];
    try {
      N.store.state.tasks.forEach(function (t) {
        out.push({ id: t.id, text: t.text, done: !!t.done, where: 'Task list', source: 'standalone' });
      });
    } catch (err) { /* no tasks store yet */ }
    try {
      N.store.allNotes().forEach(function (note) {
        if (!note.taskCounts || !note.taskCounts.total) return;
        N.serialize.extractTasks(note.content).forEach(function (t) {
          out.push({ id: note.id + ':' + t.line, text: t.text, done: !!t.done,
            where: N.store.noteTitle(note), source: 'note' });
        });
      });
    } catch (err) { /* a note that will not parse simply offers no tasks */ }
    return out;
  }

  function pickTask() {
    const list = allTasksForPicker();
    const options = list.slice(0, 80).map(function (t) {
      return { value: t.id, icon: t.done ? 'check' : 'list-check',
        label: U.truncate(String(t.text || '(empty task)').replace(/\s+/g, ' ').trim(), 46),
        description: (t.done ? 'Done · ' : '') + t.where };
    });
    if (!options.length) {
      N.toast.info('Write a task first - a "- [ ] " line in a note, or one in the Tasks view.', { ms: 3800 });
      return Promise.resolve(null);
    }
    return N.modal.choose({ title: 'Which task?', options: options });
  }

  /** The live text behind a taskref, wherever that task lives. */
  function taskById(id) {
    if (!id) return null;
    const str = String(id);
    const cut = str.lastIndexOf(':');
    if (cut > 0) {
      const noteId = str.slice(0, cut);
      const line = Number(str.slice(cut + 1));
      const note = N.store.getNote(noteId);
      if (!note) return null;
      let found = null;
      try {
        N.serialize.extractTasks(note.content).forEach(function (t) {
          if (t.line === line) found = { text: t.text, done: !!t.done, where: N.store.noteTitle(note), noteId: noteId };
        });
      } catch (err) { return null; }
      return found;
    }
    let rec = null;
    try { rec = N.store.state.tasks.get(str); } catch (err) { rec = null; }
    if (!rec) return null;
    return { text: rec.text, done: !!rec.done, where: 'Task list', noteId: null };
  }

  function stickyById(id) {
    if (!id) return null;
    try { return N.store.state.stickies.get(String(id)) || null; } catch (err) { return null; }
  }

'''

_BLOCKS['canvasbody.js'] = r'''    const body = el('div.canvas-item-body');
    if (item.kind === 'noteref') {
      const note = N.store.getNote(item.noteId);
      if (note) {
        body.innerHTML = N.markdown.render(U.truncate(note.content, 900), { depth: 2, headingAnchors: false });
        body.classList.add('prose');
        body.style.fontSize = '12px';
        body.addEventListener('dblclick', function () { N.app.openNote(item.noteId); });
      } else {
        body.appendChild(el('span.dim.small', null, 'This note no longer exists.'));
      }
    } else if (item.kind === 'stickyref') {
      /* v10.8: the sticky's own text and colour, read-only, live. */
      const sticky = stickyById(item.stickyId);
      if (sticky) {
        node.style.background = sticky.color || STICKY_COLORS[0];
        body.classList.add('canvas-ref-body');
        if (sticky.kind === 'todo') {
          const items = Array.isArray(sticky.items) ? sticky.items : [];
          if (!items.length) body.appendChild(el('span.dim.small', null, 'Empty checklist'));
          items.slice(0, 8).forEach(function (t) {
            const row = el('div.canvas-ref-todo' + (t && t.done ? '.is-done' : ''));
            row.appendChild(el('span.canvas-ref-box', null, t && t.done ? '✓' : ''));
            row.appendChild(el('span', null, String((t && t.text) || '')));
            body.appendChild(row);
          });
          if (items.length > 8) body.appendChild(el('span.dim.small', null, '+ ' + (items.length - 8) + ' more'));
        } else if (sticky.kind === 'draw') {
          body.appendChild(el('span.dim.small', null, 'Sketch — open the wall to see it'));
        } else {
          body.appendChild(el('div.canvas-ref-text', null, String(sticky.text || '')));
        }
        body.addEventListener('dblclick', function () {
          N.app.setView('sticky');
          if (N.sticky && N.sticky.focusOn) N.sticky.focusOn(sticky.id);
        });
      } else {
        body.appendChild(el('span.dim.small', null, 'This sticky no longer exists.'));
      }
    } else if (item.kind === 'taskref') {
      /* v10.8: the task, ticked or not, wherever it lives. */
      const task = taskById(item.taskId);
      if (task) {
        body.classList.add('canvas-ref-body');
        const row = el('div.canvas-ref-todo' + (task.done ? '.is-done' : ''));
        row.appendChild(el('span.canvas-ref-box', null, task.done ? '✓' : ''));
        row.appendChild(el('span', null, String(task.text || '(empty task)')));
        body.appendChild(row);
        body.appendChild(el('div.canvas-ref-where', null, task.where));
        body.addEventListener('dblclick', function () {
          if (task.noteId) N.app.openNote(task.noteId);
          else N.app.setView('tasks');
        });
      } else {
        body.appendChild(el('span.dim.small', null, 'This task no longer exists.'));
      }
    } else if (item.kind === 'image') {
'''

_BLOCKS['canvaslabel.js'] = r'''  function labelFor(kind) {
    return { card: 'Card', sticky: 'Sticky', frame: 'Frame', noteref: 'Note',
      stickyref: 'Sticky note', taskref: 'Task', text: 'Text', image: 'Image' }[kind] || kind;
  }
  function iconFor(kind) {
    return { card: 'note', sticky: 'sticky', frame: 'layout', noteref: 'link',
      stickyref: 'sticky', taskref: 'list-check', text: 'type', image: 'image' }[kind] || 'box';
  }
'''

_BLOCKS['stickyfocus.js'] = r'''  /**
   * v10.8: bring one sticky into view and select it.
   *
   * A canvas card that references a sticky needs somewhere to go when it is
   * double-clicked, and "the sticky wall, somewhere" is not an answer on a
   * wall you have panned away from.
   */
  function focusOn(id) {
    const sticky = N.store.state.stickies.get(id);
    if (!sticky) { N.toast.info('That sticky is gone.', { ms: 2200 }); return false; }
    selectedId = id;
    const land = function () {
      if (!wrap) { render(); }
      const box = wrap ? wrap.getBoundingClientRect() : null;
      if (box && box.width > 20) {
        view.k = Math.min(MAX_ZOOM, Math.max(0.6, view.k || 1));
        view.x = box.width / 2 - (sticky.x + (sticky.w || 200) / 2) * view.k;
        view.y = box.height / 2 - (sticky.y + (sticky.h || 200) / 2) * view.k;
        applyView();
      }
      paintSelection();
      const node = board ? board.querySelector('[data-sticky="' + id + '"]') : null;
      if (node) {
        node.classList.add('is-found');
        setTimeout(function () { node.classList.remove('is-found'); }, 1400);
      }
    };
    if (N.store.state.activeView !== 'sticky') {
      N.app.setView('sticky');
      setTimeout(function () { render(); requestAnimationFrame(land); }, 220);
    } else {
      requestAnimationFrame(land);
    }
    return true;
  }

'''


def block(name):
    return _BLOCKS[name]


BANNER = '=' * 80


def main(argv):
    if len(argv) < 2:
        print('usage: python3 fix_v108_standalone.py <index.html> [--dry-run]')
        return 2
    path = argv[1]
    dry = '--dry-run' in argv[2:]

    if not os.path.isfile(path):
        print('ERROR: no such file: %s' % path)
        return 1

    with io.open(path, encoding='utf-8') as fh:
        src = fh.read()

    print(BANNER)
    print(' Nodalis v10.8.0 - canvas links with a preview, the false save')
    print('                   failure, the duplicate setting, touch targets')
    print(BANNER)
    print(' file: %s  (%d bytes)' % (path, len(src.encode('utf-8'))))
    print('')

    if MARKER in src:
        print('ERROR: v10.8.0 is already installed in this file.')
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

    def report(label, ok):
        if ok:
            state['edits'] += 1
            print('   %-58s ok' % label)
        else:
            print('   %-58s FAILED' % label)
            state['fail'] += 1

    report('save: a newer save no longer fails the older one', once("  async function doSave() {\n    if (!currentId || !dirty) return;\n    const note = current();\n    if (!note) { setDirty(false); return; }\n    const id = currentId;\n    const text = ta.value;\n    saving = true;\n    setDirty(true);\n    try {\n      await N.store.updateNoteContent(id, text);\n\n      // Verify rather than assume. A private window can accept the promise and\n      // drop the row; if the note in the store does not carry what we just\n      // typed, the save did not happen and we must keep the dirty flag set.\n      const back = N.store.getNote(id);\n      if (!back || back.content !== text) {\n        throw new Error('The browser did not keep the change.');\n      }\n\n      saving = false;\n      saveAttempt = 0;\n      clearTimeout(retryTimer);\n      retryTimer = null;\n      N.toast.dismiss('save-fail');", block('savefix.js').rstrip('\n'), 'doSave'))

    report('save: and the note it no longer speaks for is left alone', once('      if (currentId === id) setDirty(ta.value !== text);\n      updateWordCount(N.store.getNote(id));\n    } catch (err) {', '    } catch (err) {', 'doSave tail'))

    report('canvas: the PNG renderer is reusable', once("  async function exportCanvasPng(doc) {\n    // A board with nothing but ink on it is not empty. The old guard refused to\n    // export it, which looked like a broken button.\n    if (!doc || (!doc.items.length && !(doc.strokes || []).length)) { N.toast.info('This canvas is empty.'); return; }", '  /**\n   * v10.8: DRAW THE BOARD. Just draw it - no toast, no download.\n   *\n   * The preview dialog needs the same picture the PNG export produces, and\n   * the only way to be sure a preview never disagrees with the board is for\n   * both to come out of one renderer. This is that renderer; exportCanvasPng\n   * and canvasImage are two things done with its output.\n   */\n  async function renderCanvas(doc) {\n    if (!doc || (!doc.items.length && !(doc.strokes || []).length)) return null;', 'renderCanvas'))

    report('canvas: and a picture for the preview', once("    canvas.toBlob(function (blob) {\n      if (!blob) { N.toast.error('Could not render the canvas.'); return; }\n      U.downloadBlob(blob, U.safeFileName(doc.title, 'canvas') + '.png');\n      N.toast.success('Canvas exported as PNG', { ms: 1800 });\n    }, 'image/png');\n  }", block('exporttail.js').rstrip('\n'), 'canvasImage'))

    report('canvas: the picture is exported from the module', once('    exportDocx: exportDocx, exportImage: exportImage, exportCanvasPng: exportCanvasPng,', '    exportDocx: exportDocx, exportImage: exportImage, exportCanvasPng: exportCanvasPng,\n    renderCanvas: renderCanvas, canvasImage: canvasImage,', 'exporter exports'))

    report('the canvas-link module', once('/* ===== js/app.js ===== */', block('cvlink.js') + '/* ===== js/app.js ===== */', 'cvlink module'))

    report('and it starts with everything else', once("      ['tools', N.tools],\n    ];", "      ['tools', N.tools],\n      /* v10.8: after canvas, sticky and tasks - it offers a menu row to all\n         three and a preview of what canvas holds. */\n      ['cvlink', N.cvlink],\n    ];", 'cvlink init'))

    report('canvas: a board can embed a sticky or a task', once("    } else if (kind === 'noteref') {\n      const noteId = await pickNote();\n      if (!noteId) return;\n      base.noteId = noteId;\n      base.w = 240; base.h = 170;", block('canvasref.js').rstrip('\n'), 'canvas addItem'))

    report('canvas: the pickers for both', once('  function pickImageFile() {', block('canvaspick.js') + '  function pickImageFile() {', 'canvas pickers'))

    report('canvas: and they draw what they point at', once("    const body = el('div.canvas-item-body');\n    if (item.kind === 'noteref') {\n      const note = N.store.getNote(item.noteId);\n      if (note) {\n        body.innerHTML = N.markdown.render(U.truncate(note.content, 900), { depth: 2, headingAnchors: false });\n        body.classList.add('prose');\n        body.style.fontSize = '12px';\n        body.addEventListener('dblclick', function () { N.app.openNote(item.noteId); });\n      } else {\n        body.appendChild(el('span.dim.small', null, 'This note no longer exists.'));\n      }\n    } else if (item.kind === 'image') {", block('canvasbody.js').rstrip('\n'), 'canvas body'))

    report('canvas: named and iconed like the rest', once("  function labelFor(kind) {\n    return { card: 'Card', sticky: 'Sticky', frame: 'Frame', noteref: 'Note', text: 'Text', image: 'Image' }[kind] || kind;\n  }\n  function iconFor(kind) {\n    return { card: 'note', sticky: 'sticky', frame: 'layout', noteref: 'link', text: 'type', image: 'image' }[kind] || 'box';\n  }", block('canvaslabel.js').rstrip('\n'), 'canvas labels'))

    report('canvas: on the right-click menu', once("      { label: 'Embed a note', icon: 'link', onClick: function () { addItem('noteref', world); } },", "      { label: 'Embed a note', icon: 'link', onClick: function () { addItem('noteref', world); } },\n      { label: 'Embed a sticky note', icon: 'sticky', onClick: function () { addItem('stickyref', world); } },\n      { label: 'Embed a task', icon: 'list-check', onClick: function () { addItem('taskref', world); } },", 'canvas context menu'))

    report('canvas: and on the toolbar', once('            <button class="icon-btn" data-add="noteref" title="Embed a note (N)"><span data-icon="link" data-icon-size="18"></span></button>', '            <button class="icon-btn" data-add="noteref" title="Embed a note (N)"><span data-icon="link" data-icon-size="18"></span></button>\n            <button class="icon-btn" data-add="stickyref" title="Embed a sticky note"><span data-icon="sticky" data-icon-size="18"></span></button>\n            <button class="icon-btn" data-add="taskref" title="Embed a task"><span data-icon="list-check" data-icon-size="18"></span></button>', 'canvas toolbar'))

    report('sticky: one sticky can be brought into view', once('  function buildSticky(sticky) {', block('stickyfocus.js') + '  function buildSticky(sticky) {', 'sticky focusOn'))

    report('sticky: exported so a canvas card can reach it', once('  N.sticky = {\n    init: init, render: render, create: createSticky, COLORS: COLORS,', '  N.sticky = {\n    init: init, render: render, create: createSticky, COLORS: COLORS,\n    focusOn: focusOn,', 'sticky exports'))

    report('sticky: the chip, with its eye, in the head', once("    const menuBtn = el('button.icon-btn.icon-btn-sm', { type: 'button', title: 'Sticky actions' });\n    menuBtn.appendChild(N.icons.node('more', { size: 13 }));\n    menuBtn.addEventListener('click', function (e) { e.stopPropagation(); openMenu(sticky, e.currentTarget); });\n    head.appendChild(menuBtn);", "    /* v10.8: a linked canvas, previewable from here. */\n    if (N.cvlink && N.cvlink.ofSticky(sticky)) {\n      head.appendChild(N.cvlink.chip(N.cvlink.ofSticky(sticky), {\n        compact: true,\n        fromLabel: 'a sticky',\n        onClear: function () { N.cvlink.setOnSticky(sticky, null); },\n      }));\n    }\n    const menuBtn = el('button.icon-btn.icon-btn-sm', { type: 'button', title: 'Sticky actions' });\n    menuBtn.appendChild(N.icons.node('more', { size: 13 }));\n    menuBtn.addEventListener('click', function (e) { e.stopPropagation(); openMenu(sticky, e.currentTarget); });\n    head.appendChild(menuBtn);", 'sticky chip'))

    report('tasks: the chip in the meta row', once("    (task.tags || []).slice(0, 3).forEach(function (t) { meta.appendChild(el('span', null, '#' + t)); });", "    (task.tags || []).slice(0, 3).forEach(function (t) { meta.appendChild(el('span', null, '#' + t)); });\n    /* v10.8: the canvas this task was thought through on. A task written in a\n       note shows its note's board, because a checkbox line has nowhere of its\n       own to keep one. */\n    if (N.cvlink) {\n      const cv = N.cvlink.ofTask(task);\n      if (cv) {\n        meta.appendChild(N.cvlink.chip(cv, {\n          fromLabel: task.source === 'note' ? task.noteTitle : 'a task',\n          onClear: function () { N.cvlink.setOnTask(task, null); render(); },\n        }));\n      }\n    }", 'task chip'))

    report('tasks: and the rows on its menu', once(
        """      { label: 'Move in the matrix…', icon: 'matrix', onClick: function () { setQuadrant(task); } },
    ];
    if (N.remind && N.remind.setFor) {""",
        """      { label: 'Move in the matrix…', icon: 'matrix', onClick: function () { setQuadrant(task); } },
    ];
    /* v10.8: link, preview, open or unlink the canvas behind this task. A
       task written inside a note shares its note's board, and the rows say
       so rather than pretending the checkbox has one of its own. */
    if (N.cvlink) {
      items.push({ separator: true });
      N.cvlink.menuItems({
        name: String(task.text || 'this task'),
        get: function () { return N.cvlink.ofTask(task); },
        set: async function (id) { await N.cvlink.setOnTask(task, id); render(); },
      }).forEach(function (row) {
        if (N.cvlink.taskLinkIsInherited(task)) {
          row.description = (row.description ? row.description + ' · ' : '') + 'kept on the note';
        }
        items.push(row);
      });
    }
    if (N.remind && N.remind.setFor) {""", 'task menu'))

    report('notes: link a canvas from the note menu', once("      { label: 'Insert a template here…', icon: 'file-text',\n        onClick: function () { if (N.templates) N.templates.pick('insert'); } },", "      { label: 'Insert a template here…', icon: 'file-text',\n        onClick: function () { if (N.templates) N.templates.pick('insert'); } },\n      /* v10.8: the board this note came out of, previewable without leaving\n         the note. Stored in frontmatter, so it goes to disk with the file. */\n      ].concat(N.cvlink ? N.cvlink.menuItems({\n        name: N.store.noteTitle(note),\n        get: function () { return N.cvlink.ofNote(note); },\n        set: async function (id) { await N.cvlink.setOnNote(note, id); renderCanvasChip(); },\n      }) : []).concat([", 'note menu'))

    report('notes: the menu list closes where it now ends', once(
        """      { label: 'Delete note', icon: 'trash', danger: true, onClick: function () { N.commands.run('note.delete'); } },
    ], { anchor: anchor, align: 'right', title: N.store.noteTitle(note), allowSheet: true });""",
        """      { label: 'Delete note', icon: 'trash', danger: true, onClick: function () { N.commands.run('note.delete'); } },
    ]), { anchor: anchor, align: 'right', title: N.store.noteTitle(note), allowSheet: true });""",
        'note menu tail'))

    report('notes: the chip, with its eye, in the header', once("  function renderTitle() {\n    const note = current();\n    titleInput.value = note ? N.store.noteTitle(note) : '';\n  }", "  function renderTitle() {\n    const note = current();\n    titleInput.value = note ? N.store.noteTitle(note) : '';\n    renderCanvasChip();\n  }\n\n  /**\n   * v10.8: the linked canvas, shown beside the share state.\n   *\n   * Rebuilt rather than updated: the chip is three elements and a title, and\n   * a rebuild cannot leave a stale name behind after the board is renamed.\n   */\n  function renderCanvasChip() {\n    const actions = document.querySelector('.editor-actions');\n    if (!actions) return;\n    const old = actions.querySelector('.cvchip');\n    if (old) old.remove();\n    if (!N.cvlink) return;\n    const note = current();\n    /*\n     * Rendered whenever the note CARRIES a link, even when the board\n     * behind it has been deleted - the chip then says \\'Canvas deleted\\'\n     * and offers to remove it. A note quietly holding a dead reference is\n     * worse than a note that tells you about it.\n     */\n    const id = note ? N.cvlink.ofNote(note) : null;\n    if (!id) return;\n    const chip = N.cvlink.chip(id, {\n      fromLabel: N.store.noteTitle(note),\n      onClear: function () { N.cvlink.setOnNote(note, null).then(renderCanvasChip); },\n    });\n    actions.insertBefore(chip, actions.firstChild);\n  }", 'note chip'))

    report('notes: and it appears the moment the link is made', once(
        "    bus.on('note:active', function (note) { loadNote(note); });",
        "    bus.on('note:active', function (note) { loadNote(note); });\n"
        "    /* v10.8: the chip has to appear when the link is made, from wherever\n"
        "       it was made - the note menu, the command palette, or a task that\n"
        "       shares this note's board. One listener beats a call at every call\n"
        "       site, and it also catches a board being renamed or deleted. */\n"
        "    bus.on('cvlink:changed', function () { renderCanvasChip(); });\n"
        "    bus.on('vault:changed', U.debounce(function () { renderCanvasChip(); }, 120));",
        'note chip refresh'))

    report('settings: one Typewriter scrolling, not two', once("    wrap.appendChild(row('Typewriter scrolling', 'Keeps the line you are writing near the middle of the screen.', toggle('typewriterMode')));\n", '    /*\n     * v10.8: THE SECOND TYPEWRITER SWITCH IS GONE.\n     *\n     * There were two rows called "Typewriter scrolling" in this one section.\n     * The one that used to be here wrote `typewriterMode`, and NOTHING IN THE\n     * APP EVER READ THAT KEY - checked across the whole build. It was a\n     * switch wired to nothing, sitting directly above the real one.\n     *\n     * The real one is under Writing modes: it writes `typewriter`, it is what\n     * scrollToCaret() reads, and it is the one with "Caret sits" underneath\n     * it. Anyone who had the dead switch on is carried over to it once, in\n     * store.js, so a setting that appeared to be on becomes one that is.\n     */\n', 'settings row'))

    report('store: the dead key goes, and takes a duplicate with it', once('    showLineNumbers: false,\n    typewriterMode: false,\n    focusMode: false,\n', '    showLineNumbers: false,\n    /*\n     * v10.8: `typewriterMode` was here and nothing read it - see settings.js.\n     * `focusMode` was here too, declared a SECOND time: it is already up in\n     * the appearance block above, and a repeated key in one object literal is\n     * a bug waiting for the two values to disagree.\n     */\n', 'store defaults'))

    report('store: and anyone who had it on keeps it on', once("""    if (!s.keymap || typeof s.keymap !== 'object') s.keymap = {};
    return s;
  }""", """    if (!s.keymap || typeof s.keymap !== 'object') s.keymap = {};
    /*
     * v10.8: ONE-TIME CARRY-OVER FOR THE DEAD TYPEWRITER SWITCH.
     *
     * Settings has had two rows called "Typewriter scrolling" in one section.
     * The one that has now gone wrote `typewriterMode`, which nothing in the
     * app ever read - so a vault can hold `typewriterMode: true` from a
     * switch that looked like it did something and did not.
     *
     * Turning the real setting on for those people is the difference between
     * "they removed my setting" and "it finally works". Then the dead key is
     * dropped, so this runs once and never again.
     */
    if (s.typewriterMode !== undefined) {
      if (s.typewriterMode === true && s.typewriter !== true) s.typewriter = true;
      delete s.typewriterMode;
    }
    return s;
  }""", 'settings migration'))

    report('read aloud: the pane that actually scrolls is the one scrolled', once('      const r = rangeFor(s.start, Math.min(s.end, s.start + 48));\n      const pane = readPane();\n      if (r && pane) {\n        const rr = r.getBoundingClientRect(), pr = pane.getBoundingClientRect();\n        if (rr.top < pr.top + 32 || rr.bottom > pr.bottom - 32) {\n          pane.scrollTop += (rr.top - pr.top) - pane.clientHeight * 0.34;\n        }\n      }', "      const r = rangeFor(s.start, Math.min(s.end, s.start + 48));\n      /*\n       * v10.8: SCROLL THE THING THAT SCROLLS.\n       *\n       * readPane() returns the .prose element, and in split mode .prose does\n       * not scroll - #split-preview around it does. Adding to .prose's\n       * scrollTop was therefore a no-op, and a sentence being read below the\n       * fold simply stayed below the fold.\n       */\n      const pane = readPane();\n      let box = pane;\n      while (box && box !== document.body) {\n        const cs = getComputedStyle(box);\n        if (/auto|scroll/.test(cs.overflowY) && box.scrollHeight > box.clientHeight + 2) break;\n        box = box.parentElement;\n      }\n      if (!box || box === document.body) box = pane;\n      if (r && box) {\n        const rr = r.getBoundingClientRect(), pr = box.getBoundingClientRect();\n        if (rr.top < pr.top + 32 || rr.bottom > pr.bottom - 32) {\n          box.scrollTop += (rr.top - pr.top) - box.clientHeight * 0.34;\n        }\n      }", 'read scroller'))

    report('the stylesheet', once('\n</style>\n</head>', '\n' + block('css108.css') + block('canvascss.css') + '\n</style>\n</head>', 'css'))

    report('the build label and date', once("  N.versionName = 'v10.7';\n  N.built = '2026-09-05';", "  N.versionName = 'v10.8';\n  N.built = '2026-09-07';", 'build label'))

    report('version 10.8.0', once("  N.version = '10.7.0';", "  N.version = '10.8.0';", 'version'))


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
