(async function ({refresh = false, installLocalOverride = false, timeoutMs = 45000} = {}) {
  const result = {
    status: "unavailable",
    reason: "runtime-unavailable",
    identity_valid: null,
    official_publication: "not-probed",
    local_override: "not-installed",
    refresh: {attempted: false, success: null},
    menu_visibility: "not-probed",
    risk_review_service: "not-probed",
  };
  const deadline = Date.now() + Math.min(45000, Math.max(1, Number(timeoutMs) || 45000));
  const timeout = Symbol("timeout");
  async function bounded(operation) {
    let timer;
    try {
      return await Promise.race([
        Promise.resolve().then(operation),
        new Promise((_, reject) => {
          timer = setTimeout(() => reject(timeout), Math.max(0, deadline - Date.now()));
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }
  function dispose(handle) {
    try { handle?.[Symbol.dispose]?.(); } catch (_) {}
  }
  const identitySource = source => source.includes("fullUserHash") &&
    source.includes("_getFullUserHash") && /\.getContext\s*\(/.test(source);
  const published = snapshot => snapshot?.defaultEnableFeatures?.guardian_approval === true;
  let phase = "runtime";
  let observer, subscription, subscriptionClosed = false;
  try {
    const runtimes = new Set();
    const sources = new Set([...document.scripts].filter(script => script.type === "module")
      .map(script => script.src).filter(Boolean));
    for (const source of sources) {
      try {
        const entry = await bounded(() => import(source));
        if (typeof entry.__webpack_require__ === "function" && entry.__webpack_require__.m) {
          runtimes.add(entry.__webpack_require__);
        }
      } catch (_) {}
    }
    if (runtimes.size !== 1) return result;
    const require = [...runtimes][0];
    const factories = Object.entries(require.m).map(([id, factory]) => [id, String(factory)]);
    const services = factories.filter(([, source]) => /\bsetAppServices\s*:/.test(source) &&
      /\bappServices\s*:/.test(source));
    const validators = factories.filter(([, source]) => identitySource(source));
    if (services.length !== 1 || validators.length !== 1) return result;
    const holder = require(services[0][0]).appServices;
    const existing = window.__zhGuardianLocalOverride;
    const service = existing?.service === holder?.statsigEvaluations ? existing.original :
      holder?.statsigEvaluations;
    const checks = Object.values(require(validators[0][0]))
      .filter(value => typeof value === "function" && identitySource(String(value)));
    const client = window.__STATSIG__?.firstInstance;
    if (!service || checks.length !== 1 || !client ||
        typeof service.readExecutionAssignments !== "function") return result;
    const identityValid = () => checks[0](client) === true;
    result.identity_valid = identityValid();
    phase = "publication";
    let assignments = await bounded(() => service.readExecutionAssignments());
    result.official_publication = published(assignments) ? "passed" : "blocked";
    if (result.identity_valid && published(assignments)) {
      return {...result, status: "ready", reason: "official-publication-ready"};
    }
    const localResult = () => ({...result, status: "ready-local", reason: "local-feature-override",
      local_override: "passed", execution_override: "passed", menu_selector: "patched"});
    if (existing?.service === holder?.statsigEvaluations && existing.isActive()) {
      const effective = await bounded(() => holder.statsigEvaluations.readExecutionAssignments());
      if (published(effective)) return localResult();
    }
    if (installLocalOverride) {
      phase = "local-override";
      // This is a local feature default, not a Statsig evaluation or identity override.
      const principal = user => JSON.stringify([user?.userID ?? null,
        user?.customIDs?.account_id ?? null, user?.custom?.auth_method ?? null,
        user?.customIDs?.stableID ?? null]);
      const assignmentPrincipal = identity => JSON.stringify([identity?.userId ?? null,
        identity?.accountId ?? null, identity?.authMethod ?? null, identity?.stableId ?? null]);
      const originalPrincipal = principal(client.getContext().user);
      if (!assignments?.identity || assignments.defaultEnableFeatures == null ||
          assignmentPrincipal(assignments.identity) !== originalPrincipal) {
        return {...result, status: "blocked", reason: "local-principal-not-ready"};
      }
      const selectors = factories.filter(([, source]) => source.includes("statsigEvaluations") &&
        source.includes("onMount") && source.includes(".subscribe(") &&
        /\.hasEvaluations\s*\?\s*[\w$]+\.defaultEnableFeatures\s*:\s*\{\}/.test(source));
      if (selectors.length !== 1) return {...result, reason: "local-selector-unavailable"};
      const selectorExports = Object.values(require(selectors[0][0])).filter(value =>
        value?.cache === "cached" && typeof value.resolve === "function" &&
        typeof value.createSubscriberAtom === "function");
      const deriveFunctions = new Set();
      for (const match of selectors[0][1].matchAll(/\b[\w$]+\(["']([^"']+)["']\)/g)) {
        if (require.m[match[1]]) {
          const derive = require(match[1]).un;
          if (typeof derive === "function") deriveFunctions.add(derive);
        }
      }
      if (selectorExports.length !== 1 || deriveFunctions.size !== 1) {
        return {...result, reason: "local-selector-unavailable"};
      }
      if (existing?.restore) existing.restore();
      const selector = selectorExports[0];
      const resolve = selector.resolve, createSubscriberAtom = selector.createSubscriberAtom;
      const originalSelector = {...selector};
      let facade;
      const isActive = () => window.__STATSIG__?.firstInstance === client &&
        holder.statsigEvaluations === facade && principal(client.getContext().user) === originalPrincipal;
      const merge = features => ({...features, guardian_approval: true});
      const readAssignments = async (...args) => {
        const value = await service.readExecutionAssignments(...args);
        return isActive() && value?.defaultEnableFeatures != null && value.identity &&
          assignmentPrincipal(value.identity) === originalPrincipal ?
          {...value, defaultEnableFeatures: merge(value.defaultEnableFeatures)} : value;
      };
      facade = new Proxy(service, {get(target, key) {
        return key === "readExecutionAssignments" ? readAssignments : Reflect.get(target, key, target);
      }});
      const localSelector = [...deriveFunctions][0](selector.scope, ({get}) => {
        const value = get(originalSelector);
        return isActive() ? merge(value) : value;
      });
      const restore = () => {
        if (holder.statsigEvaluations === facade) holder.statsigEvaluations = service;
        if (selector.resolve === localSelector.resolve) selector.resolve = resolve;
        if (selector.createSubscriberAtom === localSelector.createSubscriberAtom) {
          selector.createSubscriberAtom = createSubscriberAtom;
        }
      };
      try {
        holder.statsigEvaluations = facade;
        selector.resolve = localSelector.resolve;
        selector.createSubscriberAtom = localSelector.createSubscriberAtom;
        window.__zhGuardianLocalOverride = {service: facade, original: service, isActive, restore};
        if (!published(await bounded(() => readAssignments()))) {
          restore();
          return {...result, status: "blocked", reason: "local-principal-not-ready"};
        }
        return localResult();
      } catch (error) {
        restore();
        throw error;
      }
    }
    if (refresh) {
      phase = "refresh";
      result.refresh.attempted = true;
      const refreshed = await bounded(() => client.refreshValuesAsync());
      result.refresh.success = refreshed?.success === true;
      if (["Network", "Cache", "Bootstrap", "NoValues", "Prefetch"].includes(refreshed?.source)) {
        result.refresh.source = refreshed.source;
      }
      result.identity_valid = identityValid();
      if (!result.refresh.success) {
        return {...result, status: "blocked", reason: "evaluation-refresh-failed"};
      }
    }
    if (!result.identity_valid) {
      return {...result, status: "blocked", reason: "evaluation-identity-mismatch"};
    }
    phase = "publication";
    assignments = await bounded(() => service.readExecutionAssignments());
    if (!published(assignments) && refresh) {
      const RpcStub = Object.getPrototypeOf(service)?.constructor;
      if (typeof RpcStub !== "function" || typeof service.subscribe !== "function") {
        return {...result, status: "unavailable", reason: "publication-observer-unavailable"};
      }
      assignments = await bounded(() => new Promise((resolve, reject) => {
        observer = new RpcStub(snapshot => {
          if (snapshot?.hasEvaluations === true && published(snapshot)) resolve(snapshot);
        });
        Promise.resolve().then(() => service.subscribe(observer)).then(handle => {
          if (subscriptionClosed) dispose(handle);
          else subscription = handle;
        }, reject);
      }));
    }
    result.identity_valid = identityValid();
    result.official_publication = published(assignments) ? "passed" : "blocked";
    if (!result.identity_valid) {
      return {...result, status: "blocked", reason: "evaluation-identity-mismatch"};
    }
    return {...result, status: published(assignments) ? "ready" : "blocked",
      reason: published(assignments) ? "official-publication-ready" : "publication-not-ready"};
  } catch (_) {
    // SDK errors may contain request URLs or identity data; retain only the failed phase.
    if (phase === "refresh") result.refresh.success = false;
    return {...result, status: phase === "runtime" ? "unavailable" : "blocked",
      reason: phase === "local-override" ? "local-override-unavailable" :
        phase === "refresh" ? "evaluation-refresh-failed" :
        phase === "publication" ? "publication-not-ready" : "runtime-unavailable"};
  } finally {
    subscriptionClosed = true;
    dispose(subscription);
    dispose(observer);
  }
})
