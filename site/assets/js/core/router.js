// Hash router: works on GitHub Pages project sites and local static servers without rewrites.
// Paths look like "#/figure/forest-ci?tab=svg".
export function parseHash(hash = location.hash) {
  const raw = hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { path: path || "/", query: new URLSearchParams(query) };
}

export function compile(pattern) {
  const keys = [];
  const regex = new RegExp("^" + pattern.replace(/\/:([a-zA-Z]+)/g, (_, key) => { keys.push(key); return "/([^/]+)"; }) + "/?$");
  return (path) => {
    const match = regex.exec(path);
    if (!match) return null;
    return Object.fromEntries(keys.map((k, i) => [k, decodeURIComponent(match[i + 1])]));
  };
}

export function href(path, query) {
  const q = query && [...new URLSearchParams(query)].length ? "?" + new URLSearchParams(query).toString() : "";
  return "#" + path + q;
}

export function navigate(path, query) {
  location.hash = href(path, query).slice(1);
}

/** Update query parameters without adding history entries or re-rendering. */
export function replaceQuery(query) {
  const { path } = parseHash();
  const url = new URL(location.href);
  url.hash = href(path, query).slice(1);
  history.replaceState(history.state, "", url);
}
