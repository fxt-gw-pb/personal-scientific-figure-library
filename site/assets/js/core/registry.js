/*
 * Feature registry — the extension point of the site.
 *
 * A feature is a plain object registered with defineFeature():
 *   {
 *     id: "recolor",                       // also the key in site.config.json → features
 *     nav: { path, label, icon, order, badge(ctx) },   // optional top-bar link
 *     routes: [{ path: "/figure/:id/recolor", title, render(ctx, params) → Node | Promise<Node> }],
 *     entryActions: [{ id, label, icon, primary, when(entry, ctx), run(entry, ctx) }],
 *     detailSections: [{ id, order, render(entry, ctx) → Node | null }],
 *     cardActions: [{ id, label, icon, when(entry, ctx), run(entry, ctx) }],
 *     setup(ctx)                           // optional, called once after data loads
 *   }
 * Add a file under features/, import it in features/index.js, done.
 */
const features = [];

export function defineFeature(feature) {
  if (!feature?.id) throw new Error("feature needs an id");
  if (features.some((f) => f.id === feature.id)) throw new Error(`duplicate feature ${feature.id}`);
  features.push(feature);
  return feature;
}

let enabledFilter = () => true;
export function setEnabled(predicate) { enabledFilter = predicate; }

const active = () => features.filter((f) => enabledFilter(f));
export const allFeatures = () => active();
export const routes = () => active().flatMap((f) => (f.routes || []).map((r) => ({ ...r, feature: f.id })));
export const navItems = () => active().filter((f) => f.nav).map((f) => ({ ...f.nav, feature: f.id })).sort((a, b) => (a.order ?? 50) - (b.order ?? 50));
export const entryActions = (entry, ctx) => active().flatMap((f) => f.entryActions || []).filter((a) => !a.when || a.when(entry, ctx));
export const cardActions = (entry, ctx) => active().flatMap((f) => f.cardActions || []).filter((a) => !a.when || a.when(entry, ctx));
export const detailSections = () => active().flatMap((f) => f.detailSections || []).sort((a, b) => (a.order ?? 50) - (b.order ?? 50));
