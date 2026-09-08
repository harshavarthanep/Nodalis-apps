#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nodalis v10.9.0 - a live canvas in a small window, embedded in a note as many
                  times as you like, and ink that stays visible when the
                  lights change.

Run it on your index.html in a Codespace:

    python3 fix_v109_standalone.py index.html --dry-run     # report only
    python3 fix_v109_standalone.py index.html               # apply

One file, standard library only. It refuses to run twice, refuses a file
that is not at v10.8.0, and writes NOTHING unless every single edit anchors
cleanly - so a failed run leaves your file exactly as it was.
"""

import io
import os
import sys

MARKER = 'v10.9: INK THAT STAYS VISIBLE WHEN THE LIGHTS CHANGE'
REQUIRES = 'v10.8: A NEWER SAVE MUST NOT MAKE AN OLDER ONE LOOK LIKE A FAILURE'
REQUIRES_NAME = 'v10.8.0'
PREV_PATCHER = 'fix_v108_standalone.py'

_BLOCKS = {}

_BLOCKS['inkutil.js'] = r'''  /*
   * v10.9: INK THAT STAYS VISIBLE WHEN THE LIGHTS CHANGE.
   *
   * A freehand stroke stores an absolute colour, and canvas.js used to take
   * that colour from the THEME at the moment of drawing:
   *
   *     color: inkColor || currentAccent()      // = --text-0, right now
   *
   * So a line drawn in dark mode is stored as near-white, and the moment you
   * switch to a light theme it is white ink on cream paper - gone. Drawn in
   * light mode it is stored near-black and disappears on a dark theme. Both
   * directions were reported, and both are in the screenshots.
   *
   * Two halves to the fix. canvas.js stops baking the theme into new strokes
   * (see `color: null` there). This is the other half, and it is what rescues
   * drawings that ALREADY EXIST: at paint time, a stroke whose stored colour
   * cannot be seen against the paper it is on is flipped in lightness and
   * kept. Hue and saturation survive, so a deliberate red stays red; only
   * ink that would be invisible moves.
   *
   * It runs on the canvas, in the preview, and in the PNG export - which
   * matters, because the export paints on WHITE, so white ink drawn on a
   * dark theme would otherwise export as an empty picture.
   */
  const INK_MIN_CONTRAST = 2.4;

  /** #rrggbb, rgb(), or a CSS colour word, resolved to #rrggbb. */
  function toHex(color, fallback) {
    const raw = String(color === null || color === undefined ? '' : color).trim();
    if (!raw) return fallback || '#000000';
    if (/^#[0-9a-f]{3}$|^#[0-9a-f]{6}$/i.test(raw)) {
      const c = hexToRgb(raw);
      return rgbToHex(c.r, c.g, c.b);
    }
    const m = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(raw);
    if (m) return rgbToHex(Number(m[1]), Number(m[2]), Number(m[3]));
    /* Anything else - a colour keyword, a colour function - is resolved by
       the browser once, off screen, rather than parsed by hand. */
    try {
      const probe = document.createElement('span');
      probe.style.cssText = 'position:absolute;left:-9999px;top:0;color:' + raw;
      document.body.appendChild(probe);
      const got = getComputedStyle(probe).color;
      probe.remove();
      const p = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)/i.exec(got || '');
      if (p) return rgbToHex(Number(p[1]), Number(p[2]), Number(p[3]));
    } catch (err) { /* fall through to the fallback */ }
    return fallback || '#000000';
  }

  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let h = 0, s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0));
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h /= 6;
    }
    return { h: h, s: s, l: l };
  }

  function hslToHex(h, s, l) {
    const f = function (p, q, t) {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    if (s === 0) return rgbToHex(l * 255, l * 255, l * 255);
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    return rgbToHex(f(p, q, h + 1 / 3) * 255, f(p, q, h) * 255, f(p, q, h - 1 / 3) * 255);
  }

  /**
   * visibleInk(color, paper)
   *
   * The colour to actually draw with, so a stroke can be seen on `paper`.
   * `color` may be null or empty, which means "the pen with no colour of its
   * own" - that ink follows the paper and always has.
   */
  function visibleInk(color, paper) {
    const bg = toHex(paper || '#ffffff', '#ffffff');
    if (color === null || color === undefined || color === '' || color === 'currentColor') {
      return readableOn(bg);
    }
    const ink = toHex(color, readableOn(bg));
    if (contrastRatio(ink, bg) >= INK_MIN_CONTRAST) return ink;
    const c = hexToRgb(ink);
    const hsl = rgbToHsl(c.r, c.g, c.b);
    /* Flip the lightness and push it away from the middle, where nothing
       contrasts with anything. */
    let l = 1 - hsl.l;
    l = l > 0.5 ? Math.max(l, 0.66) : Math.min(l, 0.34);
    const flipped = hslToHex(hsl.h, hsl.s, l);
    if (contrastRatio(flipped, bg) >= INK_MIN_CONTRAST) return flipped;
    /* Grey on grey: black or white, whichever wins. */
    return readableOn(bg);
  }

  /** The paper a canvas is drawn on, as the theme currently has it. */
  function canvasPaper() {
    try {
      const probe = document.getElementById('canvas-wrap') || document.body;
      const bg = getComputedStyle(probe).backgroundColor;
      const hex = toHex(bg, '');
      if (hex && !/^rgba\(0, 0, 0, 0\)$/.test(bg)) return hex;
    } catch (err) { /* fall through */ }
    try { return toHex(getComputedStyle(document.body).backgroundColor, '#ffffff'); }
    catch (err) { return '#ffffff'; }
  }

'''

_BLOCKS['cvview.js'] = r'''/* ===== js/features/cvview.js ===== */
/* =========================================================================
 * Nodalis — features/cvview.js
 *
 * A live canvas, in a small window, that never saves anything.
 *
 * The v10.8 preview was a picture. Asked for, and fair: a picture cannot be
 * scrolled around, cannot be zoomed into, and cannot be nudged to see what is
 * behind something. This is the real board instead - the same items, the same
 * stickies, the same connectors and the same ink - pannable, zoomable, and
 * with elements you can drag out of the way.
 *
 * NOTHING IT DOES IS WRITTEN DOWN. mount() takes a DEEP CLONE of the canvas
 * record, and every drag, every zoom and every pan happens to the clone. There
 * is no save path out of this module at all - not a guarded one, not a
 * debounced one, none. That is the whole design: a preview you can push
 * around is only safe if pushing it around cannot reach the board.
 *
 * Used twice: inside the eye dialog, and inline in a note - where a note can
 * hold as many of them as it likes, each one resizable and alignable like an
 * image.
 * ========================================================================= */
(function (N) {
  'use strict';

  const U = N.util;
  const el = U.el;
  const SVGNS = 'http://www.w3.org/2000/svg';

  const MIN_K = 0.08, MAX_K = 3;
  const live = new Set();          /* every mounted view, so themes can repaint */

  /* ------------------------------------------------------------ the items */

  function itemLabel(item) {
    if (item.kind === 'noteref') {
      const note = N.store.getNote(item.noteId);
      return note ? N.store.noteTitle(note) : 'Missing note';
    }
    if (item.kind === 'stickyref') return 'Sticky note';
    if (item.kind === 'taskref') return 'Task';
    return item.title || ({ card: 'Card', sticky: 'Sticky', frame: 'Frame',
      text: 'Text', image: 'Image' }[item.kind] || item.kind);
  }

  function itemIcon(kind) {
    return { card: 'note', sticky: 'sticky', frame: 'layout', noteref: 'link',
      stickyref: 'sticky', taskref: 'list-check', text: 'type', image: 'image' }[kind] || 'box';
  }

  function refText(item) {
    if (item.kind === 'noteref') {
      const note = N.store.getNote(item.noteId);
      return note ? U.truncate(String(note.content || '').replace(/[#*_`>\-]/g, ' ').replace(/\s+/g, ' ').trim(), 260) : '';
    }
    if (item.kind === 'stickyref') {
      let s = null;
      try { s = N.store.state.stickies.get(item.stickyId); } catch (err) { s = null; }
      if (!s) return 'This sticky no longer exists.';
      if (s.kind === 'todo') {
        return (Array.isArray(s.items) ? s.items : []).slice(0, 8)
          .map(function (t) { return (t && t.done ? '✓ ' : '○ ') + String((t && t.text) || ''); }).join('\n');
      }
      if (s.kind === 'draw') return 'Sketch';
      return String(s.text || '');
    }
    if (item.kind === 'taskref') {
      const str = String(item.taskId || '');
      const cut = str.lastIndexOf(':');
      if (cut > 0) {
        const note = N.store.getNote(str.slice(0, cut));
        const line = Number(str.slice(cut + 1));
        let found = '';
        if (note) {
          try {
            N.serialize.extractTasks(note.content).forEach(function (t) {
              if (t.line === line) found = (t.done ? '✓ ' : '○ ') + t.text;
            });
          } catch (err) { found = ''; }
        }
        return found || 'This task no longer exists.';
      }
      let rec = null;
      try { rec = N.store.state.tasks.get(str); } catch (err) { rec = null; }
      return rec ? ((rec.done ? '✓ ' : '○ ') + rec.text) : 'This task no longer exists.';
    }
    return '';
  }

  function buildItem(item, state) {
    const node = el('div.canvas-item.cvv-item', {
      dataset: { kind: item.kind, shape: item.shape || '', cvvItem: item.id },
      style: {
        left: item.x + 'px', top: item.y + 'px',
        width: item.w + 'px', height: item.h + 'px',
        zIndex: String(item.z || 0),
      },
    });
    if (item.kind === 'sticky') node.style.background = item.color || '#ffe9a8';
    if (item.kind === 'shape') node.style.borderColor = item.color || 'var(--accent)';

    if (item.kind !== 'shape' && item.kind !== 'image') {
      const head = el('div.canvas-item-head');
      head.appendChild(N.icons.node(itemIcon(item.kind), { size: 13 }));
      head.appendChild(el('span.truncate', { style: { flex: '1' } }, itemLabel(item)));
      node.appendChild(head);
    }

    if (item.kind === 'image') {
      const img = el('img', { alt: '' });
      if (item.attachmentId) {
        N.db.get('attachments', item.attachmentId).then(function (row) {
          if (row && row.blob) {
            const url = URL.createObjectURL(row.blob);
            img.src = url;
            state.urls.push(url);
          }
        }).catch(function () { /* a missing image stays an empty frame */ });
      }
      node.appendChild(img);
    } else if (item.kind !== 'shape') {
      const body = el('div.canvas-item-body.cvv-body');
      const txt = (item.kind === 'noteref' || item.kind === 'stickyref' || item.kind === 'taskref')
        ? refText(item) : String(item.text || '');
      body.textContent = txt;
      node.appendChild(body);
    }
    return node;
  }

  /* -------------------------------------------------------------- the ink */

  function strokePath(points) {
    if (!points || !points.length) return '';
    let d = 'M' + points[0][0] + ' ' + points[0][1];
    for (let i = 1; i < points.length; i++) d += 'L' + points[i][0] + ' ' + points[i][1];
    return d;
  }

  function paintInk(state) {
    const svg = state.svg;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    let paper = '#ffffff';
    try { paper = getComputedStyle(state.stage).backgroundColor; } catch (err) { paper = '#ffffff'; }

    (state.doc.connections || []).forEach(function (conn) {
      const from = state.byId[conn.from], to = state.byId[conn.to];
      if (!from || !to) return;
      const line = document.createElementNS(SVGNS, 'line');
      line.setAttribute('x1', String(from.x + from.w / 2));
      line.setAttribute('y1', String(from.y + from.h / 2));
      line.setAttribute('x2', String(to.x + to.w / 2));
      line.setAttribute('y2', String(to.y + to.h / 2));
      line.setAttribute('stroke', U.visibleInk('#9a9a9a', paper));
      line.setAttribute('stroke-width', '1.6');
      svg.appendChild(line);
    });

    (state.doc.strokes || []).forEach(function (sk) {
      const path = document.createElementNS(SVGNS, 'path');
      path.setAttribute('d', strokePath(sk.points));
      path.setAttribute('fill', 'none');
      /* v10.9: the stroke is drawn in a colour that can be SEEN here, which
         is not always the colour it was stored with. */
      path.setAttribute('stroke', U.visibleInk(sk.color, paper));
      path.setAttribute('stroke-width', String(sk.width || 3));
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('stroke-linejoin', 'round');
      svg.appendChild(path);
    });
  }

  /* ----------------------------------------------------------- the window */

  function bounds(doc) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    (doc.items || []).forEach(function (i) {
      minX = Math.min(minX, i.x); minY = Math.min(minY, i.y);
      maxX = Math.max(maxX, i.x + i.w); maxY = Math.max(maxY, i.y + i.h);
    });
    (doc.strokes || []).forEach(function (s) {
      (s.points || []).forEach(function (p) {
        minX = Math.min(minX, p[0]); minY = Math.min(minY, p[1]);
        maxX = Math.max(maxX, p[0]); maxY = Math.max(maxY, p[1]);
      });
    });
    if (!isFinite(minX)) return null;
    return { minX: minX, minY: minY, maxX: maxX, maxY: maxY };
  }

  function apply(state) {
    state.layer.style.transform =
      'translate(' + state.view.x + 'px,' + state.view.y + 'px) scale(' + state.view.k + ')';
    if (state.zoomLabel) state.zoomLabel.textContent = Math.round(state.view.k * 100) + '%';
  }

  function fit(state) {
    const b = bounds(state.doc);
    const box = state.stage.getBoundingClientRect();
    if (!b || box.width < 10) { state.view = { x: 0, y: 0, k: 1 }; apply(state); return; }
    const pad = 24;
    const w = Math.max(1, b.maxX - b.minX), h = Math.max(1, b.maxY - b.minY);
    const k = U.clamp(Math.min((box.width - pad * 2) / w, (box.height - pad * 2) / h), MIN_K, 1.4);
    state.view.k = k;
    state.view.x = box.width / 2 - ((b.minX + b.maxX) / 2) * k;
    state.view.y = box.height / 2 - ((b.minY + b.maxY) / 2) * k;
    apply(state);
  }

  function zoomAt(state, factor, cx, cy) {
    const box = state.stage.getBoundingClientRect();
    const px = cx === undefined ? box.width / 2 : cx - box.left;
    const py = cy === undefined ? box.height / 2 : cy - box.top;
    const before = state.view.k;
    const after = U.clamp(before * factor, MIN_K, MAX_K);
    if (after === before) return;
    /* Keep the point under the cursor where it is. */
    state.view.x = px - (px - state.view.x) * (after / before);
    state.view.y = py - (py - state.view.y) * (after / before);
    state.view.k = after;
    apply(state);
  }

  function moved(state) {
    return state.moves > 0;
  }

  function markMoved(state) {
    state.moves++;
    if (state.resetBtn) state.resetBtn.disabled = false;
    if (state.badge) state.badge.classList.add('is-touched');
  }

  function reset(state) {
    state.doc = U.deepClone(state.source);
    state.byId = {};
    (state.doc.items || []).forEach(function (i) { state.byId[i.id] = i; });
    state.moves = 0;
    if (state.resetBtn) state.resetBtn.disabled = true;
    if (state.badge) state.badge.classList.remove('is-touched');
    draw(state);
    fit(state);
  }

  function draw(state) {
    const layer = state.layer;
    Array.prototype.slice.call(layer.children).forEach(function (c) {
      if (c !== state.svg) c.remove();
    });
    (state.doc.items || []).slice()
      .sort(function (a, b) { return (a.z || 0) - (b.z || 0); })
      .forEach(function (item) { layer.appendChild(buildItem(item, state)); });
    paintInk(state);
  }

  /* ------------------------------------------------------------- pointers */

  function wire(state) {
    const stage = state.stage;

    stage.addEventListener('pointerdown', function (e) {
      if (e.button !== 0 && e.pointerType === 'mouse') return;
      const itemNode = e.target.closest ? e.target.closest('[data-cvv-item]') : null;
      stage.setPointerCapture && stage.setPointerCapture(e.pointerId);
      if (itemNode && state.opts.movable !== false) {
        const item = state.byId[itemNode.dataset.cvvItem];
        if (!item) return;
        state.drag = { kind: 'item', item: item, node: itemNode,
          sx: e.clientX, sy: e.clientY, ox: item.x, oy: item.y };
        itemNode.classList.add('is-dragging');
      } else {
        state.drag = { kind: 'pan', sx: e.clientX, sy: e.clientY, ox: state.view.x, oy: state.view.y };
        stage.classList.add('is-panning');
      }
      e.preventDefault();
    });

    stage.addEventListener('pointermove', function (e) {
      const d = state.drag;
      if (!d) return;
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy;
      if (d.kind === 'pan') {
        state.view.x = d.ox + dx;
        state.view.y = d.oy + dy;
        apply(state);
      } else {
        d.item.x = Math.round(d.ox + dx / state.view.k);
        d.item.y = Math.round(d.oy + dy / state.view.k);
        d.node.style.left = d.item.x + 'px';
        d.node.style.top = d.item.y + 'px';
        paintInk(state);
        if (!d.counted && (Math.abs(dx) > 2 || Math.abs(dy) > 2)) { d.counted = true; markMoved(state); }
      }
    });

    const end = function () {
      if (state.drag && state.drag.node) state.drag.node.classList.remove('is-dragging');
      state.drag = null;
      stage.classList.remove('is-panning');
    };
    stage.addEventListener('pointerup', end);
    stage.addEventListener('pointercancel', end);
    stage.addEventListener('pointerleave', function () { if (state.drag && state.drag.kind === 'pan') end(); });

    stage.addEventListener('wheel', function (e) {
      /* Ctrl/⌘ + wheel is the browser's own page zoom; leave it alone. */
      if (e.ctrlKey || e.metaKey) return;
      e.preventDefault();
      zoomAt(state, e.deltaY < 0 ? 1.12 : 0.89, e.clientX, e.clientY);
    }, { passive: false });

    /* Two fingers: pinch to zoom, which is how every other board here works. */
    const points = new Map();
    let pinchFrom = null;
    stage.addEventListener('pointerdown', function (e) { points.set(e.pointerId, e); });
    stage.addEventListener('pointermove', function (e) {
      if (!points.has(e.pointerId)) return;
      points.set(e.pointerId, e);
      if (points.size !== 2) return;
      const two = Array.from(points.values());
      const dist = Math.hypot(two[0].clientX - two[1].clientX, two[0].clientY - two[1].clientY);
      if (pinchFrom === null) { pinchFrom = { dist: dist, k: state.view.k }; return; }
      if (pinchFrom.dist > 8) {
        state.drag = null;
        const want = U.clamp(pinchFrom.k * (dist / pinchFrom.dist), MIN_K, MAX_K);
        const box = stage.getBoundingClientRect();
        const cx = (two[0].clientX + two[1].clientX) / 2, cy = (two[0].clientY + two[1].clientY) / 2;
        const px = cx - box.left, py = cy - box.top;
        const ratio = want / state.view.k;
        state.view.x = px - (px - state.view.x) * ratio;
        state.view.y = py - (py - state.view.y) * ratio;
        state.view.k = want;
        apply(state);
      }
    });
    const drop = function (e) { points.delete(e.pointerId); if (points.size < 2) pinchFrom = null; };
    stage.addEventListener('pointerup', drop);
    stage.addEventListener('pointercancel', drop);
  }

  /* ---------------------------------------------------------------- mount */

  /**
   * mount(host, canvasId, opts) -> handle
   *
   * opts.movable   false to look but not nudge (default true)
   * opts.controls  false to leave out the zoom row (default true)
   * opts.onOpen    a function, and an "Open" button appears
   */
  function mount(host, canvasId, opts) {
    if (!host) return null;
    const o = opts || {};
    let source = null;
    try { source = N.store.state.canvases.get(canvasId) || null; } catch (err) { source = null; }
    U.clear(host);
    host.classList.add('cvv');

    if (!source) {
      host.appendChild(el('div.cvv-empty', null, 'That canvas no longer exists.'));
      return { destroy: function () { U.clear(host); }, id: canvasId, missing: true };
    }

    const state = {
      id: canvasId,
      source: source,
      doc: U.deepClone(source),
      byId: {},
      view: { x: 0, y: 0, k: 1 },
      urls: [],
      moves: 0,
      drag: null,
      opts: o,
      host: host,
    };
    (state.doc.items || []).forEach(function (i) { state.byId[i.id] = i; });

    const stage = el('div.cvv-stage');
    const layer = el('div.cvv-layer');
    const svg = document.createElementNS(SVGNS, 'svg');
    svg.setAttribute('class', 'cvv-svg');
    svg.setAttribute('overflow', 'visible');
    layer.appendChild(svg);
    stage.appendChild(layer);
    host.appendChild(stage);
    state.stage = stage;
    state.layer = layer;
    state.svg = svg;

    /* The promise, made in the corner where it cannot be missed. */
    const badge = el('div.cvv-badge', { title: 'Move and zoom all you like - none of it is written to the canvas' });
    badge.appendChild(N.icons.node('eye', { size: 12 }));
    badge.appendChild(el('span', null, 'Preview · not saved'));
    stage.appendChild(badge);
    state.badge = badge;

    if (o.controls !== false) {
      const bar = el('div.cvv-controls');
      const mk = function (icon, title, fn) {
        const b = el('button.icon-btn.icon-btn-sm', { type: 'button', title: title });
        b.appendChild(N.icons.node(icon, { size: 14 }));
        b.addEventListener('click', function (e) { e.stopPropagation(); e.preventDefault(); fn(); });
        return b;
      };
      bar.appendChild(mk('minus', 'Zoom out', function () { zoomAt(state, 0.83); }));
      const lvl = el('span.cvv-zoom', null, '100%');
      bar.appendChild(lvl);
      state.zoomLabel = lvl;
      bar.appendChild(mk('plus', 'Zoom in', function () { zoomAt(state, 1.2); }));
      bar.appendChild(mk('maximize', 'Fit the whole board', function () { fit(state); }));
      const resetBtn = mk('undo', 'Put everything back where it was', function () { reset(state); });
      resetBtn.disabled = true;
      bar.appendChild(resetBtn);
      state.resetBtn = resetBtn;
      if (typeof o.onOpen === 'function') {
        bar.appendChild(mk('external', 'Open this canvas', function () { o.onOpen(canvasId); }));
      }
      stage.appendChild(bar);
    }

    draw(state);
    wire(state);
    /* Fitted once the stage has a real width - a stage measured inside a
       dialog that has not been laid out yet is 0px wide, and everything
       would land in the corner. */
    requestAnimationFrame(function () { fit(state); });
    setTimeout(function () { fit(state); }, 120);

    const onResize = U.debounce(function () { if (!state.moves) fit(state); }, 180);
    window.addEventListener('resize', onResize);

    const handle = {
      id: canvasId,
      fit: function () { fit(state); },
      reset: function () { reset(state); },
      repaint: function () { paintInk(state); },
      moved: function () { return moved(state); },
      destroy: function () {
        window.removeEventListener('resize', onResize);
        state.urls.forEach(function (u) { try { URL.revokeObjectURL(u); } catch (err) {} });
        live.delete(handle);
        U.clear(host);
        host.classList.remove('cvv');
      },
    };
    live.add(handle);
    return handle;
  }

  /* A theme change moves the paper, so every open preview repaints its ink. */
  function init() {
    N.bus.on('settings:changed', function () {
      live.forEach(function (h) { try { h.repaint(); } catch (err) { /* gone */ } });
    });
    N.bus.on('theme:changed', function () {
      live.forEach(function (h) { try { h.repaint(); } catch (err) { /* gone */ } });
    });
  }

  N.cvview = { init: init, mount: mount, bounds: bounds };
})(window.NODALIS = window.NODALIS || {});

'''

_BLOCKS['mdembed.js'] = r'''  /**
   * v10.9: A CANVAS, EMBEDDED IN A NOTE, AS MANY AS YOU LIKE.
   *
   *     ![[canvas: Launch board]]
   *     ![[canvas: Launch board|left|240]]
   *     ![[canvas: Launch board|full|420]]
   *
   * The same `![[ ]]` shape the note embed already uses, so it is one thing
   * to remember rather than two. Everything after the name is layout:
   * alignment, then the height in pixels - which is what the resize handle
   * and the align buttons write back, so the FILE is where the layout lives
   * and a note carries its own appearance to any other machine.
   *
   * This only marks the spot. The editor hydrates it into a live board, and
   * a hydrated board is a preview: pan it, zoom it, push its cards around,
   * and none of it is written to the canvas.
   */
  const CV_ALIGN = { left: 1, center: 1, right: 1, full: 1 };

  function canvasByName(name) {
    const want = String(name || '').trim().toLowerCase();
    if (!want) return null;
    let found = null;
    try {
      N.store.state.canvases.forEach(function (c) {
        if (found) return;
        if (String(c.id) === String(name).trim()) found = c;
        else if (String(c.title || '').trim().toLowerCase() === want) found = c;
      });
    } catch (err) { return null; }
    return found;
  }

  function renderCanvasEmbed(name, optionText, raw) {
    const bits = String(optionText || '').split('|').map(function (s) { return s.trim(); }).filter(Boolean);
    let align = 'center', height = 320;
    bits.forEach(function (bit) {
      const low = bit.toLowerCase();
      if (CV_ALIGN[low]) align = low;
      else if (/^\d{2,4}$/.test(bit)) height = Math.max(140, Math.min(1200, Number(bit)));
    });
    const canvas = canvasByName(name);
    const attrs = ' data-cvembed="' + U.escapeAttr(name) + '"' +
      ' data-cvid="' + U.escapeAttr(canvas ? canvas.id : '') + '"' +
      ' data-align="' + align + '"' +
      ' data-h="' + height + '"' +
      ' data-raw="' + U.escapeAttr(raw || '') + '"';
    if (!canvas) {
      return '<div class="cvembed is-missing"' + attrs + '>' +
        '<div class="cvembed-head">' + N.icons.svg('canvas', { size: 14 }) +
        '<span class="embed-missing">' + esc(name) + ' — no canvas with that name</span></div></div>';
    }
    return '<div class="cvembed"' + attrs + ' style="--cvembed-h:' + height + 'px">' +
      '<div class="cvembed-head">' + N.icons.svg('canvas', { size: 14 }) +
      '<span class="cvembed-name">' + esc(canvas.title || 'Untitled canvas') + '</span>' +
      '<span class="cvembed-tools"></span></div>' +
      '<div class="cvembed-stage"></div>' +
      '<div class="cvembed-grip" title="Drag to resize"></div></div>';
  }

'''

_BLOCKS['hydrate.js'] = r'''  /* v10.9: every live canvas this preview has mounted, so they can be torn
     down before the next render rather than leaking a listener per keystroke. */
  let cvMounts = [];

  function dropCanvasEmbeds() {
    cvMounts.forEach(function (h) { try { h.destroy(); } catch (err) { /* already gone */ } });
    cvMounts = [];
  }

  /**
   * Rewrite one embed's source text in place.
   *
   * The file is where the layout lives, so an align click and a resize drag
   * both end here. The caret and the scroll position are put back, because
   * assigning to ta.value moves both and the note is very likely open in
   * front of someone.
   */
  function rewriteEmbedSource(oldRaw, newRaw) {
    if (!oldRaw || oldRaw === newRaw) return false;
    const at = ta.value.indexOf(oldRaw);
    if (at < 0) return false;
    const selStart = ta.selectionStart, selEnd = ta.selectionEnd, top = ta.scrollTop;
    ta.value = ta.value.slice(0, at) + newRaw + ta.value.slice(at + oldRaw.length);
    const shift = newRaw.length - oldRaw.length;
    try {
      ta.setSelectionRange(selStart > at ? Math.max(at, selStart + shift) : selStart,
        selEnd > at ? Math.max(at, selEnd + shift) : selEnd);
    } catch (err) { /* a caret we could not put back is not worth an error */ }
    ta.scrollTop = top;
    onInput();
    return true;
  }

  function embedRaw(name, align, height) {
    const bits = [String(name)];
    if (align && align !== 'center') bits.push(align);
    if (height && Number(height) !== 320) bits.push(String(Math.round(height)));
    else if (align && align !== 'center') bits.push(String(Math.round(height || 320)));
    return '![[canvas: ' + bits.join('|') + ']]';
  }

  /**
   * Turn every ![[canvas: …]] marker in the rendered preview into a live,
   * non-saving board with the controls a picture would have: align left,
   * centre, right or full width, and a grip to drag it taller or shorter.
   */
  function hydrateCanvasEmbeds(root) {
    if (!N.cvview) return;
    const hosts = U.$$('.cvembed', root);
    hosts.forEach(function (box) {
      const stage = box.querySelector('.cvembed-stage');
      const id = box.dataset.cvid;
      const name = box.dataset.cvembed || '';
      const raw = box.dataset.raw || '';
      let align = box.dataset.align || 'center';
      let height = Math.max(140, Math.min(1200, Number(box.dataset.h) || 320));
      box.classList.add('is-align-' + align);
      box.style.setProperty('--cvembed-h', height + 'px');
      if (!stage || !id) return;

      const handle = N.cvview.mount(stage, id, {
        movable: true,
        controls: true,
        onOpen: function (cid) { if (N.canvas && N.canvas.open) N.canvas.open(cid); },
      });
      if (handle) cvMounts.push(handle);

      /* --- the tools: alignment, and a way out to the real board --- */
      const tools = box.querySelector('.cvembed-tools');
      if (tools) {
        U.clear(tools);
        const setAlign = function (next) {
          if (next === align) return;
          const before = raw;
          align = next;
          ['left', 'center', 'right', 'full'].forEach(function (a) {
            box.classList.toggle('is-align-' + a, a === next);
          });
          box.dataset.align = next;
          rewriteEmbedSource(before, embedRaw(name, next, height));
        };
        [['align-left', 'left', 'Align left'], ['align-center', 'center', 'Centre'],
         ['align-right', 'right', 'Align right'], ['maximize', 'full', 'Full width']]
          .forEach(function (spec) {
            const b = el('button.cvembed-btn' + (align === spec[1] ? '.is-on' : ''),
              { type: 'button', title: spec[2] });
            b.appendChild(N.icons.node(spec[0], { size: 13 }));
            b.addEventListener('click', function (e) {
              e.preventDefault(); e.stopPropagation();
              setAlign(spec[1]);
            });
            tools.appendChild(b);
          });
        const open = el('button.cvembed-btn', { type: 'button', title: 'Open this canvas' });
        open.appendChild(N.icons.node('external', { size: 13 }));
        open.addEventListener('click', function (e) {
          e.preventDefault(); e.stopPropagation();
          if (N.canvas && N.canvas.open) N.canvas.open(id);
        });
        tools.appendChild(open);
      }

      /* --- the grip: drag it taller, and the note remembers --- */
      const grip = box.querySelector('.cvembed-grip');
      if (grip) {
        let from = null;
        grip.addEventListener('pointerdown', function (e) {
          from = { y: e.clientY, h: height, raw: raw };
          grip.setPointerCapture && grip.setPointerCapture(e.pointerId);
          box.classList.add('is-resizing');
          e.preventDefault(); e.stopPropagation();
        });
        grip.addEventListener('pointermove', function (e) {
          if (!from) return;
          height = Math.max(140, Math.min(1200, Math.round(from.h + (e.clientY - from.y))));
          box.style.setProperty('--cvembed-h', height + 'px');
          e.preventDefault();
        });
        const done = function () {
          if (!from) return;
          const before = from.raw;
          from = null;
          box.classList.remove('is-resizing');
          box.dataset.h = String(height);
          /* Written once, at the end of the gesture - not on every pixel. */
          rewriteEmbedSource(before, embedRaw(name, align, height));
        };
        grip.addEventListener('pointerup', done);
        grip.addEventListener('pointercancel', done);
      }
    });
  }

'''

_BLOCKS['icons.js'] = r'''    'align-center': 'M6 6.5h12M3.5 12h17M6 17.5h12',
    /* v10.9: alignment for an embedded canvas, the way a picture aligns. */
    'align-left': 'M3.5 6.5h13M3.5 12h17M3.5 17.5h13',
    'align-right': 'M7.5 6.5h13M3.5 12h17M7.5 17.5h13',
    'align-full': 'M3.5 6.5h17M3.5 12h17M3.5 17.5h17',
'''

_BLOCKS['css109.css'] = r'''
/* ===== v10.9: a live canvas in a small window, saving nothing ===== */

.cvv { display: block; width: 100%; min-width: 0; }
.cvv-stage {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 140px;
  overflow: hidden;
  border-radius: var(--r-md, 12px);
  background: var(--bg-canvas, var(--bg-1));
  background-image: radial-gradient(circle at 1px 1px,
    color-mix(in srgb, var(--text-0) 14%, transparent) 1px, transparent 0);
  background-size: 24px 24px;
  touch-action: none;
  cursor: grab;
  contain: paint;
}
.cvv-stage.is-panning { cursor: grabbing; }
.cvv-layer {
  position: absolute; left: 0; top: 0;
  width: 1px; height: 1px;          /* the transform does the work */
  transform-origin: 0 0;
  will-change: transform;
}
.cvv-svg { position: absolute; left: 0; top: 0; width: 1px; height: 1px; pointer-events: none; }
/* Inside a preview a card is a thing to look at and nudge, not to edit. */
.cvv-item { cursor: grab; }
.cvv-item.is-dragging { cursor: grabbing; }
.cvv-item .canvas-item-head { cursor: inherit; }
.cvv-body {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  user-select: none;
  cursor: inherit;
}
.cvv-empty {
  display: flex; align-items: center; justify-content: center;
  min-height: 140px;
  color: var(--text-3);
  font-size: var(--text-sm);
}
.cvv-badge {
  position: absolute; left: 8px; top: 8px;
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 8px;
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--bg-0) 88%, transparent);
  border: 1px solid var(--border);
  color: var(--text-3);
  font-size: 10.5px; line-height: 1;
  pointer-events: none;
  z-index: 4;
}
.cvv-badge svg { color: var(--text-3); }
.cvv-badge.is-touched {
  color: var(--accent);
  border-color: color-mix(in srgb, var(--accent) 45%, var(--border));
}
.cvv-badge.is-touched svg { color: var(--accent); }
.cvv-controls {
  position: absolute; right: 8px; bottom: 8px;
  display: flex; align-items: center; gap: 2px;
  padding: 3px;
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--bg-0) 92%, transparent);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  z-index: 5;
}
.cvv-controls .icon-btn { width: 26px; height: 26px; }
.cvv-controls .icon-btn:disabled { opacity: 0.4; cursor: default; }
.cvv-zoom {
  min-width: 34px;
  text-align: center;
  font-size: 10.5px;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
@media (hover: none) {
  .cvv-controls .icon-btn { width: 32px; height: 32px; }
}

/* --- the eye dialog holds one of these --- */
.cvprev-live {
  height: min(58vh, 560px);
  min-height: 220px;
  border: 1px solid var(--border);
  border-radius: var(--r-md, 12px);
  overflow: hidden;
}
.cvprev-hint { font-size: var(--text-xs); color: var(--text-3); line-height: 1.5; }

/* ===== v10.9: and the same board, embedded in a note ===== */

.cvembed {
  --cvembed-h: 320px;
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 100%;
  margin: var(--sp-5) 0;
  border: 1px solid var(--border);
  border-radius: var(--r-md, 12px);
  background: var(--bg-0);
  overflow: hidden;
}
.cvembed.is-align-left  { max-width: min(58%, 520px); margin-right: auto; }
.cvembed.is-align-right { max-width: min(58%, 520px); margin-left: auto; }
.cvembed.is-align-center { max-width: min(86%, 720px); margin-left: auto; margin-right: auto; }
.cvembed.is-align-full { max-width: 100%; }
@media (max-width: 620px) {
  /* A 58%-wide board on a phone is a postage stamp. */
  .cvembed.is-align-left, .cvembed.is-align-right, .cvembed.is-align-center { max-width: 100%; }
}
.cvembed-head {
  flex: none;
  display: flex; align-items: center; gap: 6px;
  padding: 5px 6px 5px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-1);
  font-size: var(--text-xs);
  color: var(--text-2);
  min-width: 0;
}
.cvembed-head > svg { color: var(--accent); flex: none; }
.cvembed-name {
  flex: 1 1 auto; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 600;
}
.cvembed-tools { flex: none; display: flex; align-items: center; gap: 1px; }
.cvembed-btn {
  width: 24px; height: 24px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 0; background: transparent; padding: 0;
  border-radius: var(--r-sm, 6px);
  color: var(--text-3);
  cursor: pointer;
}
.cvembed-btn:hover, .cvembed-btn:focus-visible { background: var(--bg-2); color: var(--text-0); }
.cvembed-btn.is-on { background: var(--accent); color: var(--accent-on, #fff); }
.cvembed-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
@media (hover: none) {
  .cvembed-btn { width: 30px; height: 30px; }
}
.cvembed-stage { flex: 1 1 auto; height: var(--cvembed-h); min-height: 140px; }
.cvembed-stage .cvv, .cvembed-stage .cvv-stage { height: 100%; }
.cvembed-stage .cvv-stage { border-radius: 0; }
.cvembed-grip {
  flex: none;
  height: 12px;
  cursor: ns-resize;
  background: var(--bg-1);
  border-top: 1px solid var(--border);
  position: relative;
  touch-action: none;
}
.cvembed-grip::after {
  content: '';
  position: absolute; left: 50%; top: 50%;
  width: 34px; height: 3px;
  transform: translate(-50%, -50%);
  border-radius: 2px;
  background: var(--border-strong);
}
.cvembed-grip:hover::after { background: var(--accent); }
.cvembed.is-resizing { outline: 2px solid var(--accent); outline-offset: -1px; }
@media (hover: none) {
  .cvembed-grip { height: 20px; }
}
.cvembed.is-missing {
  border-style: dashed;
  border-color: color-mix(in srgb, #e0245e 40%, var(--border));
}
.cvembed.is-missing .cvembed-head { background: transparent; }
/* Printing a note prints the board, not its controls. */
@media print {
  .cvv-controls, .cvv-badge, .cvembed-grip, .cvembed-tools { display: none !important; }
}
'''


def block(name):
    return _BLOCKS[name]


BANNER = '=' * 80


def main(argv):
    if len(argv) < 2:
        print('usage: python3 fix_v109_standalone.py <index.html> [--dry-run]')
        return 2
    path = argv[1]
    dry = '--dry-run' in argv[2:]

    if not os.path.isfile(path):
        print('ERROR: no such file: %s' % path)
        return 1

    with io.open(path, encoding='utf-8') as fh:
        src = fh.read()

    print(BANNER)
    print(' Nodalis v10.9.0 - a live canvas preview, canvases embedded in a')
    print('                   note, and ink that survives a theme change')
    print(BANNER)
    print(' file: %s  (%d bytes)' % (path, len(src.encode('utf-8'))))
    print('')

    if MARKER in src:
        print('ERROR: v10.9.0 is already installed in this file.')
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

    report('ink: a colour that can be seen on the paper it is on', once('  function colorFromString(str) {', block('inkutil.js').rstrip('\n') + '\n  function colorFromString(str) {', 'ink helper'))

    report('ink: exported from util', once('    luminance: luminance, readableOn: readableOn, contrastRatio: contrastRatio, colorFromString: colorFromString,', '    luminance: luminance, readableOn: readableOn, contrastRatio: contrastRatio, colorFromString: colorFromString,\n    visibleInk: visibleInk, canvasPaper: canvasPaper, toHex: toHex,', 'util exports'))

    report('canvas: a new stroke does not bake the theme into itself', once("      const stroke = { id: U.uid('sk'), points: [[round(world.x), round(world.y)]], color: inkColor || currentAccent(), width: inkWidth };", "      /*\n       * v10.9: color is NULL when the pen has no colour of its own.\n       *\n       * It used to be currentAccent() - the theme's --text-0 read at the\n       * moment of drawing - which is why a line drawn in the dark was stored\n       * as white and vanished the moment the lights came on. A pen with no\n       * colour follows the paper instead, for ever, and a pen with a colour\n       * keeps it.\n       */\n      const stroke = { id: U.uid('sk'), points: [[round(world.x), round(world.y)]], color: inkColor || null, width: inkWidth };", 'canvas stroke colour'))

    report('canvas: ink is painted in a colour that can be seen', once("      path.setAttribute('stroke', stroke.color || 'currentColor');", "      /* v10.9: not necessarily the colour it was stored with - see\n         U.visibleInk. An old stroke that would be invisible on this theme is\n         flipped in lightness and kept. */\n      path.setAttribute('stroke', U.visibleInk(stroke.color, paper));", 'canvas ink paint'))

    report('canvas: the paper is measured once per repaint', once("  function drawInk() {\n    Array.prototype.slice.call(svg.querySelectorAll('[data-stroke]')).forEach(function (n) { n.remove(); });\n    if (!doc || !doc.strokes.length) return;", "  function drawInk() {\n    Array.prototype.slice.call(svg.querySelectorAll('[data-stroke]')).forEach(function (n) { n.remove(); });\n    if (!doc || !doc.strokes.length) return;\n    const paper = U.canvasPaper();", 'canvas paper'))

    report('canvas: a theme change repaints the ink', once("    N.bus.on('vault:changed', U.debounce(refreshPicker, 300));", "    N.bus.on('vault:changed', U.debounce(refreshPicker, 300));\n    /* v10.9: the paper moved, so the ink has to be re-checked against it. */\n    N.bus.on('settings:changed', function () { if (doc) drawInk(); });\n    N.bus.on('theme:changed', function () { if (doc) drawInk(); });", 'canvas theme repaint'))

    report('canvas: the line you are drawing is visible while you draw it', once(
        """        path.setAttribute('stroke', interaction.stroke.color);""",
        """        /*
         * v10.9: through visibleInk, like every other stroke.
         *
         * A pen with no colour of its own now stores color: null, and
         * setAttribute('stroke', null) writes the STRING "null" - which is
         * not a colour, so the line you were drawing would not appear until
         * you let go and drawInk() painted it properly. Checked, and fixed
         * before it could ship.
         */
        path.setAttribute('stroke', U.visibleInk(interaction.stroke.color, U.canvasPaper()));""",
        'in-progress stroke'))

    report('export: ink is visible on the white page too', once("    (doc.strokes || []).forEach(function (stroke) {\n      ctx.strokeStyle = stroke.color || '#333';", "    (doc.strokes || []).forEach(function (stroke) {\n      /* v10.9: the export paints on WHITE, so white ink drawn on a dark\n         theme would come out as an empty picture. Same rule as the board. */\n      ctx.strokeStyle = U.visibleInk(stroke.color, '#ffffff');", 'export ink'))

    report('the live-preview module', once('/* ===== js/app.js ===== */', block('cvview.js') + '/* ===== js/app.js ===== */', 'cvview module'))

    report('and it starts with everything else', once("      ['cvlink', N.cvlink],\n    ];", "      /* v10.9: cvview before cvlink - the dialog mounts one. */\n      ['cvview', N.cvview],\n      ['cvlink', N.cvlink],\n    ];", 'cvview init'))

    report('the eye dialog shows the live board, not a picture', once("        const stage = el('div.cvprev-stage');\n        stage.appendChild(el('div.cvprev-loading', null, 'Drawing the board…'));\n        box.appendChild(stage);", "        /*\n         * v10.9: THE PREVIEW IS THE BOARD, NOT A PICTURE OF IT.\n         *\n         * v10.8 drew a PNG here, which was faithful and completely inert -\n         * you could not scroll it, zoom it, or move a card aside to see what\n         * was behind it. This mounts the real thing instead, on a deep clone,\n         * so all of that works and none of it is written down.\n         */\n        const stage = el('div.cvprev-stage.cvprev-live');\n        box.appendChild(stage);\n        box.appendChild(el('p.cvprev-hint', null,\n          'Drag to pan, scroll or pinch to zoom, drag a card to move it. Nothing here is saved to the canvas.'));", 'cvprev stage'))

    report('the eye dialog mounts it and lets go of it', once(
        """        /* The same renderer the PNG export uses. */
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
        return box;""",
        """        /* Mounted after the dialog has been laid out, so the board is
           fitted to a stage that has its real width rather than to 0px. */
        setTimeout(function () {
          if (!N.cvview || !document.body.contains(stage)) return;
          mounted = N.cvview.mount(stage, id, {
            movable: true,
            controls: true,
            onOpen: function (cid) { api.close('open'); if (N.canvas && N.canvas.open) N.canvas.open(cid); },
          });
        }, 30);
        return box;""", 'dialog mount'))

    report('the eye dialog tidies up after itself', once(
        """    let shot = null;
    const api = N.modal.open({""",
        """    /*
     * v10.9: the mounted board, so it can be destroyed when the dialog goes.
     * A live preview holds a resize listener and any object URLs its images
     * needed; leaving one behind per open would be a leak per click.
     */
    let mounted = null;
    const api = N.modal.open({""", 'dialog handle'))

    report('the eye dialog still hands over a picture on request', once(
        """        out.push(el('button.btn', { type: 'button', onclick: function () { a.close(null); } }, 'Close'));
        if (shot !== undefined) {
          const copy = el('button.btn', { type: 'button', title: 'Put the picture on the clipboard' }, 'Copy picture');
          copy.addEventListener('click', async function () {
            try {
              if (!shot) throw new Error('nothing drawn');
              const blob = await (await fetch(shot)).blob();""",
        """        out.push(el('button.btn', { type: 'button', onclick: function () { a.close(null); } }, 'Close'));
        {
          const copy = el('button.btn', { type: 'button', title: 'Put the picture on the clipboard' }, 'Copy picture');
          copy.addEventListener('click', async function () {
            try {
              /* v10.9: drawn on demand now that the preview itself is live. */
              const shot = (N.exporter && N.exporter.canvasImage)
                ? await N.exporter.canvasImage(get(id), 1600) : null;
              if (!shot) throw new Error('nothing drawn');
              const blob = await (await fetch(shot)).blob();""", 'dialog copy'))

    report('the eye dialog destroys the board when it closes', once(
        """      title: canvas.title || 'Untitled canvas',
      size: 'lg',
      dismissValue: null,
      showClose: true,""",
        """      title: canvas.title || 'Untitled canvas',
      size: 'lg',
      dismissValue: null,
      showClose: true,
      onClose: function () {
        if (mounted) { try { mounted.destroy(); } catch (err) { /* already gone */ } mounted = null; }
      },""", 'dialog close'))

    report('notes: the embed keeps its options', once('    src = src.replace(/!\\[\\[([^\\]|#^]+)(#[^\\]|^]*)?(\\^[^\\]|]*)?(\\|[^\\]]*)?\\]\\]/g, function (_, target) {\n      stash.push(renderEmbedPlaceholder(target.trim(), options));\n      return SENTINEL + (stash.length - 1) + SENTINEL;\n    });', "    /* v10.9: the raw match and the |option|option tail are handed on, so an\n       embedded canvas can carry its alignment and its height. */\n    src = src.replace(/!\\[\\[([^\\]|#^]+)(#[^\\]|^]*)?(\\^[^\\]|]*)?(\\|[^\\]]*)?\\]\\]/g,\n      function (raw, target, heading, blockRef, opts) {\n        stash.push(renderEmbedPlaceholder(target.trim(), options, opts || '', raw));\n        return SENTINEL + (stash.length - 1) + SENTINEL;\n      });", 'md embed call'))

    report('notes: ![[canvas: name]] is a canvas', once('  function renderEmbedPlaceholder(target, options) {\n    const note = N.store && N.store.findNoteByTitle(target);', block('mdembed.js').rstrip('\n') + '\n  function renderEmbedPlaceholder(target, options, optionText, raw) {\n    /* v10.9: a canvas embed before anything else, because "canvas: Name" is\n       not the title of a note and must not be looked up as one. */\n    const cv = /^canvas\\s*:\\s*([\\s\\S]+)$/i.exec(target);\n    if (cv) return renderCanvasEmbed(cv[1].trim(), optionText, raw);\n    const note = N.store && N.store.findNoteByTitle(target);', 'md canvas embed'))

    report('notes: an embedded canvas is not a broken note link', once(
        """      const target = m[1].trim();
      if (!target) continue;
      const key = target.toLowerCase();""",
        """      const target = m[1].trim();
      if (!target) continue;
      /*
       * v10.9: ![[canvas: Name]] is a canvas, not a note.
       *
       * Without this the embed was indexed as a wikilink to a note called
       * "canvas: Name", so the Links panel listed it as "not created yet"
       * and Check my vault reported a dead link for every embedded board.
       * Measured on a note with one embed: 1 link from this note, 1 broken.
       */
      if (/^canvas\s*:/i.test(target)) continue;
      const key = target.toLowerCase();""", 'link index'))

    report('notes: the embeds become live boards', once('  async function hydrateAttachments(root) {', block('hydrate.js') + '  async function hydrateAttachments(root) {', 'hydrate fns'))

    report('notes: hydrated on every render, torn down first', once("    hydrateAttachments(preview);\n    bus.emit('preview:rendered', preview);", "    hydrateAttachments(preview);\n    /* v10.9: the old boards go before the new ones are mounted, or every\n       keystroke would leave a listener and an object URL behind. */\n    dropCanvasEmbeds();\n    hydrateCanvasEmbeds(preview);\n    bus.emit('preview:rendered', preview);", 'hydrate call'))

    report('notes: and a way to insert one without typing it', once("      { label: 'Insert table of contents', icon: 'list-tree', onClick: function () { insertAtCursor('\\n' + buildToc() + '\\n'); } },", "      { label: 'Insert table of contents', icon: 'list-tree', onClick: function () { insertAtCursor('\\n' + buildToc() + '\\n'); } },\n      { label: 'Embed a canvas here…', icon: 'canvas',\n        description: 'A live board in the note, resizable and alignable',\n        onClick: async function () {\n          if (!N.cvlink) return;\n          const id = await N.cvlink.pick({ forName: N.store.noteTitle(note), title: 'Embed which canvas?' });\n          if (!id) return;\n          const cv = N.cvlink.get(id);\n          insertAtCursor('\\n![[canvas: ' + (cv ? (cv.title || id) : id) + ']]\\n');\n          N.toast.success('Canvas embedded — drag its grip to resize it', { ms: 3200 });\n        } },", 'note menu embed'))

    report('the alignment icons', once("    'align-center': 'M6 6.5h12M3.5 12h17M6 17.5h12',", block('icons.js').rstrip('\n'), 'icons'))

    report('the stylesheet', once('\n</style>\n</head>', '\n' + block('css109.css') + '\n</style>\n</head>', 'css'))

    report('the build label and date', once("  N.versionName = 'v10.8';\n  N.built = '2026-09-07';", "  N.versionName = 'v10.9';\n  N.built = '2026-09-09';", 'build label'))

    report('version 10.9.0', once("  N.version = '10.8.0';", "  N.version = '10.9.0';", 'version'))


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
