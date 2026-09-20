const GITHUB_RAW_BASE =
  "https://raw.githubusercontent.com/kedi-lang/registry/main/generated/v1";
const REGISTRY_REPOSITORY = "https://github.com/kedi-lang/registry";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);
const dataBase = LOCAL_HOSTS.has(window.location.hostname) ? "/v1" : GITHUB_RAW_BASE;

const app = document.querySelector("#app");

const themeButton = document.querySelector("#theme-toggle");
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  if (themeButton) {
    themeButton.textContent = theme === "dark" ? "Light" : "Dark";
    themeButton.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
  }
}
let initialTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
try { initialTheme = localStorage.getItem("registry-theme") || initialTheme; } catch {}
applyTheme(initialTheme);
themeButton?.addEventListener("click", () => {
  const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  applyTheme(theme);
  try { localStorage.setItem("registry-theme", theme); } catch {}
});

const icons = {
  search: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path>
    </svg>`,
  copy: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <rect width="14" height="14" x="8" y="8" rx="2"></rect>
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"></path>
    </svg>`,
  check: `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="m20 6-11 11-5-5"></path>
    </svg>`,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function packageRoute() {
  const match = window.location.pathname.match(/^\/package\/([^/]+)\/?$/);
  if (!match) return null;
  const name = decodeURIComponent(match[1]);
  return /^[a-z][a-z0-9_]*$/.test(name) ? name : "";
}

async function fetchJson(path) {
  const response = await fetch(`${dataBase}/${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const error = new Error(`Registry returned ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function statusPill(status) {
  const normalized = ["active", "superseded", "yanked", "revoked"].includes(status)
    ? status
    : "unknown";
  return `<span class="status-pill status-${normalized}">${escapeHtml(normalized)}</span>`;
}

function searchMarkup() {
  return `
    <form class="search-form" role="search">
      <label class="sr-only" for="package-search">Search packages</label>
      ${icons.search}
      <input id="package-search" type="search" autocomplete="off"
        placeholder="Search packages by name, description or author" aria-controls="package-results" />
      <button type="submit">Search</button>
    </form>`;
}

function heroMarkup() {
  return `
    <section class="registry-hero">
      <div class="registry-hero-inner">
        <div>
          <p class="eyebrow">The Kedi Package Index</p>
          <h1>A home for your packages.</h1>
          <p class="hero-copy">
            Find something useful. Share something you made.<br />
            Little building blocks for your next Kedi program.
          </p>
        </div>
        <div class="depot-scene" aria-hidden="true">
          <div class="parcel parcel-one"><span class="parcel-stamp">KEDI</span></div>
          <div class="parcel parcel-two"></div>
          <img class="depot-cat" src="/assets/cat.webp" alt="" />
        </div>
      </div>
    </section>`;
}

function catalogSidebar(packages) {
  const counts = { all: packages.length };
  for (const status of ["active", "yanked", "revoked"]) {
    counts[status] = packages.filter((pkg) => pkg.status === status).length;
  }
  const authors = new Set(packages.map((pkg) => pkg.author?.name || pkg.author)).size;
  return `<aside class="registry-sidebar" aria-label="Catalog navigation">
    <section>
      <h2 class="rail-heading">Browse the index</h2>
      <nav class="filter-links" aria-label="Filter packages by status">
        ${Object.entries({ all: "All packages", active: "Active", yanked: "Yanked", revoked: "Revoked" })
          .map(([status, label]) => `<button type="button" data-status="${status}" aria-pressed="${status === "all"}">
            <span>${label}</span><span class="rail-count">${counts[status]}</span></button>`).join("")}
      </nav>
    </section>
    <section class="rail-section">
      <h2 class="rail-heading">For package authors</h2>
      <a href="${REGISTRY_REPOSITORY}/blob/main/README.md#register-a-package">Register a package</a>
      <a href="${REGISTRY_REPOSITORY}/pulls">Review submissions</a>
      <a href="${REGISTRY_REPOSITORY}/blob/main/schemas/package-manifest-v1.schema.json">Manifest reference</a>
    </section>
    <section class="rail-section index-facts">
      <h2 class="rail-heading">In the registry</h2>
      <dl><div><dt>Packages</dt><dd>${packages.length}</dd></div>
        <div><dt>Authors</dt><dd>${authors}</dd></div></dl>
      <p>Built in the open.<br /><a href="${REGISTRY_REPOSITORY}">Explore the source</a></p>
    </section>
  </aside>`;
}

function contributionMarkup() {
  return `<section class="contribution" id="contribute" aria-labelledby="contribute-heading">
    <div>
      <p class="eyebrow">Made something useful?</p>
      <h2 id="contribute-heading">There's room on the shelf.</h2>
      <p>Share a package through a registry pull request. Each release points to a reviewed commit.</p>
      <a class="text-link" href="${REGISTRY_REPOSITORY}/blob/main/README.md#register-a-package">Submit your package <span aria-hidden="true">&rarr;</span></a>
    </div>
    <div class="submission-files" aria-label="Package submission files">
      <div class="file-caption">packages/your_package/</div>
      <dl><div><dt>manifest.json</dt><dd>The package record</dd></div>
        <div><dt>README.md</dt><dd>What it does</dd></div>
        <div><dt>LICENSE</dt><dd>How it can be used</dd></div></dl>
    </div>
  </section>`;
}

function packageRow(pkg) {
  const author = typeof pkg.author === "object" ? pkg.author?.name : pkg.author;
  return `
    <a class="package-row" href="/package/${encodeURIComponent(pkg.name)}">
      <span class="package-identity">
        <span class="package-name">${escapeHtml(pkg.name)}</span>
        <span class="package-author">by ${escapeHtml(author || "Unknown")}</span>
      </span>
      <span class="package-description">${escapeHtml(pkg.description)}</span>
      <span class="package-version">${escapeHtml(pkg.version)}</span>
      ${statusPill(pkg.status)}
    </a>`;
}

function packageListMarkup(packages, searching = false) {
  if (!packages.length) {
    return `
      <div class="empty-state">
        <div><strong>${searching ? "No matching packages." : "The first shelf is ready."}</strong>
          ${searching ? 'Try a different search or <button type="button" id="reset-filters">clear the filters</button>.' : 'Be the first to <a href="#contribute">share a Kedi package</a>.'}</div>
      </div>`;
  }
  return `
    <div class="package-column-labels" aria-hidden="true">
      <span>Package / author</span><span>Description</span><span>Version</span><span>Status</span>
    </div>
    <div id="package-list" class="package-list">${packages.map(packageRow).join("")}</div>`;
}

async function renderCatalog() {
  document.title = "kedi registry";
  try {
    const index = await fetchJson("index.json");
    const packages = Array.isArray(index.packages) ? index.packages : [];
    const state = { status: "all", letter: "all", sort: "asc" };
    app.innerHTML = `
      <div class="registry-shell">
        ${catalogSidebar(packages)}
        <div class="registry-content">
          ${heroMarkup()}
          ${searchMarkup()}
          <section class="catalog" aria-labelledby="packages-heading">
            <div class="catalog-heading">
              <h2 id="packages-heading">Browse packages <span id="registry-counts" class="registry-counts">${packages.length}</span></h2>
              <label class="sort-label">Sort <select id="package-sort"><option value="asc">Name: A to Z</option><option value="desc">Name: Z to A</option></select></label>
            </div>
            <nav class="alphabet" aria-label="Filter by first letter">
              <button type="button" data-letter="all" aria-pressed="true">All</button>
              ${"abcdefghijklmnopqrstuvwxyz".split("").map((letter) => `<button type="button" data-letter="${letter}" aria-pressed="false" ${packages.some((pkg) => pkg.name.startsWith(letter)) ? "" : "disabled"}>${letter.toUpperCase()}</button>`).join("")}
            </nav>
            <div id="package-results">${packageListMarkup(packages)}</div>
            <div class="index-note"><span id="result-summary" role="status"></span><span>Exact commits, every install.</span></div>
          </section>
          ${contributionMarkup()}
        </div>
      </div>`;

    const search = document.querySelector("#package-search");
    const results = document.querySelector("#package-results");
    const counts = document.querySelector("#registry-counts");
    const update = () => {
      const query = search.value.trim().toLocaleLowerCase();
      const filtered = packages.filter((pkg) => {
        if (state.status !== "all" && pkg.status !== state.status) return false;
        if (state.letter !== "all" && !pkg.name.startsWith(state.letter)) return false;
        const author = typeof pkg.author === "object" ? pkg.author?.name : pkg.author;
        return [pkg.name, pkg.description, author]
          .filter(Boolean)
          .some((value) => String(value).toLocaleLowerCase().includes(query));
      }).sort((a, b) => a.name.localeCompare(b.name) * (state.sort === "desc" ? -1 : 1));
      results.innerHTML = packageListMarkup(filtered, Boolean(query || state.status !== "all" || state.letter !== "all"));
      counts.textContent = filtered.length;
      document.querySelector("#result-summary").textContent = `Showing ${filtered.length} of ${packages.length} packages`;
      document.querySelectorAll("[data-status]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.status === state.status)));
      document.querySelectorAll("[data-letter]").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.letter === state.letter)));
      document.querySelector("#reset-filters")?.addEventListener("click", () => {
        search.value = "";
        state.status = "all";
        state.letter = "all";
        update();
      });
    };
    search.addEventListener("input", update);
    document.querySelector(".search-form").addEventListener("submit", (event) => { event.preventDefault(); update(); });
    document.querySelectorAll("[data-status]").forEach((button) => button.addEventListener("click", () => { state.status = button.dataset.status; update(); }));
    document.querySelectorAll("[data-letter]").forEach((button) => button.addEventListener("click", () => { state.letter = button.dataset.letter; update(); }));
    document.querySelector("#package-sort").addEventListener("change", (event) => {
      state.sort = event.target.value;
      update();
    });
    update();
  } catch (error) {
    renderFailure("The package shelves could not be loaded.", error);
  }
}

function repositoryCommitUrl(record) {
  const repository = safeHttpUrl(record.repository);
  return repository
    ? `${repository.replace(/\.git\/?$/, "").replace(/\/$/, "")}/commit/${record.verified_commit}`
    : null;
}

function registryFileUrl(name, filename) {
  return `${REGISTRY_REPOSITORY}/blob/main/packages/${encodeURIComponent(name)}/${filename}`;
}

function metadataLink(label, value, url) {
  const content = url
    ? `<a href="${escapeHtml(url)}" rel="noreferrer">${escapeHtml(value)}</a>`
    : escapeHtml(value);
  return `<div><dt>${escapeHtml(label)}</dt><dd>${content}</dd></div>`;
}

function withdrawalMarkup(record) {
  if (record.status !== "yanked" && record.status !== "revoked") return "";
  const wording =
    record.status === "revoked"
      ? "This exact package revision has been revoked and cannot be installed."
      : "This package revision has been yanked and is no longer available for new installs.";
  return `<div class="withdrawal-notice ${record.status}"><strong>${escapeHtml(
    record.status.toUpperCase(),
  )}</strong> ${wording}</div>`;
}

async function copyInstallCommand(button, command) {
  await navigator.clipboard.writeText(command);
  button.innerHTML = icons.check;
  button.setAttribute("aria-label", "Copied");
  window.setTimeout(() => {
    button.innerHTML = icons.copy;
    button.setAttribute("aria-label", "Copy install command");
  }, 1600);
}

function renderPackage(record, details = null) {
  const author = typeof record.author === "object" ? record.author : { name: record.author };
  const repository = safeHttpUrl(record.repository);
  const commitUrl = repositoryCommitUrl(record);
  const installCommand = `kedi add ${record.name}`;
  const readmeUrl = safeHttpUrl(details?.readme_url) || registryFileUrl(record.name, "README.md");
  const licenseUrl = safeHttpUrl(details?.license_url) || registryFileUrl(record.name, "LICENSE");
  const manifestUrl = safeHttpUrl(details?.package_manifest_url);
  const classifiers = details?.python_classifiers || [];
  const dependencies = details?.python_dependencies || [];
  const notDeclared = details ? "Not declared" : "Unavailable";
  const installMarkup =
    record.status === "active"
      ? `<div class="install-strip">
          <code class="install-command">${escapeHtml(installCommand)}</code>
          <button class="copy-button" type="button" aria-label="Copy install command"
            title="Copy install command">${icons.copy}</button>
        </div>`
      : withdrawalMarkup(record);

  document.title = `${record.name} · kedi registry`;
  app.innerHTML = `
    <div class="registry-shell package-shell">
    <aside class="registry-sidebar" aria-label="Package navigation">
      <a class="back-link" href="/">&larr; All packages</a>
      <section class="rail-section">
        <h2 class="rail-heading">This package</h2>
        <a href="#installation">Installation</a>
        <a href="#description">Project description</a>
        <a href="#verified-source">Verified source</a>
        <a href="#package-files">Package files</a>
      </section>
      <details class="package-sidebar-details" ${window.matchMedia("(min-width: 801px)").matches ? "open" : ""}>
        <summary>Package information</summary>
        <section class="rail-section">
          <h2 class="rail-heading">Project links</h2>
          ${repository ? `<a href="${escapeHtml(repository)}">Source repository</a>` : ""}
          <a href="${escapeHtml(readmeUrl)}">README on GitHub</a>
          ${manifestUrl ? `<a href="${escapeHtml(manifestUrl)}">package.kedi</a>` : ""}
        </section>
        <section class="rail-section" aria-label="Package metadata">
          <h2 class="rail-heading">Metadata</h2>
          <dl class="metadata">
            ${metadataLink("Author", author?.name || "Unknown", null)}
            ${metadataLink("Contact", author?.contact || "Not declared", null)}
            ${metadataLink("License", details?.license || notDeclared, details?.license ? licenseUrl : null)}
            ${metadataLink("Version", record.version, null)}
            ${metadataLink("Source directory", details?.source_directory || notDeclared, manifestUrl)}
          </dl>
        </section>
        <section class="rail-section" aria-label="Supported languages">
          <h2 class="rail-heading">Languages</h2>
          <ul class="classifiers">
            <li>Kedi</li>
            ${classifiers.map((item, index) => `<li class="${index > 0 && classifiers.length > 1 ? "classifier-version" : ""}">${escapeHtml(item)}</li>`).join("")}
          </ul>
          <p class="metadata-note">${details?.python_requirement ? `Declared support: <code>${escapeHtml(details.python_requirement.replace(/^python@/, ""))}</code>` : `Python support: ${notDeclared.toLowerCase()}`}</p>
        </section>
        <section class="rail-section" aria-label="Python dependencies">
          <h2 class="rail-heading">Python dependencies</h2>
          ${dependencies.length ? `<ul class="dependency-list">${dependencies.map((item) => `<li><code>${escapeHtml(item)}</code></li>`).join("")}</ul>` : `<p class="metadata-note">${notDeclared}</p>`}
        </section>
        <details class="provenance"><summary>Registry provenance</summary><dl class="metadata">
          ${metadataLink("Registry revision", record.registry_revision, null)}
          ${metadataLink("Record digest", record.registry_manifest_digest, null)}
        </dl></details>
      </details>
    </aside>
    <article class="detail-page registry-content">
      <nav class="breadcrumbs" aria-label="Breadcrumb">
        <a href="/">Registry</a><span aria-hidden="true">/</span>
        <span>${escapeHtml(record.name)}</span>
      </nav>

      <header class="package-titlebar" id="overview">
        <div>
          <h1>${escapeHtml(record.name)}</h1>
          <p>${escapeHtml(record.description)}</p>
        </div>
        <div>
          ${statusPill(record.status)}
          <div class="package-version-large">v${escapeHtml(record.version)}</div>
        </div>
      </header>

      <section id="installation" class="installation-section" aria-label="Installation">
        ${installMarkup}
        ${record.status === "active" ? `<p class="import-line">Then use it in your program: <code>&gt; import: ${escapeHtml(record.name)}</code></p>` : ""}
      </section>

      <section class="detail-section readme-section" id="description" aria-label="Project description">
        <h2 class="section-label">Project description</h2>
        ${details ? `<div class="readme-content">${details.readme_html}</div>` : `<p class="metadata-unavailable" role="status">Package documentation and metadata could not be loaded. <a href="">Retry</a> or <a href="${escapeHtml(readmeUrl)}">read the README on GitHub</a>.</p>`}
      </section>
          <section class="detail-section" id="verified-source">
            <h2 class="section-label">Verified source</h2>
            <p>
              This release resolves to one reviewed commit. Kedi installs that exact revision,
              not the repository's moving HEAD.
            </p>
            ${
              commitUrl
                ? `<a class="commit-block" href="${escapeHtml(commitUrl)}" rel="noreferrer">
                    <span>${escapeHtml(record.verified_commit)}</span>
                  </a>`
                : `<div class="commit-block"><span>${escapeHtml(record.verified_commit)}</span></div>`
            }
          </section>
          <section class="detail-section" id="package-files">
            <h2 class="section-label">Package files</h2>
            <div class="file-list">
              <a href="${escapeHtml(readmeUrl)}"><code>README.md</code><span>Documentation &amp; examples</span><span aria-hidden="true">&nearr;</span></a>
              <a href="${escapeHtml(licenseUrl)}"><code>LICENSE</code><span>${escapeHtml(details?.license || "Package license")}</span><span aria-hidden="true">&nearr;</span></a>
              <a href="${registryFileUrl(record.name, "manifest.json")}"><code>manifest.json</code><span>Reviewed registry record</span><span aria-hidden="true">&nearr;</span></a>
            </div>
          </section>
    </article>
    </div>`;

  const copyButton = document.querySelector(".copy-button");
  copyButton?.addEventListener("click", () => copyInstallCommand(copyButton, installCommand));
}

async function renderPackageRoute(name) {
  if (!name) {
    renderNotFound("That package name is not valid.");
    return;
  }
  try {
    const record = await fetchJson(`package/${encodeURIComponent(name)}.json`);
    let details = null;
    try {
      const candidate = await fetchJson(`details/${encodeURIComponent(name)}.json`);
      if (
        candidate.schema_version === 1 && candidate.name === record.name &&
        candidate.version === record.version && candidate.verified_commit === record.verified_commit &&
        candidate.registry_revision === record.registry_revision && typeof candidate.readme_html === "string"
      ) details = candidate;
    } catch {
      // A missing publication asset must not hide the install record.
    }
    renderPackage(record, details);
  } catch (error) {
    if (error.status === 404) {
      renderNotFound(`No package named “${name}” lives here.`);
      return;
    }
    renderFailure("This package could not be loaded.", error);
  }
}

function renderNotFound(message) {
  document.title = "Package not found · kedi registry";
  app.innerHTML = `
    <section class="detail-page">
      <nav class="breadcrumbs"><a href="/">Registry</a><span>/</span><span>Not found</span></nav>
      <div class="error-state">
        <div><strong>Empty box.</strong>${escapeHtml(message)} <a href="/">Browse the depot.</a></div>
      </div>
    </section>`;
}

function renderFailure(message, error) {
  console.error(error);
  app.innerHTML = `
    <section class="detail-page">
      <div class="error-state">
        <div><strong>${escapeHtml(message)}</strong>Check the registry connection and try again.</div>
      </div>
    </section>`;
}

const packageName = packageRoute();
if (packageName === null) {
  renderCatalog();
} else {
  renderPackageRoute(packageName);
}
