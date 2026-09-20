const DATA_BASE = "https://raw.githubusercontent.com/kedi-lang/registry/main/generated/v1";
const CACHE_PREFIX = "kedi-registry:github-v1:";
const RESOURCE_PATH = /^(index\.json|(?:package|details)\/[a-z][a-z0-9_]*\.json)$/;

function browserStorage() {
  try { return globalThis.localStorage; } catch { return null; }
}

function validResource(data, path, revision) {
  if (!data || data.schema_version !== 1 || data.registry_revision !== revision) return false;
  if (path === "index.json") return Array.isArray(data.packages);
  const name = path.split("/")[1].slice(0, -5);
  if (data.name !== name || typeof data.version !== "string" || typeof data.verified_commit !== "string") return false;
  if (path.startsWith("details/")) {
    return typeof data.readme_html === "string" &&
      Array.isArray(data.python_classifiers) && Array.isArray(data.python_dependencies);
  }
  return ["active", "yanked", "revoked"].includes(data.status);
}

export function createRegistryClient({ fetcher = globalThis.fetch, storage = browserStorage() } = {}) {
  let revisionPromise;
  const pending = new Map();

  async function request(path, options) {
    const response = await fetcher(`${DATA_BASE}/${path}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(15000),
      ...options,
    });
    if (!response.ok) {
      const error = new Error(`Registry returned ${response.status}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }

  function prune(revision) {
    const currentPrefix = `${CACHE_PREFIX}${encodeURIComponent(revision)}/`;
    try {
      for (let i = storage.length - 1; i >= 0; i--) {
        const key = storage.key(i);
        if (key?.startsWith(CACHE_PREFIX) && !key.startsWith(currentPrefix)) storage.removeItem(key);
      }
    } catch { /* Storage can be unavailable or full; network reads still work. */ }
  }

  async function currentRevision() {
    if (!revisionPromise) {
      revisionPromise = request("revision.json", { cache: "no-cache" }).then((data) => {
        if (data?.schema_version !== 1 || typeof data.registry_revision !== "string" ||
            !data.registry_revision.trim() || data.registry_revision.length > 256) {
          throw new Error("Invalid registry revision");
        }
        prune(data.registry_revision);
        return data.registry_revision;
      }).catch((error) => {
        revisionPromise = undefined;
        throw error;
      });
    }
    return revisionPromise;
  }

  async function load(path) {
    for (let attempt = 0; attempt < 2; attempt++) {
      const revision = await currentRevision();
      const key = `${CACHE_PREFIX}${encodeURIComponent(revision)}/${path}`;
      try {
        const cached = JSON.parse(storage.getItem(key));
        if (validResource(cached, path, revision)) return cached;
        storage.removeItem(key);
      } catch { /* Ignore corrupt or inaccessible browser cache entries. */ }

      const data = await request(`${path}?revision=${encodeURIComponent(revision)}`, { cache: "no-store" });
      if (data?.registry_revision !== revision) {
        // A publication can advance between the pointer and content requests.
        revisionPromise = undefined;
        continue;
      }
      if (!validResource(data, path, revision)) throw new Error("Invalid registry data");
      try { storage.setItem(key, JSON.stringify(data)); } catch {}
      return data;
    }
    throw new Error("Registry changed during loading. Please reload.");
  }

  return {
    get(path) {
      if (!RESOURCE_PATH.test(path)) return Promise.reject(new Error("Invalid registry resource"));
      if (!pending.has(path)) {
        const promise = load(path).finally(() => pending.delete(path));
        pending.set(path, promise);
      }
      return pending.get(path);
    },
  };
}
