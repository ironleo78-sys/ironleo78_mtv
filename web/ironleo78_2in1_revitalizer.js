// IronLeo78 2in1 Revitalizer: "Upload latent / conditioning files" button.
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "IronLeo78_2in1_Revitalizer";
const TAG = "[uploaded] ";

async function refreshLists(node) {
  const r = await api.fetchApi("/object_info/" + NODE);
  const info = (await r.json())[NODE].input.required;
  for (const [name, spec] of [["latent", info.latent], ["conditioning", info.conditioning]]) {
    const w = node.widgets?.find((x) => x.name === name);
    if (w) w.options.values = spec[0];
  }
}

async function upload(node, files) {
  const body = new FormData();
  for (const f of files) body.append("file", f, f.name);
  let result;
  try {
    const resp = await api.fetchApi("/ironleo78/revitalizer/upload", { method: "POST", body });
    if (!resp.ok) throw new Error(resp.status + " " + resp.statusText);
    result = await resp.json();
  } catch (e) {
    alert("2in1 Revitalizer upload failed: " + e);
    return;
  }
  await refreshLists(node);
  const latent = node.widgets.find((w) => w.name === "latent");
  const cond = node.widgets.find((w) => w.name === "conditioning");
  const video = result.saved.find((n) => n.endsWith("_video.latent"));
  const conditioning = result.saved.find((n) => n.endsWith(".conditioning"));
  if (video) latent.value = TAG + video;
  if (conditioning) cond.value = TAG + conditioning;
  node.setDirtyCanvas(true, true);
  const notes = [];
  if (result.refused.length) notes.push("Not accepted (only .latent and .conditioning files): " + result.refused.join(", "));
  if (result.saved.length && !video) notes.push("No _video.latent among the files: pick the latent in the list.");
  if (notes.length) alert("2in1 Revitalizer\n" + notes.join("\n"));
}

function pick(node) {
  const input = document.createElement("input");
  input.type = "file";
  input.multiple = true;
  input.accept = ".latent,.conditioning";
  input.onchange = () => { if (input.files.length) upload(node, [...input.files]); };
  input.click();
}

app.registerExtension({
  name: "IronLeo78.2in1Revitalizer",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created ? created.apply(this, arguments) : undefined;
      this.addWidget("button", "Upload latent / conditioning files...", null, () => pick(this));
      return r;
    };
  },
});
