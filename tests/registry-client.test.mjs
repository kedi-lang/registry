import assert from "node:assert/strict";
import test from "node:test";
import { createRegistryClient } from "../web/registry-client.mjs";

class MemoryStorage {
  values = new Map();
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
  removeItem(key) { this.values.delete(key); }
}

const index = (revision) => ({ schema_version: 1, registry_revision: revision, packages: [] });
const record = (revision, status = "active") => ({ schema_version: 1, registry_revision: revision, name: "textkit", version: "0.1.0", verified_commit: "a".repeat(40), status });
const details = (revision) => ({ ...record(revision), readme_html: "<p>Real documentation</p>", python_classifiers: ["Python 3.12"], python_dependencies: [] });

function server() {
  const state = { revision: "v1", resources: { "index.json": index("v1"), "package/textkit.json": record("v1"), "details/textkit.json": details("v1") }, requests: [] };
  state.fetcher = async (url, options) => {
    const parsed = new URL(url);
    const path = parsed.pathname.split("/generated/v1/")[1];
    state.requests.push({ url, path, options });
    assert.equal(parsed.origin, "https://raw.githubusercontent.com");
    const data = path === "revision.json" ? { schema_version: 1, registry_revision: state.revision } : state.resources[path];
    return new Response(JSON.stringify(data ?? {}), { status: data ? 200 : 404 });
  };
  return state;
}

test("first load caches content; next page fetches only revision", async () => {
  const remote = server();
  const storage = new MemoryStorage();
  let client = createRegistryClient({ fetcher: remote.fetcher, storage });
  for (const path of Object.keys(remote.resources)) await client.get(path);
  assert.equal(remote.requests.length, 4);
  assert.equal(remote.requests[0].options.cache, "no-cache");
  for (const request of remote.requests.slice(1)) {
    assert.equal(new URL(request.url).searchParams.get("revision"), "v1");
    assert.equal(request.options.cache, "no-store");
  }
  client = createRegistryClient({ fetcher: remote.fetcher, storage });
  for (const path of Object.keys(remote.resources)) assert.deepEqual(await client.get(path), remote.resources[path]);
  assert.equal(remote.requests.length, 5);
  assert.equal(remote.requests.at(-1).path, "revision.json");
});

test("new registry revision invalidates old status even with unchanged package version", async () => {
  const remote = server();
  const storage = new MemoryStorage();
  storage.setItem("registry-theme", "dark");
  await createRegistryClient({ fetcher: remote.fetcher, storage }).get("package/textkit.json");
  const oldKeys = [...storage.values.keys()].filter(key => key !== "registry-theme");
  remote.revision = "v2";
  remote.resources["package/textkit.json"] = record("v2", "revoked");
  const result = await createRegistryClient({ fetcher: remote.fetcher, storage }).get("package/textkit.json");
  assert.equal(result.status, "revoked");
  for (const key of oldKeys) assert.equal(storage.getItem(key), null);
  assert.equal(storage.getItem("registry-theme"), "dark");
  assert.equal(remote.requests.length, 4);
});

test("corrupt cache is refetched, never rendered", async () => {
  const remote = server();
  const storage = new MemoryStorage();
  await createRegistryClient({ fetcher: remote.fetcher, storage }).get("index.json");
  storage.setItem(storage.key(0), "{not json");
  const result = await createRegistryClient({ fetcher: remote.fetcher, storage }).get("index.json");
  assert.deepEqual(result, index("v1"));
  assert.equal(remote.requests.length, 4);
});

test("storage denial and quota errors do not block live reads", async () => {
  const remote = server();
  const denied = new Proxy({}, { get() { throw new Error("Storage disabled"); } });
  for (const storage of [null, denied]) {
    assert.deepEqual(await createRegistryClient({ fetcher: remote.fetcher, storage }).get("index.json"), index("v1"));
  }
});

test("unconfirmed revision cannot reuse stale active records", async () => {
  const remote = server();
  const storage = new MemoryStorage();
  await createRegistryClient({ fetcher: remote.fetcher, storage }).get("package/textkit.json");
  const client = createRegistryClient({ storage, fetcher: async () => { throw new Error("offline"); } });
  await assert.rejects(client.get("package/textkit.json"), /offline/);
});

test("same-page simultaneous reads share requests", async () => {
  const remote = server();
  const client = createRegistryClient({ fetcher: remote.fetcher, storage: new MemoryStorage() });
  const [first, second] = await Promise.all([client.get("index.json"), client.get("index.json")]);
  assert.deepEqual(first, second);
  assert.equal(remote.requests.length, 2);
});

test("publication race refreshes the pointer before accepting content", async () => {
  const remote = server();
  let calls = 0;
  const client = createRegistryClient({ storage: new MemoryStorage(), fetcher: async (url, options) => {
    if (++calls === 2) {
      remote.revision = "v2";
      remote.resources["index.json"] = index("v2");
    }
    return remote.fetcher(url, options);
  } });
  assert.deepEqual(await client.get("index.json"), index("v2"));
  assert.equal(calls, 4);
});

test("persistent revision mismatch fails without caching", async () => {
  const remote = server();
  remote.resources["index.json"] = index("other");
  const storage = new MemoryStorage();
  const client = createRegistryClient({ fetcher: remote.fetcher, storage });
  await assert.rejects(client.get("index.json"), /Registry changed/);
  assert.equal(storage.length, 0);
});

test("missing packages, invalid data and paths are not cached", async () => {
  const remote = server();
  remote.resources["index.json"].packages = null;
  const storage = new MemoryStorage();
  const client = createRegistryClient({ fetcher: remote.fetcher, storage });
  await assert.rejects(client.get("index.json"), /Invalid registry data/);
  await assert.rejects(client.get("package/missing.json"), error => error.status === 404);
  const count = remote.requests.length;
  await assert.rejects(client.get("../secret.json"), /Invalid registry resource/);
  assert.equal(remote.requests.length, count);
  assert.equal(storage.length, 0);
});
