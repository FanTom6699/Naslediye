const MAP_SIZE = 25;
const CELL_PX = 26;

const mapEl = document.getElementById("map");
const infoEl = document.getElementById("objectInfo");
const statusEl = document.getElementById("statusLine");
const attackBtn = document.getElementById("attackBtn");
const scoutBtn = document.getElementById("scoutBtn");
const gatherBtn = document.getElementById("gatherBtn");

let objects = [];
let selected = null;

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

async function loadObjects() {
  const response = await fetch("./world_objects.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("Не удалось загрузить объекты карты");
  }
  const payload = await response.json();
  objects = Array.isArray(payload.objects) ? payload.objects : [];
}

function clampCoord(value) {
  const n = Number(value);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(MAP_SIZE - 1, n));
}

function objectCssType(type) {
  if (type === "castle" || type === "village" || type === "resource") {
    return type;
  }
  return "resource";
}

function renderMap() {
  mapEl.innerHTML = "";

  objects.forEach((obj) => {
    const x = clampCoord(obj.x);
    const y = clampCoord(obj.y);

    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = `object ${objectCssType(obj.type)}`;
    marker.style.left = `${x * CELL_PX + CELL_PX / 2}px`;
    marker.style.top = `${y * CELL_PX + CELL_PX / 2}px`;
    marker.title = `${obj.name || "Объект"} (${x}, ${y})`;

    marker.addEventListener("click", () => {
      selectObject(obj, marker);
    });

    mapEl.appendChild(marker);
  });
}

function clearSelectionState() {
  mapEl.querySelectorAll(".object.selected").forEach((node) => {
    node.classList.remove("selected");
  });
}

function selectObject(obj, markerEl) {
  clearSelectionState();
  markerEl.classList.add("selected");
  selected = {
    id: obj.id,
    name: obj.name || "Неизвестный объект",
    type: obj.type || "unknown",
    owner: obj.owner || "нейтральный",
    resource: obj.resource || "-",
    amount: Number(obj.amount || 0),
    x: clampCoord(obj.x),
    y: clampCoord(obj.y),
  };

  infoEl.innerHTML = [
    `<strong>${selected.name}</strong>`,
    `Тип: ${selected.type}`,
    `Координаты: (${selected.x}, ${selected.y})`,
    `Владелец: ${selected.owner}`,
    `Ресурс: ${selected.resource}`,
    `Количество: ${selected.amount}`,
  ].join("<br>");

  attackBtn.disabled = false;
  scoutBtn.disabled = false;
  gatherBtn.disabled = false;
  statusEl.textContent = "Статус: объект выбран";
}

function sendAction(action) {
  if (!selected) {
    statusEl.textContent = "Статус: сначала выберите объект";
    return;
  }

  const payload = {
    action,
    x: selected.x,
    y: selected.y,
  };

  if (tg) {
    tg.sendData(JSON.stringify(payload));
    statusEl.textContent = `Статус: отправлено (${action})`;
  } else {
    statusEl.textContent = `Статус: demo-режим, payload=${JSON.stringify(payload)}`;
  }
}

attackBtn.addEventListener("click", () => sendAction("attack"));
scoutBtn.addEventListener("click", () => sendAction("scout"));
gatherBtn.addEventListener("click", () => sendAction("gather"));

(async () => {
  try {
    await loadObjects();
    renderMap();
  } catch (error) {
    statusEl.textContent = `Статус: ошибка загрузки (${error.message})`;
  }
})();
