"""Read-only Guardian diagnosis. No evaluation, config, policy or mode writes.

Integration: evaluate DIAGNOSTIC_JS with the existing CdpSession after UI mount,
then include classify(result) in verification.json. This is NOT an enablement
patch: do not treat a true SDK gate as a visible-menu acceptance result.
"""

DIAGNOSTIC_JS = r'''(async () => {
 const scripts = [...document.scripts].map(s => s.src).filter(Boolean);
 let r;
 for (const src of scripts) {
   const module = await import(src);
   if (typeof module.__webpack_require__ === 'function') {
     r = module.__webpack_require__; break;
   }
 }
 if (!r) throw Error('Renderer runtime unavailable');
 const client = window.__STATSIG__?.firstInstance;
 if (!client) throw Error('Statsig client unavailable');
 const scope = r('OWtl').u;
 let chain, visits = 0;
 function walk(f) {
   if (!f || chain || ++visits > 30000) return;
   const v = f.memoizedProps?.value;
   if (v instanceof Map && v.has(scope.id)) {chain = v; return;}
   walk(f.child); walk(f.sibling);
 }
 walk(window.__codexRoot?._internalRoot?.current);
 if (!chain) throw Error('Mounted app scope unavailable');
 const node = chain.get(scope.id);
 const read = a => node.store.get(a.resolve(node, chain));
 const publication = read(r('jMec').L);
 const features = read(r('jMec').B);
 const ctx = client.getContext();
 const cached = client.dataAdapter.getDataSync(ctx.user);
 const expectedHash = r('gXxh')._getFullUserHash(ctx.user);
 const queries = node.queryClient.getQueryCache().getAll();
 const configs = queries.filter(q => q.queryKey[0] === 'config' && q.queryKey[1] === 'effective');
 const requirements = queries.find(q => q.queryKey[0] === 'config' && q.queryKey[1] === 'requirements')?.state.data?.requirements ?? null;
 const selectors = configs.map(q => {
   const config = q.state.data?.config;
   const inputs = {isConfigDataPending:q.state.status !== 'success', requirements,
     resolvedConfig:config, isGuardianApprovalEnabledByStatsig:features?.guardian_approval === true,
     isGuardianDefaultEnabledByStatsig:false, showFullAccessInComposer:true};
   return {explicitGuardian:config?.features?.guardian_approval ?? null,
     selected:r('BFUY').lS(inputs),
     configTrueOnly:r('BFUY').lS({...inputs,resolvedConfig:{...config,
       features:{...config?.features,guardian_approval:true}}})};
 });
 const menus = [...document.querySelectorAll('[role=menu]')].map(m => ({
   text:m.textContent, visible:m.getClientRects().length > 0,
   items:[...m.querySelectorAll('[role^=menuitem]')].map(i => i.textContent)}));
 return {scope:'guardian-read-only-diagnosis', sdkReady:client.loadingStatus === 'Ready',
   valuesPresent:ctx.values != null, valuesKeys:Object.keys(ctx.values ?? {}),
   gate:client.getFeatureGate('3902016271').value,
   officialUserMatch:r('Qg7S').z(client),
   cacheUserHashMatches:cached?.fullUserHash === expectedHash,
   hasEvaluations:publication?.hasEvaluations ?? null,
   publishedGuardian:features?.guardian_approval === true,
   selectors, modes:read(r('NvK2').mW), requirements, menus,
   trigger:document.querySelector('button[data-composer-navigation-target=permissions]')?.textContent ?? null,
   riskReviewService:'not-probed'};
})()'''


def classify(state):
    """Keep publication, displayed menu and service claims separate."""
    menus = [m for m in state.get('menus', []) if m.get('visible')]
    visible = any('帮我批准' in m.get('text', '') or 'Approve for me' in m.get('text', '')
                  for m in menus)
    result = {
        'verification_scope': 'guardian-menu-and-publication',
        'menu_visibility': ('visible' if visible else 'absent') if menus else 'not-probed',
        'official_publication': state.get('hasEvaluations'),
        'risk_review_service': 'not-probed',
        'enablement_patch_available': False,
    }
    if visible:
        result['limitation'] = None
    elif state.get('hasEvaluations') is False and state.get('cacheUserHashMatches') is False:
        result['limitation'] = 'official-evaluations-rejected-current-user-cache-mismatch'
    else:
        result['limitation'] = 'no-verified-mode-preserving-enablement-path'
    return result
