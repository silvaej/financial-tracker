(function () {
  function nodeBox(node) {
    const x = parseFloat(node.dataset.x) || 0;
    const y = parseFloat(node.dataset.y) || 0;
    const w = node.offsetWidth || 160;
    const h = node.offsetHeight || 70;
    return { x, y, w, h };
  }

  // Clamp an external point into `rect`'s bounds on both axes; if the
  // clamped point lands strictly inside (the two rects' projections
  // overlap on both axes), push it out to the nearest of the 4 edges so
  // the result is always a boundary point, never an interior one.
  function nearestBoundaryPoint(rect, ext) {
    let x = Math.max(rect.x, Math.min(ext.x, rect.x + rect.w));
    let y = Math.max(rect.y, Math.min(ext.y, rect.y + rect.h));
    const insideX = x > rect.x && x < rect.x + rect.w;
    const insideY = y > rect.y && y < rect.y + rect.h;
    if (insideX && insideY) {
      const dLeft = x - rect.x;
      const dRight = rect.x + rect.w - x;
      const dTop = y - rect.y;
      const dBottom = rect.y + rect.h - y;
      const m = Math.min(dLeft, dRight, dTop, dBottom);
      if (m === dLeft) x = rect.x;
      else if (m === dRight) x = rect.x + rect.w;
      else if (m === dTop) y = rect.y;
      else y = rect.y + rect.h;
    }
    return { x, y };
  }

  // Which side of `box` a boundary point landed on.
  function pointSide(box, p) {
    const eps = 0.5;
    if (Math.abs(p.x - box.x) <= eps) return "left";
    if (Math.abs(p.x - (box.x + box.w)) <= eps) return "right";
    if (Math.abs(p.y - box.y) <= eps) return "top";
    return "bottom";
  }

  function sideMidpoint(box, side) {
    if (side === "left") return { x: box.x, y: box.y + box.h / 2 };
    if (side === "right") return { x: box.x + box.w, y: box.y + box.h / 2 };
    if (side === "top") return { x: box.x + box.w / 2, y: box.y };
    return { x: box.x + box.w / 2, y: box.y + box.h };
  }

  const EXPENSE_GAP = 16;

  // Expense nodes default to sitting directly below their channel, using
  // the channel's *actual* rendered height (which varies with content --
  // a carry-in note, etc.) rather than a guessed fixed offset, so they can
  // never overlap their own channel or whatever's in the row below. This
  // also makes a freshly-dragged channel's expense node land correctly
  // without needing a Save round-trip. Once a user manually drags an
  // expense node, it stops auto-following so their placement sticks.
  function repositionExpenseNodes(canvas) {
    canvas.querySelectorAll('.canvas-node[data-node-kind="expense"]').forEach((expenseNode) => {
      if (expenseNode.dataset.manuallyPositioned === "true") return;
      const channelId = "channel-" + expenseNode.dataset.nodeId.split("-")[1];
      const channelNode = canvas.querySelector('[data-node-id="' + channelId + '"]');
      if (!channelNode) return;
      const box = nodeBox(channelNode);
      expenseNode.dataset.x = box.x;
      expenseNode.dataset.y = box.y + box.h + EXPENSE_GAP;
    });
  }

  function redrawCanvas(canvas) {
    repositionExpenseNodes(canvas);

    canvas.querySelectorAll(".canvas-node").forEach((node) => {
      node.style.left = (parseFloat(node.dataset.x) || 0) + "px";
      node.style.top = (parseFloat(node.dataset.y) || 0) + "px";
    });

    const edges = Array.from(canvas.querySelectorAll(".canvas-edge-line"))
      .map((path) => {
        const from = canvas.querySelector('[data-node-id="' + path.dataset.from + '"]');
        const to = canvas.querySelector('[data-node-id="' + path.dataset.to + '"]');
        if (!from || !to) return null;
        const a = nodeBox(from);
        const b = nodeBox(to);
        const centerA = { x: a.x + a.w / 2, y: a.y + a.h / 2 };
        const centerB = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
        return { path, a, b, p1: nearestBoundaryPoint(a, centerB), p2: nearestBoundaryPoint(b, centerA) };
      })
      .filter(Boolean);

    // All of a node's outgoing connections meet at one point, and all of
    // its incoming connections meet at another -- whichever side each
    // group would naturally land on -- rather than fanning out around the
    // node. These are tracked separately (not just one shared point for
    // everything): a node with, say, 3 outgoing transfers/contributions
    // pulling its shared point toward "right" would otherwise also drag a
    // single incoming transfer onto "right" even when the sender sits to
    // its left, drawing that line straight through the node to reach a
    // point on its far side.
    const sidesByNode = {};
    function recordSide(key, box, side) {
      const entry = (sidesByNode[key] = sidesByNode[key] || { box, counts: {}, order: [] });
      if (!(side in entry.counts)) entry.order.push(side);
      entry.counts[side] = (entry.counts[side] || 0) + 1;
    }
    edges.forEach((edge) => {
      recordSide(edge.path.dataset.from + ":out", edge.a, pointSide(edge.a, edge.p1));
      recordSide(edge.path.dataset.to + ":in", edge.b, pointSide(edge.b, edge.p2));
    });

    const dominantSide = {};
    Object.keys(sidesByNode).forEach((key) => {
      const { counts, order } = sidesByNode[key];
      let best = order[0];
      order.forEach((side) => {
        if (counts[side] > counts[best]) best = side;
      });
      dominantSide[key] = best;
    });

    edges.forEach((edge) => {
      edge.p1 = sideMidpoint(edge.a, dominantSide[edge.path.dataset.from + ":out"]);
      edge.p2 = sideMidpoint(edge.b, dominantSide[edge.path.dataset.to + ":in"]);
    });

    edges.forEach(({ path, p1, p2 }) => {
      path.setAttribute("d", "M " + p1.x + " " + p1.y + " L " + p2.x + " " + p2.y);

      const label = canvas.querySelector(
        '.canvas-edge-label[data-edge-id="' + path.dataset.edgeId + '"]'
      );
      if (label) {
        label.style.left = (p1.x + p2.x) / 2 + "px";
        label.style.top = (p1.y + p2.y) / 2 + "px";
      }
    });
  }

  // Expense nodes/edges are a read-only summary the server derives from
  // each channel's expenses -- not part of the user-editable graph, so
  // they're excluded from connectivity validation and the save/preview
  // payload (see buildCanvasPayload).
  function isRealEdge(line) {
    return line.dataset.edgeId.indexOf("expense-") !== 0;
  }

  function unconnectedNodes(canvas) {
    const connected = new Set();
    canvas.querySelectorAll(".canvas-edge-line").forEach((line) => {
      if (!isRealEdge(line)) return;
      connected.add(line.dataset.from);
      connected.add(line.dataset.to);
    });
    return Array.from(canvas.querySelectorAll(".canvas-node")).filter(
      (node) => node.dataset.nodeKind !== "expense" && !connected.has(node.dataset.nodeId)
    );
  }

  function saveBarFor(canvas) {
    const section = canvas.closest(".section");
    return section ? section.querySelector(".canvas-save-bar") : null;
  }

  function refreshCanvasValidation(canvas) {
    const bad = unconnectedNodes(canvas);
    canvas.querySelectorAll(".canvas-node").forEach((node) => {
      node.classList.toggle("canvas-node-unconnected", bad.indexOf(node) !== -1);
    });

    const bar = saveBarFor(canvas);
    if (!bar) return;
    const status = bar.querySelector(".canvas-save-status");
    const btn = bar.querySelector(".canvas-save-btn");
    const dirty = canvas.dataset.dirty === "true";

    if (!dirty) {
      status.textContent = "All changes saved";
      status.classList.remove("canvas-save-status-dirty");
      btn.disabled = true;
    } else if (bad.length > 0) {
      status.textContent = "Connect every node before saving";
      status.classList.add("canvas-save-status-dirty");
      btn.disabled = true;
    } else {
      status.textContent = "Unsaved changes";
      status.classList.add("canvas-save-status-dirty");
      btn.disabled = false;
    }
  }

  function markDirty(canvas) {
    canvas.dataset.dirty = "true";
    refreshCanvasValidation(canvas);
  }

  // Undo for staged (pre-Save) canvas edits: a snapshot stack per canvas,
  // rather than hand-written inverse operations per action -- simpler and
  // far less error-prone than reconstructing exactly what placeNode,
  // removeNode's cascades, toolbox-item show/hide, etc. each need to undo.
  const undoStacks = new WeakMap();
  const UNDO_LIMIT = 25;

  function undoBarFor(canvas) {
    const bar = saveBarFor(canvas);
    return bar ? bar.querySelector('[data-role="undo"]') : null;
  }

  function updateUndoButton(canvas) {
    const btn = undoBarFor(canvas);
    if (!btn) return;
    const stack = undoStacks.get(canvas) || [];
    btn.disabled = stack.length === 0;
  }

  function pushUndo(canvas) {
    const inner = canvas.querySelector(".canvas-inner");
    const section = canvas.closest(".section");
    const toolbox = section ? section.querySelector(".toolbox") : null;
    const stack = undoStacks.get(canvas) || [];
    stack.push({
      innerHTML: inner ? inner.innerHTML : "",
      toolboxHTML: toolbox ? toolbox.innerHTML : "",
      dirty: canvas.dataset.dirty === "true",
    });
    if (stack.length > UNDO_LIMIT) stack.shift();
    undoStacks.set(canvas, stack);
    updateUndoButton(canvas);
  }

  function undoLastChange(canvas) {
    const stack = undoStacks.get(canvas);
    if (!stack || !stack.length) return;
    const snapshot = stack.pop();
    const inner = canvas.querySelector(".canvas-inner");
    const section = canvas.closest(".section");
    const toolbox = section ? section.querySelector(".toolbox") : null;
    if (inner) inner.innerHTML = snapshot.innerHTML;
    if (toolbox) toolbox.innerHTML = snapshot.toolboxHTML;
    canvas.dataset.dirty = snapshot.dirty ? "true" : "false";
    redrawCanvas(canvas);
    refreshCanvasValidation(canvas);
    schedulePreview(canvas);
    updateUndoButton(canvas);
  }

  const previewTimers = new WeakMap();
  const previewRequestIds = new WeakMap();

  function schedulePreview(canvas) {
    const existing = previewTimers.get(canvas);
    if (existing) clearTimeout(existing);
    previewTimers.set(
      canvas,
      setTimeout(() => runPreview(canvas), 250)
    );
  }

  function applyPreview(canvas, preview) {
    canvas.querySelectorAll('.canvas-node[data-node-kind="channel"]').forEach((node) => {
      const id = node.dataset.nodeId.split("-")[1];
      const net = preview.channel_balances[id];
      if (net === undefined) return;
      const balanceEl = node.querySelector('[data-role="node-balance"]');
      if (balanceEl) {
        balanceEl.textContent = formatPeso(net);
        balanceEl.classList.remove("canvas-node-balance-pending");
        balanceEl.classList.toggle("card-value-neg", net < 0);
      }
      node.classList.toggle("canvas-node-warn", preview.unfunded_channel_ids.indexOf(+id) !== -1);
    });

    canvas.querySelectorAll('.canvas-node[data-node-kind="goal"]').forEach((node) => {
      const id = node.dataset.nodeId.split("-")[1];
      const contributed = preview.goal_contributed[id];
      if (contributed === undefined) return;
      const perPayout = parseFloat(node.dataset.perPayout || "0");
      const balanceEl = node.querySelector('[data-role="node-balance"]');
      if (balanceEl) {
        balanceEl.textContent = formatPeso(contributed) + " / " + formatPeso(perPayout);
        balanceEl.classList.remove("canvas-node-balance-pending");
      }
      const fillEl = node.querySelector('[data-role="node-progress-fill"]');
      if (fillEl) {
        const pct = perPayout ? Math.max(0, Math.min(100, (100 * contributed) / perPayout)) : 100;
        fillEl.style.width = pct + "%";
      }
      node.classList.toggle(
        "canvas-node-warn",
        preview.underfunded_goal_ids.indexOf(+id) !== -1
      );
    });
  }

  function runPreview(canvas) {
    const periodId = canvas.dataset.payoutPeriodId;
    const requestId = (previewRequestIds.get(canvas) || 0) + 1;
    previewRequestIds.set(canvas, requestId);

    fetch("/cashflow/" + periodId + "/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildCanvasPayload(canvas)),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((preview) => {
        if (!preview || previewRequestIds.get(canvas) !== requestId) return;
        applyPreview(canvas, preview);
      })
      .catch(() => {
        /* preview is best-effort -- leave whatever numbers are already shown */
      });
  }

  function initCashflowCanvases() {
    document.querySelectorAll(".canvas").forEach((canvas) => {
      redrawCanvas(canvas);
      refreshCanvasValidation(canvas);
      updateUndoButton(canvas);
      // First time this canvas element is seen (fresh page load, or a
      // fresh one swapped in by Save), fit the view to whatever's placed
      // instead of defaulting to 100%/no-pan -- a tall or wide graph can
      // easily exceed the canvas's fixed viewport, and defaulting to a
      // view that doesn't show all of it reads as a rendering bug (edges
      // running off the bottom/side) rather than "pan or zoom out."
      if (!canvasViewState.has(canvas) && canvas.querySelector(".canvas-node")) {
        recenterCanvas(canvas);
      } else {
        applyViewTransform(canvas);
      }
    });
  }

  // Per-canvas pan/zoom state. Never persisted -- a Save replaces the whole
  // #cashflow-page outerHTML with fresh DOM, so new canvases always miss
  // this WeakMap and get sane defaults for free.
  const canvasViewState = new WeakMap();
  const ZOOM_MIN = 0.5;
  const ZOOM_MAX = 1.5;
  const ZOOM_STEP = 0.1;

  function getViewState(canvas) {
    let state = canvasViewState.get(canvas);
    if (!state) {
      state = { scale: 1, panX: 0, panY: 0 };
      canvasViewState.set(canvas, state);
    }
    return state;
  }

  function applyViewTransform(canvas) {
    const state = getViewState(canvas);
    const inner = canvas.querySelector(".canvas-inner");
    if (inner) {
      inner.style.transform =
        "translate(" + state.panX + "px, " + state.panY + "px) scale(" + state.scale + ")";
    }
    const level = canvas.querySelector('[data-role="zoom-reset"]');
    if (level) level.textContent = Math.round(state.scale * 100) + "%";
  }

  function recenterCanvas(canvas) {
    const state = getViewState(canvas);
    const nodes = Array.from(canvas.querySelectorAll(".canvas-node"));
    if (!nodes.length) {
      state.scale = 1;
      state.panX = 0;
      state.panY = 0;
      applyViewTransform(canvas);
      return;
    }
    let minX = Infinity,
      minY = Infinity,
      maxX = -Infinity,
      maxY = -Infinity;
    nodes.forEach((node) => {
      const box = nodeBox(node);
      minX = Math.min(minX, box.x);
      minY = Math.min(minY, box.y);
      maxX = Math.max(maxX, box.x + box.w);
      maxY = Math.max(maxY, box.y + box.h);
    });
    const bboxW = maxX - minX || 1;
    const bboxH = maxY - minY || 1;
    const rect = canvas.getBoundingClientRect();
    let scale = Math.min((rect.width / bboxW) * 0.9, (rect.height / bboxH) * 0.9);
    scale = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, scale));
    state.scale = scale;
    state.panX = rect.width / 2 - (minX + bboxW / 2) * scale;
    state.panY = rect.height / 2 - (minY + bboxH / 2) * scale;
    applyViewTransform(canvas);
  }

  function canvasPoint(canvas, evt) {
    const rect = canvas.getBoundingClientRect();
    const state = getViewState(canvas);
    return {
      x: (evt.clientX - rect.left - state.panX) / state.scale,
      y: (evt.clientY - rect.top - state.panY) / state.scale,
    };
  }

  const CONNECT_BORDER_MARGIN = 14;

  function isNearNodeBorder(node, evt) {
    const rect = node.getBoundingClientRect();
    return (
      evt.clientX - rect.left <= CONNECT_BORDER_MARGIN ||
      rect.right - evt.clientX <= CONNECT_BORDER_MARGIN ||
      evt.clientY - rect.top <= CONNECT_BORDER_MARGIN ||
      rect.bottom - evt.clientY <= CONNECT_BORDER_MARGIN
    );
  }

  function nodeAtPoint(canvas, clientX, clientY, exclude) {
    const nodes = canvas.querySelectorAll(".canvas-node");
    for (const candidate of nodes) {
      if (candidate === exclude) continue;
      const rect = candidate.getBoundingClientRect();
      if (
        clientX >= rect.left &&
        clientX <= rect.right &&
        clientY >= rect.top &&
        clientY <= rect.bottom
      ) {
        return candidate;
      }
    }
    return null;
  }

  function formatPeso(amount) {
    const sign = amount < 0 ? "-" : "";
    return (
      sign +
      "₱" +
      Math.abs(amount).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  }

  // Server-rendered edges toggle view/edit spans keyed by "transfer-{id}" or
  // "gc-{id}" (goal contributions use the short "gc" prefix, transfers don't).
  function toggleKeyForEdge(edgeId) {
    if (edgeId.indexOf("goal-contribution-") === 0) {
      return "gc-" + edgeId.slice("goal-contribution-".length);
    }
    return edgeId;
  }

  function balancePlaceholder(kind, toolboxItem) {
    const el = document.createElement("div");
    el.className = "num text-sm mt-1 canvas-node-balance-pending";
    el.dataset.role = "node-balance";
    if (kind === "channel") {
      el.textContent = "Save to calculate";
    } else {
      const perPayout = parseFloat(toolboxItem.dataset.perPayout || "0");
      el.textContent = "-- / " + formatPeso(perPayout);
    }
    return el;
  }

  const WARN_BADGE_SVG =
    '<svg viewBox="0 0 20 20" fill="currentColor"><path d="M10 2 1 17h18L10 2Zm0 5.5c.5 0 .9.4.9.9v4a.9.9 0 0 1-1.8 0v-4c0-.5.4-.9.9-.9Zm0 8.4a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"/></svg>';

  // A channel dropped from the toolbox that has expenses this period needs
  // its own "Expenses" node too -- the server only ever renders one for
  // already-placed channels, so without this a freshly-dragged channel's
  // expenses would only show up after a Save round-trip.
  function createExpenseNodeForChannel(canvas, channelNode, toolboxItem) {
    const raw = toolboxItem.dataset.expenses;
    if (!raw) return;
    let items;
    try {
      items = JSON.parse(raw);
    } catch (err) {
      return;
    }
    if (!items || !items.length) return;

    const channelId = channelNode.dataset.nodeId;
    const expenseId = "expense-" + channelId.split("-")[1];
    const total = items.reduce((sum, item) => sum + item.amount, 0);

    const node = document.createElement("div");
    node.className = "canvas-node canvas-node-expense";
    node.dataset.nodeId = expenseId;
    node.dataset.nodeKind = "expense";
    node.dataset.x = channelNode.dataset.x;
    node.dataset.y = channelNode.dataset.y;

    const card = document.createElement("div");
    card.className = "canvas-node-expense-card";
    const label = document.createElement("div");
    label.className = "text-sm font-semibold";
    label.textContent = "Expenses";
    card.appendChild(label);
    const balance = document.createElement("div");
    balance.className = "num text-sm mt-1 card-value-neg";
    balance.dataset.role = "node-balance";
    balance.textContent = formatPeso(total);
    card.appendChild(balance);
    node.appendChild(card);

    const detail = document.createElement("div");
    detail.className = "canvas-expense-detail";
    const detailTitle = document.createElement("div");
    detailTitle.className = "canvas-expense-detail-title";
    detailTitle.textContent = "Breakdown";
    detail.appendChild(detailTitle);
    const list = document.createElement("ul");
    items.forEach((item) => {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = item.name;
      const amount = document.createElement("span");
      amount.className = "num";
      amount.textContent = formatPeso(item.amount);
      li.appendChild(name);
      li.appendChild(amount);
      list.appendChild(li);
    });
    detail.appendChild(list);
    node.appendChild(detail);

    canvas.querySelector(".canvas-inner").appendChild(node);

    const edge = document.createElementNS("http://www.w3.org/2000/svg", "path");
    edge.setAttribute("class", "canvas-edge-line");
    edge.dataset.edgeId = expenseId;
    edge.dataset.from = channelId;
    edge.dataset.to = expenseId;
    canvas.querySelector(".canvas-edges").appendChild(edge);
  }

  function placeNode(canvas, toolboxItem, x, y) {
    pushUndo(canvas);
    const kind = toolboxItem.dataset.nodeKind;
    const node = document.createElement("div");
    node.className = "canvas-node" + (kind === "goal" ? " canvas-node-goal" : "");
    node.dataset.nodeId = toolboxItem.dataset.nodeId;
    node.dataset.nodeKind = kind;
    node.dataset.x = x;
    node.dataset.y = y;
    if (kind === "goal") node.dataset.perPayout = toolboxItem.dataset.perPayout || "0";

    if (kind === "channel") {
      const badge = toolboxItem.querySelector(".badge");
      const color = badge ? badge.style.background : "";
      if (color) node.style.setProperty("--rail", color);
    }

    const warnBadge = document.createElement("span");
    warnBadge.className = "canvas-node-warn-badge";
    warnBadge.innerHTML = WARN_BADGE_SVG;
    node.appendChild(warnBadge);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "canvas-node-remove";
    remove.title = "Remove from canvas";
    remove.textContent = "×";
    node.appendChild(remove);

    const content = document.createElement("div");
    content.className = "flex items-center gap-1.5";
    content.innerHTML = toolboxItem.innerHTML;
    node.appendChild(content);

    node.appendChild(balancePlaceholder(kind, toolboxItem));

    if (kind === "goal") {
      const progress = document.createElement("div");
      progress.className = "canvas-node-progress bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.dataset.role = "node-progress-fill";
      fill.style.width = "0%";
      progress.appendChild(fill);
      node.appendChild(progress);
    }

    canvas.querySelector(".canvas-inner").appendChild(node);
    toolboxItem.style.display = "none";

    if (kind === "channel") createExpenseNodeForChannel(canvas, node, toolboxItem);

    redrawCanvas(canvas);
    markDirty(canvas);
    schedulePreview(canvas);
  }

  function cascadeRemoveEdges(canvas, nodeId) {
    canvas
      .querySelectorAll(
        '.canvas-edge-line[data-from="' + nodeId + '"], .canvas-edge-line[data-to="' + nodeId + '"]'
      )
      .forEach((line) => {
        const label = canvas.querySelector(
          '.canvas-edge-label[data-edge-id="' + line.dataset.edgeId + '"]'
        );
        line.remove();
        if (label) label.remove();
      });
  }

  // If the toolbox already has a (hidden) pill for this node -- placed
  // this session via placeNode, or restored by an undo snapshot -- just
  // un-hide it rather than looking for a stashed JS reference: an undo
  // rebuilds the toolbox from an HTML snapshot, which doesn't carry JS
  // properties attached to the old DOM nodes, so a reference would go
  // stale and this would otherwise build a duplicate hidden pill. Nodes
  // that were already placed when the page loaded have no pill at all (the
  // server never rendered one, since it was already on the canvas) -- build
  // one from the node's own content instead of leaving it stranded until
  // the next full-page render on Save.
  function restoreToolboxItem(canvas, node) {
    const section = canvas.closest(".section");
    const toolbox = section ? section.querySelector(".toolbox") : null;
    if (!toolbox) return;

    const kind = node.dataset.nodeKind;
    const item = document.createElement("div");
    item.className = "toolbox-item" + (kind === "goal" ? " toolbox-item-goal" : "");
    item.dataset.nodeId = node.dataset.nodeId;
    item.dataset.nodeKind = kind;
    if (kind === "goal") item.dataset.perPayout = node.dataset.perPayout || "0";

    if (kind === "channel") {
      const content = node.querySelector(".flex.items-center");
      if (content) item.innerHTML = content.innerHTML;
    } else {
      const nameEl = node.querySelector(".text-sm.font-semibold");
      const span = document.createElement("span");
      span.className = "text-xs font-semibold";
      span.textContent = nameEl ? nameEl.textContent.trim() : "";
      item.appendChild(span);
    }

    const empty = toolbox.querySelector(".toolbox-empty");
    if (empty) empty.remove();
    toolbox.appendChild(item);
  }

  function removeNode(canvas, node) {
    pushUndo(canvas);
    cascadeRemoveEdges(canvas, node.dataset.nodeId);
    if (node.dataset.nodeKind === "channel") {
      // A channel's Expenses node makes no sense stranded without it.
      const expenseId = "expense-" + node.dataset.nodeId.split("-")[1];
      const expenseNode = canvas.querySelector('[data-node-id="' + expenseId + '"]');
      if (expenseNode) {
        cascadeRemoveEdges(canvas, expenseId);
        expenseNode.remove();
      }
    }
    const section = canvas.closest(".section");
    const toolbox = section ? section.querySelector(".toolbox") : null;
    const existingItem = toolbox
      ? toolbox.querySelector('[data-node-id="' + node.dataset.nodeId + '"]')
      : null;
    if (existingItem) {
      existingItem.style.display = "";
    } else {
      restoreToolboxItem(canvas, node);
    }
    node.remove();
    redrawCanvas(canvas);
    markDirty(canvas);
    schedulePreview(canvas);
  }

  function removeEdge(canvas, edgeId) {
    pushUndo(canvas);
    const line = canvas.querySelector('.canvas-edge-line[data-edge-id="' + edgeId + '"]');
    const label = canvas.querySelector('.canvas-edge-label[data-edge-id="' + edgeId + '"]');
    if (line) line.remove();
    if (label) label.remove();
    redrawCanvas(canvas);
    markDirty(canvas);
    schedulePreview(canvas);
  }

  let pendingEdgeCounter = 0;

  function createEdge(canvas, sourceNode, targetNode) {
    pushUndo(canvas);
    const isGoal = targetNode.dataset.nodeKind === "goal";
    pendingEdgeCounter += 1;
    const edgeId = (isGoal ? "goal-contribution-" : "transfer-") + "pending" + pendingEdgeCounter;
    const toggleKey = toggleKeyForEdge(edgeId);

    const line = document.createElementNS("http://www.w3.org/2000/svg", "path");
    line.setAttribute("class", "canvas-edge-line");
    line.dataset.edgeId = edgeId;
    line.dataset.from = sourceNode.dataset.nodeId;
    line.dataset.to = targetNode.dataset.nodeId;
    canvas.querySelector(".canvas-edges").appendChild(line);

    const label = document.createElement("div");
    label.className = "canvas-edge-label";
    label.dataset.edgeId = edgeId;

    const view = document.createElement("span");
    view.className = "view-" + toggleKey;
    view.textContent = formatPeso(0);
    // An inline attribute (matching the server-rendered markup) rather than
    // addEventListener, so this keeps working if the node is ever restored
    // from an innerHTML snapshot (see undo), which doesn't carry JS
    // listeners with it.
    view.setAttribute("onclick", "toggleEditMode('" + toggleKey + "')");
    label.appendChild(view);

    const editWrap = document.createElement("span");
    editWrap.className = "edit-" + toggleKey + " hidden";
    const input = document.createElement("input");
    input.className = "field field-mono w-20";
    input.type = "number";
    input.step = "0.01";
    input.value = "0";
    input.dataset.role = "edge-amount";
    editWrap.appendChild(input);
    label.appendChild(editWrap);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "icon-btn";
    del.dataset.role = "edge-remove";
    del.title = "Remove connection";
    del.textContent = "×";
    label.appendChild(del);

    canvas.querySelector(".canvas-inner").appendChild(label);

    redrawCanvas(canvas);
    markDirty(canvas);
    schedulePreview(canvas);
  }

  function buildCanvasPayload(canvas) {
    const channelPlacements = [];
    const goalPlacements = [];
    canvas.querySelectorAll(".canvas-node").forEach((node) => {
      if (node.dataset.nodeKind === "expense") return;
      const [kind, idStr] = node.dataset.nodeId.split("-");
      const id = parseInt(idStr, 10);
      const x = parseFloat(node.dataset.x) || 0;
      const y = parseFloat(node.dataset.y) || 0;
      if (kind === "channel") {
        channelPlacements.push({ channel_id: id, x, y });
      } else {
        goalPlacements.push({ goal_id: id, x, y });
      }
    });

    const transfers = [];
    const goalContributions = [];
    canvas.querySelectorAll(".canvas-edge-line").forEach((line) => {
      if (!isRealEdge(line)) return;
      const fromId = parseInt(line.dataset.from.split("-")[1], 10);
      const toParts = line.dataset.to.split("-");
      const toId = parseInt(toParts[1], 10);
      const label = canvas.querySelector(
        '.canvas-edge-label[data-edge-id="' + line.dataset.edgeId + '"]'
      );
      const input = label ? label.querySelector('[data-role="edge-amount"]') : null;
      const amount = input ? parseFloat(input.value) || 0 : 0;
      if (toParts[0] === "goal") {
        goalContributions.push({ channel_id: fromId, goal_id: toId, amount });
      } else {
        transfers.push({ from_channel_id: fromId, to_channel_id: toId, amount });
      }
    });

    return {
      channel_placements: channelPlacements,
      goal_placements: goalPlacements,
      transfers,
      goal_contributions: goalContributions,
    };
  }

  function saveCanvas(canvas, bar) {
    const btn = bar.querySelector(".canvas-save-btn");
    const status = bar.querySelector(".canvas-save-status");
    const url = btn.dataset.saveUrl;
    btn.disabled = true;
    status.textContent = "Saving…";

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildCanvasPayload(canvas)),
    })
      .then(async (res) => {
        if (!res.ok) {
          let message = "Could not save changes.";
          try {
            const data = await res.json();
            if (data && data.detail) message = data.detail;
          } catch (err) {
            /* response wasn't JSON, fall back to default message */
          }
          if (window.showAlert) window.showAlert(message);
          refreshCanvasValidation(canvas);
          return;
        }
        const page = document.getElementById("cashflow-page");
        if (page) page.outerHTML = await res.text();
        initCashflowCanvases();
      })
      .catch(() => {
        if (window.showAlert) window.showAlert("Could not save changes. Check your connection.");
        refreshCanvasValidation(canvas);
      });
  }

  let dragState = null;

  function onPointerDown(evt) {
    const toolboxItem = evt.target.closest(".toolbox-item");
    if (toolboxItem) {
      evt.preventDefault();
      const ghost = toolboxItem.cloneNode(true);
      ghost.style.position = "fixed";
      ghost.style.pointerEvents = "none";
      ghost.style.zIndex = "9999";
      ghost.style.left = evt.clientX + "px";
      ghost.style.top = evt.clientY + "px";
      ghost.style.opacity = "0.85";
      document.body.appendChild(ghost);
      dragState = { mode: "place", sourceItem: toolboxItem, ghost };
      return;
    }

    if (evt.target.closest(".canvas-node-remove")) return;
    if (evt.target.closest(".canvas-edge-label")) return;

    const canvas = evt.target.closest(".canvas");
    if (!canvas) return;

    const node = evt.target.closest(".canvas-node");
    if (node) {
      evt.preventDefault();

      if (node.dataset.nodeKind === "channel" && isNearNodeBorder(node, evt)) {
        const start = canvasPoint(canvas, evt);
        const ghost = document.createElementNS("http://www.w3.org/2000/svg", "line");
        ghost.setAttribute("class", "canvas-edge-line");
        ghost.setAttribute("stroke-dasharray", "4");
        ghost.setAttribute("x1", start.x);
        ghost.setAttribute("y1", start.y);
        ghost.setAttribute("x2", start.x);
        ghost.setAttribute("y2", start.y);
        canvas.querySelector(".canvas-edges").appendChild(ghost);
        dragState = {
          mode: "connect",
          canvas,
          sourceNode: node,
          ghost,
          hoverNode: null,
        };
        return;
      }

      if (node.dataset.nodeKind === "expense") {
        // Opt out of auto-following its channel (see repositionExpenseNodes)
        // as soon as the drag starts, not when it ends -- otherwise every
        // redrawCanvas call during the drag would snap it straight back.
        // Its position isn't part of the save payload either, so it's not
        // undo-worthy.
        node.dataset.manuallyPositioned = "true";
      } else {
        pushUndo(canvas);
      }

      const point = canvasPoint(canvas, evt);
      dragState = {
        mode: "move",
        canvas,
        node,
        offsetX: point.x - (parseFloat(node.dataset.x) || 0),
        offsetY: point.y - (parseFloat(node.dataset.y) || 0),
      };
      return;
    }

    if (evt.target.closest(".canvas-zoom-control, .canvas-recenter-btn")) return;

    // Empty canvas background: pan the view.
    evt.preventDefault();
    const state = getViewState(canvas);
    dragState = {
      mode: "pan",
      canvas,
      startClientX: evt.clientX,
      startClientY: evt.clientY,
      startPanX: state.panX,
      startPanY: state.panY,
    };
    canvas.classList.add("canvas-panning");
  }

  // Hint that a channel node's border is a drag-to-connect zone before the
  // user actually starts dragging, by swapping in a different cursor.
  let borderHoverNode = null;

  function updateBorderHoverCursor(evt) {
    const node = evt.target.closest(".canvas-node");
    const nearBorder = node && node.dataset.nodeKind === "channel" && isNearNodeBorder(node, evt);
    if (nearBorder) {
      if (borderHoverNode !== node) {
        if (borderHoverNode) borderHoverNode.classList.remove("canvas-node-connect-hover");
        node.classList.add("canvas-node-connect-hover");
        borderHoverNode = node;
      }
    } else if (borderHoverNode) {
      borderHoverNode.classList.remove("canvas-node-connect-hover");
      borderHoverNode = null;
    }
  }

  function onPointerMove(evt) {
    if (!dragState) {
      updateBorderHoverCursor(evt);
      return;
    }

    if (dragState.mode === "place") {
      dragState.ghost.style.left = evt.clientX + "px";
      dragState.ghost.style.top = evt.clientY + "px";
      return;
    }

    if (dragState.mode === "pan") {
      const state = getViewState(dragState.canvas);
      state.panX = dragState.startPanX + (evt.clientX - dragState.startClientX);
      state.panY = dragState.startPanY + (evt.clientY - dragState.startClientY);
      applyViewTransform(dragState.canvas);
      return;
    }

    const point = canvasPoint(dragState.canvas, evt);

    if (dragState.mode === "move") {
      dragState.node.dataset.x = Math.max(0, point.x - dragState.offsetX);
      dragState.node.dataset.y = Math.max(0, point.y - dragState.offsetY);
      redrawCanvas(dragState.canvas);
    } else if (dragState.mode === "connect") {
      dragState.ghost.setAttribute("x2", point.x);
      dragState.ghost.setAttribute("y2", point.y);

      let hover = nodeAtPoint(dragState.canvas, evt.clientX, evt.clientY, dragState.sourceNode);
      if (hover && hover.dataset.nodeKind === "expense") hover = null;
      if (hover !== dragState.hoverNode) {
        if (dragState.hoverNode) dragState.hoverNode.classList.remove("canvas-node-drop-target");
        if (hover) hover.classList.add("canvas-node-drop-target");
        dragState.hoverNode = hover;
      }
    }
  }

  function onPointerUp(evt) {
    if (!dragState) return;

    if (dragState.mode === "place") {
      dragState.ghost.remove();
      const under = document.elementFromPoint(evt.clientX, evt.clientY);
      const canvas = under ? under.closest(".canvas") : null;
      if (canvas) {
        const point = canvasPoint(canvas, evt);
        placeNode(canvas, dragState.sourceItem, Math.max(0, point.x - 70), Math.max(0, point.y - 30));
      }
    } else if (dragState.mode === "move") {
      // Expense nodes are a read-only derived summary -- their position
      // isn't part of the save payload, so dragging one shouldn't flip the
      // canvas into an "unsaved changes" state.
      if (dragState.node.dataset.nodeKind !== "expense") markDirty(dragState.canvas);
    } else if (dragState.mode === "pan") {
      dragState.canvas.classList.remove("canvas-panning");
    } else if (dragState.mode === "connect") {
      dragState.ghost.remove();
      if (dragState.hoverNode) dragState.hoverNode.classList.remove("canvas-node-drop-target");
      const targetNode = nodeAtPoint(
        dragState.canvas,
        evt.clientX,
        evt.clientY,
        dragState.sourceNode
      );
      if (targetNode && targetNode.dataset.nodeKind !== "expense") {
        createEdge(dragState.canvas, dragState.sourceNode, targetNode);
      }
    }
    dragState = null;
  }

  if (!window.__cashflowCanvasInit) {
    window.__cashflowCanvasInit = true;
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.body.addEventListener("htmx:afterSettle", initCashflowCanvases);

    document.addEventListener("click", (evt) => {
      const removeNodeBtn = evt.target.closest(".canvas-node-remove");
      if (removeNodeBtn) {
        const node = removeNodeBtn.closest(".canvas-node");
        const canvas = removeNodeBtn.closest(".canvas");
        if (node && canvas) removeNode(canvas, node);
        return;
      }

      const removeEdgeBtn = evt.target.closest('[data-role="edge-remove"]');
      if (removeEdgeBtn) {
        const label = removeEdgeBtn.closest(".canvas-edge-label");
        const canvas = removeEdgeBtn.closest(".canvas");
        if (label && canvas) removeEdge(canvas, label.dataset.edgeId);
        return;
      }

      const saveBtn = evt.target.closest(".canvas-save-btn");
      if (saveBtn) {
        const bar = saveBtn.closest(".canvas-save-bar");
        const canvas = bar ? bar.closest(".section").querySelector(".canvas") : null;
        if (canvas && bar && !saveBtn.disabled) saveCanvas(canvas, bar);
        return;
      }

      const undoBtn = evt.target.closest('[data-role="undo"]');
      if (undoBtn) {
        const bar = undoBtn.closest(".canvas-save-bar");
        const canvas = bar ? bar.closest(".section").querySelector(".canvas") : null;
        if (canvas && !undoBtn.disabled) undoLastChange(canvas);
        return;
      }

      const zoomInBtn = evt.target.closest('[data-role="zoom-in"]');
      if (zoomInBtn) {
        const canvas = zoomInBtn.closest(".canvas");
        if (canvas) {
          const state = getViewState(canvas);
          state.scale = Math.round(Math.min(ZOOM_MAX, state.scale + ZOOM_STEP) * 10) / 10;
          applyViewTransform(canvas);
        }
        return;
      }

      const zoomOutBtn = evt.target.closest('[data-role="zoom-out"]');
      if (zoomOutBtn) {
        const canvas = zoomOutBtn.closest(".canvas");
        if (canvas) {
          const state = getViewState(canvas);
          state.scale = Math.round(Math.max(ZOOM_MIN, state.scale - ZOOM_STEP) * 10) / 10;
          applyViewTransform(canvas);
        }
        return;
      }

      const zoomResetBtn = evt.target.closest('[data-role="zoom-reset"]');
      if (zoomResetBtn) {
        const canvas = zoomResetBtn.closest(".canvas");
        if (canvas) {
          const state = getViewState(canvas);
          state.scale = 1;
          state.panX = 0;
          state.panY = 0;
          applyViewTransform(canvas);
        }
        return;
      }

      const recenterBtn = evt.target.closest('[data-role="recenter"]');
      if (recenterBtn) {
        const canvas = recenterBtn.closest(".canvas");
        if (canvas) recenterCanvas(canvas);
      }
    });

    document.addEventListener(
      "wheel",
      (evt) => {
        const canvas = evt.target.closest(".canvas");
        if (!canvas) return;
        evt.preventDefault();

        const state = getViewState(canvas);
        const rect = canvas.getBoundingClientRect();
        const cx = evt.clientX - rect.left;
        const cy = evt.clientY - rect.top;
        const delta = evt.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP;
        const newScale = Math.round(Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, state.scale + delta)) * 10) / 10;
        if (newScale === state.scale) return;

        state.panX = cx - ((cx - state.panX) * newScale) / state.scale;
        state.panY = cy - ((cy - state.panY) * newScale) / state.scale;
        state.scale = newScale;
        applyViewTransform(canvas);
      },
      { passive: false }
    );

    function commitEdgeAmount(input) {
      const label = input.closest(".canvas-edge-label");
      const canvas = input.closest(".canvas");
      if (!label || !canvas) return;
      const key = toggleKeyForEdge(label.dataset.edgeId);
      const editWrap = label.querySelector(".edit-" + key);
      // Enter's keydown handler and the blur-triggered "change" event can
      // both fire for one commit -- the second call is a no-op rather than
      // a second undo step, detected by the edit box already being closed.
      if (editWrap && editWrap.classList.contains("hidden")) return;
      pushUndo(canvas);
      const amount = parseFloat(input.value) || 0;
      const view = label.querySelector(".view-" + key);
      if (view) view.textContent = formatPeso(amount);
      if (editWrap) toggleEditMode(key);
      markDirty(canvas);
      schedulePreview(canvas);
    }

    document.addEventListener("change", (evt) => {
      if (!evt.target.matches('[data-role="edge-amount"]')) return;
      commitEdgeAmount(evt.target);
    });

    document.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      if (!evt.target.matches('[data-role="edge-amount"]')) return;
      evt.preventDefault();
      commitEdgeAmount(evt.target);
      evt.target.blur();
    });
  }

  initCashflowCanvases();
})();
