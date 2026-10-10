// Optional features. Each module registers itself with defineFeature().
// To add one: create features/<name>.js, import it here, and (optionally) toggle it in
// site/site.config.json → "features": { "<name>": false }.
import "./recolor.js";
import "./compose.js";
