// Tiny DOM builder. Text is always inserted as text nodes, so library data can never inject HTML.
const SVG_NS = "http://www.w3.org/2000/svg";

function apply(el, props) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.setAttribute("class", Array.isArray(value) ? value.filter(Boolean).join(" ") : value);
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, String(v));
        else el.style[prop] = v;
      }
    }
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "ref" && typeof value === "function") value(el);
    else if (key in el && !(el instanceof SVGElement) && typeof value !== "string") el[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** h("div", {class: "x", onClick}, "text", otherNode) */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props instanceof Node || typeof props !== "object" || Array.isArray(props)) children.unshift(props);
  else apply(el, props);
  append(el, children);
  return el;
}

/** SVG element builder with the same signature as h(). */
export function s(tag, props, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  if (props instanceof Node || typeof props !== "object" || Array.isArray(props)) children.unshift(props);
  else apply(el, props);
  append(el, children);
  return el;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export function mount(el, ...children) {
  clear(el);
  append(el, children);
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);
