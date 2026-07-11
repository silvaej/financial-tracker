(function () {
  function nodeBox(node) {
    const x = parseFloat(node.dataset.x) || 0;
    const y = parseFloat(node.dataset.y) || 0;
    const w = node.offsetWidth || 160;
    const h = node.offsetHeight || 70;
    return { x, y, w, h };
  }

  function redrawCanvas(canvas) {
    canvas.querySelectorAll(".canvas-node").forEach((node) => {
      node.style.left = (parseFloat(node.dataset.x) || 0) + "px";
      node.style.top = (parseFloat(node.dataset.y) || 0) + "px";
    });

    canvas.querySelectorAll(".canvas-edge-line").forEach((line) => {
      const from = canvas.querySelector('[data-node-id="' + line.dataset.from + '"]');
      const to = canvas.querySelector('[data-node-id="' + line.dataset.to + '"]');
      if (!from || !to) return;

      const a = nodeBox(from);
      const b = nodeBox(to);
      const x1 = a.x + a.w;
      const y1 = a.y + a.h / 2;
      const x2 = b.x;
      const y2 = b.y + b.h / 2;
      line.setAttribute("x1", x1);
      line.setAttribute("y1", y1);
      line.setAttribute("x2", x2);
      line.setAttribute("y2", y2);

      const label = canvas.querySelector(
        '.canvas-edge-label[data-edge-id="' + line.dataset.edgeId + '"]'
      );
      if (label) {
        label.style.left = (x1 + x2) / 2 + "px";
        label.style.top = (y1 + y2) / 2 + "px";
      }
    });
  }

  function initCashflowCanvases() {
    document.querySelectorAll(".canvas").forEach(redrawCanvas);
  }

  function canvasPoint(canvas, evt) {
    const rect = canvas.getBoundingClientRect();
    return { x: evt.clientX - rect.left, y: evt.clientY - rect.top };
  }

  let dragState = null;

  function onPointerDown(evt) {
    const canvas = evt.target.closest(".canvas");
    if (!canvas) return;

    const handle = evt.target.closest(".canvas-handle");
    if (handle) {
      evt.preventDefault();
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
        sourceNode: handle.closest(".canvas-node"),
        ghost,
      };
      return;
    }

    const node = evt.target.closest(".canvas-node");
    if (node) {
      evt.preventDefault();
      const point = canvasPoint(canvas, evt);
      dragState = {
        mode: "move",
        canvas,
        node,
        offsetX: point.x - (parseFloat(node.dataset.x) || 0),
        offsetY: point.y - (parseFloat(node.dataset.y) || 0),
      };
    }
  }

  function onPointerMove(evt) {
    if (!dragState) return;
    const point = canvasPoint(dragState.canvas, evt);

    if (dragState.mode === "move") {
      dragState.node.dataset.x = Math.max(0, point.x - dragState.offsetX);
      dragState.node.dataset.y = Math.max(0, point.y - dragState.offsetY);
      redrawCanvas(dragState.canvas);
    } else if (dragState.mode === "connect") {
      dragState.ghost.setAttribute("x2", point.x);
      dragState.ghost.setAttribute("y2", point.y);
    }
  }

  function onPointerUp(evt) {
    if (!dragState) return;

    if (dragState.mode === "move") {
      const node = dragState.node;
      fetch(node.dataset.positionUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          x: parseFloat(node.dataset.x) || 0,
          y: parseFloat(node.dataset.y) || 0,
        }),
      });
    } else if (dragState.mode === "connect") {
      dragState.ghost.remove();
      const under = document.elementFromPoint(evt.clientX, evt.clientY);
      const targetNode = under ? under.closest(".canvas-node") : null;
      if (targetNode && targetNode !== dragState.sourceNode) {
        createConnection(dragState.canvas, dragState.sourceNode, targetNode);
      }
    }
    dragState = null;
  }

  function createConnection(canvas, sourceNode, targetNode) {
    const periodId = canvas.dataset.payoutPeriodId;
    const sourceChannelId = sourceNode.dataset.nodeId.split("-")[1];
    const targetId = targetNode.dataset.nodeId.split("-")[1];

    if (targetNode.dataset.nodeKind === "channel") {
      const form = document.getElementById("add-transfer-form-" + periodId);
      form.querySelector('[data-role="new-transfer-from"]').value = sourceChannelId;
      form.querySelector('[data-role="new-transfer-to"]').value = targetId;
      form.querySelector('[data-role="new-transfer-amount"]').value = "0";
      form.requestSubmit();
    } else if (targetNode.dataset.nodeKind === "goal") {
      const form = document.getElementById("add-goal-contribution-form-" + periodId);
      form.querySelector('[data-role="new-contribution-channel"]').value = sourceChannelId;
      form.querySelector('[data-role="new-contribution-goal"]').value = targetId;
      form.querySelector('[data-role="new-contribution-amount"]').value = "0";
      form.requestSubmit();
    }
  }

  if (!window.__cashflowCanvasInit) {
    window.__cashflowCanvasInit = true;
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
    document.body.addEventListener("htmx:afterSettle", initCashflowCanvases);
  }

  initCashflowCanvases();
})();
