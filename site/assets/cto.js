const el = id => document.getElementById(id);
const vocabulary = {
  Components: 'Interior wall|Ceiling|Floor|Skirting board|Façade|Roof covering|Gutter|Downpipe|Window frame|Window pane|Door leaf|Door frame|Fixed worktop|Shower hose|Shower tray|Toilet bowl|Accessible pipe|Pipe joint|Safety valve|Floor drain',
  'Materials and finishes': 'Gypsum plaster|Cement render|Painted finish|Wallpaper|Plasterboard|Concrete|Brick|Mortar|Ceramic tile|Grout|Silicone sealant|Solid wood|Parquet|Laminate|Vinyl flooring|Composite worktop|Glass|Metal|Plastic|Bituminous membrane',
  Manifestations: 'Crack|Chip|Puncture|Scratch|Dent|Fracture|Missing piece|Surface detachment|Coating flaking|Blistering|Swelling|Warping|Erosion|Corrosion|Discolouration|Surface deposit|Charred surface|Melted surface|Crushed surface|Component displacement',
  'Water and moisture': 'Water droplets|Visible water stream|Standing water|Wet sheen|Wet–dry boundary|Tide mark|Drip streak|Floor-level moisture band|Ceiling stain|Stain beneath window|Stain beside pipe joint|Stain along sealant|Dark speckling|Fuzzy surface growth|White crystalline deposit|Swollen board edge|Raised flooring seam|Lifted veneer|Water at drain opening|Silt residue',
  'Fracture and impact': 'Hairline crack|Open crack|Diagonal crack|Horizontal crack|Vertical crack|Stepped crack|Branching crack|Radial crack|Crack through tile body|Crack along grout joint|Crack ending at opening corner|Offset across crack|Multiple parallel cracks|Edge chip pattern|Clustered impact marks|Punctured roof tile|Missing roof tile|Shattered glazing pattern|Bent frame|Localised pry-like marks',
  Context: 'Interior|Exterior|Ceiling–wall junction|Wall–floor junction|Room corner|Window reveal|Door threshold|Junction of two materials|Adjacent to drain|Adjacent to fixture|Adjacent to pipe penetration|Below roof edge|Below gutter|Repeated on adjacent components|Confined to joint|Spread across joints|Partly out of frame|Partly obstructed|Prior patch visible|Measurement reference visible'
};

function renderFeatures() {
  const query = el('search').value.trim().toLowerCase();
  const groups = Object.entries(vocabulary);
  el('feature-count').textContent = groups.reduce((count, [, entries]) => count + entries.split('|').length, 0);
  const cards = [];
  for (const [group, entries] of groups) {
    const matching = entries.split('|').filter(label => group.toLowerCase().includes(query) || label.toLowerCase().includes(query));
    if (!matching.length) continue;
    const card = document.createElement('article');
    const title = document.createElement('h3');
    title.textContent = group;
    const list = document.createElement('ul');
    for (const label of matching) {
      const item = document.createElement('li');
      item.textContent = label;
      list.append(item);
    }
    card.append(title, list);
    cards.push(card);
  }
  el('features').replaceChildren(...cards);
  if (!cards.length) el('features').textContent = 'No matching labels.';
}

function button(label, container, onClick) {
  const node = document.createElement('button');
  node.type = 'button';
  node.textContent = label;
  node.setAttribute('aria-pressed', 'false');
  node.addEventListener('click', () => onClick(node));
  container.append(node);
  return node;
}

function select(node, container) {
  for (const item of container.children) item.setAttribute('aria-pressed', String(item === node));
}

async function readJSON(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

const handoffs = {
  ceiling_stain: 'The visible stain and crack can guide review. Verify the water source and event timing from other evidence before applying a Leitungswasser clause.',
  dark_corner: 'The dark line needs a sharp close-up. Keep the material, cause and any mould identification unresolved.',
  clean_wall: 'No damage is recorded in the visible area. A wider photo can establish whether other surfaces were in view.'
};

function renderCase(example, result) {
  el('case-image').src = example.image;
  el('case-image').alt = example.title;
  el('verdict').textContent = {yes: 'Visible damage', no: 'No damage in the visible area', unclear: 'Damage unclear'}[result.damage_present];
  el('handoff').textContent = handoffs[result.image_id];
  el('json').textContent = JSON.stringify(result, null, 2);
  el('download').href = example.result;
  const controls = el('findings');
  const overlay = el('overlay');
  controls.replaceChildren();
  overlay.replaceChildren();
  el('readout').textContent = result.limitations.join(' ') || 'Select an evidence region to inspect its attributes.';
  for (const finding of result.findings) {
    const label = finding.damage_type.replaceAll('_', ' ');
    button(label, controls, node => {
      select(node, controls);
      overlay.replaceChildren();
      if (finding.bbox && result.width && result.height) {
        const [x, y, width, height] = finding.bbox;
        const box = document.createElement('span');
        box.style.left = `${x / result.width * 100}%`;
        box.style.top = `${y / result.height * 100}%`;
        box.style.width = `${width / result.width * 100}%`;
        box.style.height = `${height / result.height * 100}%`;
        overlay.append(box);
      }
      const material = finding.material || 'unknown';
      el('readout').textContent = `${label} on ${finding.component}, ${finding.location}. Material ${material}. Evidence ${finding.visible_traits.join(', ')}. Status ${finding.status}, ${finding.uncertain ? 'uncertain' : 'no uncertainty flagged'}.`;
    });
  }
  controls.firstElementChild?.click();
}

async function loadExamples() {
  try {
    const examples = await readJSON('examples/index.json');
    const records = await Promise.all(examples.map(example => readJSON(example.result)));
    const tabs = el('cases');
    examples.forEach((example, index) => {
      button(example.title, tabs, node => {
        select(node, tabs);
        renderCase(example, records[index]);
      });
    });
    tabs.firstElementChild?.click();
  } catch {
    el('demo-status').textContent = 'The bundled examples could not load. Open this page from a web server.';
  }
}

async function loadMetrics() {
  try {
    const metrics = await readJSON('data/metrics.json');
    if (!Number.isInteger(metrics.images_evaluated) || metrics.images_evaluated < 1) throw new Error('No evaluation sample');
    el('metrics').textContent = `Published evaluation report · ${metrics.images_evaluated} evaluated images.`;
    el('report-data').textContent = JSON.stringify(metrics, null, 2);
    el('report').hidden = false;
  } catch {
    el('metrics').textContent = 'No scored evaluation report is published. The example cases illustrate the output format.';
  }
}

el('search').addEventListener('input', renderFeatures);
renderFeatures();
loadExamples();
loadMetrics();
