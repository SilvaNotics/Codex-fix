"""Exercise guardian recovery against the SDK and publication boundaries."""
import asyncio
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_policy


ASSET = Path(__file__).resolve().parents[1] / 'assets' / 'guardian_approval.js'

RUNTIME = r'''
const scenario = SCENARIO;
const stats = {refreshes: 0, publications: 0, disposed: 0};
let user = {customIDs: {stableID: 'current'}};
let cachedHash = scenario.identityValid ? 'current' : 'previous';
let published = scenario.published ? {guardian_approval: true} : {};
let listener;
const sdk = {
  loadingStatus: 'Ready',
  getContext: () => ({user, values: {}}),
  dataAdapter: {getDataSync: () => ({fullUserHash: cachedHash})},
  async refreshValuesAsync() {
    stats.refreshes++;
    if (scenario.refreshThrows) throw Error('private URL?token=secret');
    if (!scenario.refreshSucceeds) return {success: false, source: 'Cache',
      error: Error('private URL?token=secret')};
    cachedHash = 'current';
    if (!scenario.publicationBlocked) {
      if (scenario.delayedPublication) {
        listener = () => { published = {guardian_approval: true}; stats.publications++; };
      } else {
        published = {guardian_approval: true};
        stats.publications++;
      }
    }
    return {success: true, source: 'Network'};
  },
};
class RpcStub {
  constructor(callback) { this.callback = callback; }
  [Symbol.dispose]() { stats.disposed++; }
}
class Service extends RpcStub {
  async readExecutionAssignments() { return {
    identity: {userId: null, accountId: null, authMethod: null,
      stableId: scenario.wrongPrincipal ? 'other' : 'current'},
    defaultEnableFeatures: {...published, unrelated: false}, values: {personality: {}},
  }; }
  async subscribe(observer) {
    if (listener) listener();
    observer.callback({hasEvaluations: true, defaultEnableFeatures: published});
    return {[Symbol.dispose]() { stats.disposed++; }};
  }
}
const services = {appServices: {statsigEvaluations: new RpcStub()}};
Object.assign(services.appServices.statsigEvaluations, {
  readExecutionAssignments: Service.prototype.readExecutionAssignments,
  subscribe: Service.prototype.subscribe,
});
function identityMatches(client) {
  const {user} = client.getContext();
  return client.dataAdapter.getDataSync(user).fullUserHash === _getFullUserHash(user);
}
function _getFullUserHash(user) { return user.customIDs.stableID; }
function derived(scope, read) {
  const atom = {cache: 'cached', scope, resolve: () => read({get: a => a.resolve()})};
  atom.createSubscriberAtom = () => atom.resolve();
  return atom;
}
const selector = derived({}, () => scenario.hasEvaluations ? {...published, unrelated: false} : {});
export function __webpack_require__(id) {
  if (id === 'services-renamed') return services;
  if (id === 'identity-renamed') return {checkRenamed: identityMatches};
  if (id === 'selector-renamed') return {renamedFeatures: selector};
  if (id === 'atoms-renamed') return {un: derived};
  throw Error('Unexpected module');
}
__webpack_require__.m = {
  'atoms-renamed': function() { return {un: derived}; },
  'services-renamed': function() { return {appServices: {}, setAppServices: function() {}}; },
  'identity-renamed': function() {
    const check = client => {
      const {user} = client.getContext();
      return client.dataAdapter.getDataSync(user).fullUserHash === _getFullUserHash(user);
    };
  },
  'selector-renamed': function() {
    const state = __webpack_require__('atoms-renamed');
    const onMount = () => services.appServices.statsigEvaluations.subscribe();
    const compute = t => t.hasEvaluations ? t.defaultEnableFeatures : {};
  },
};
if (scenario.ambiguous) __webpack_require__.m['second-service'] =
  __webpack_require__.m['services-renamed'];
if (scenario.bootstrapModule) __webpack_require__.m['bootstrap-renamed'] =
  function() { services.setAppServices(services.appServices); };
globalThis.window = {__STATSIG__: {firstInstance: sdk}};
globalThis.guardianStats = stats;
globalThis.guardianFixture = {services, selector, sdk};
'''


class GuardianRuntimeTests(unittest.TestCase):
    def run_probe(self, scenario, refresh=True, local=False):
        self.assertTrue(ASSET.is_file(), 'Guardian runtime recovery is missing')
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'runtime.mjs'
            runtime.write_text(RUNTIME.replace('SCENARIO', json.dumps(scenario)), encoding='utf-8')
            url = runtime.as_uri()
            driver = ('globalThis.document={scripts:[{type:"module",src:' + json.dumps(url) + '}]};\n'
                      'await import(' + json.dumps(url) + ');\nconst probe=' +
                      ASSET.read_text(encoding='utf-8') + ';\n'
                      'const result=await probe({refresh:' + json.dumps(refresh) +
                      ',installLocalOverride:' + json.dumps(local) + ',timeoutMs:100});\n'
                      'const local=' + json.dumps(local) + ';const f=globalThis.guardianFixture;\n'
                      'const assignments=await f.services.appServices.statsigEvaluations.readExecutionAssignments();\n'
                      'const features=f.selector.resolve();\n'
                      'const readonly=local?await probe({refresh:false}):null;\n'
                      'if(local)f.sdk.getContext=()=>({user:{customIDs:{stableID:"changed"}},values:{}});\n'
                      'const afterIdentityChange=f.selector.resolve();\n'
                      'console.log(JSON.stringify({result,stats:globalThis.guardianStats,assignments,features,readonly,afterIdentityChange}));')
            completed = subprocess.run(['node', '--input-type=module', '-e', driver],
                                       text=True, capture_output=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr[:1500])
            return json.loads(completed.stdout)

    def test_refresh_recovers_stale_identity_and_publication(self):
        output = self.run_probe({'refreshSucceeds': True})
        self.assertEqual(output['result']['status'], 'ready')
        self.assertTrue(output['result']['identity_valid'])
        self.assertEqual(output['result']['official_publication'], 'passed')
        self.assertEqual(output['stats']['refreshes'], 1)
        self.assertEqual(output['stats']['publications'], 1)

    def test_healthy_publication_skips_refresh(self):
        output = self.run_probe({'identityValid': True, 'published': True})
        self.assertEqual(output['result']['status'], 'ready')
        self.assertEqual(output['stats']['refreshes'], 0)

    def test_valid_identity_with_stale_publication_refreshes(self):
        output = self.run_probe({'identityValid': True, 'refreshSucceeds': True})
        self.assertEqual(output['result']['official_publication'], 'passed')
        self.assertEqual(output['stats']['refreshes'], 1)

    def test_failed_refresh_does_not_publish_or_leak_error_details(self):
        for scenario in ({}, {'refreshThrows': True}):
            with self.subTest(scenario=scenario):
                output = self.run_probe(scenario)
                self.assertEqual(output['result']['status'], 'blocked')
                self.assertEqual(output['result']['reason'], 'evaluation-refresh-failed')
                self.assertFalse(output['result']['identity_valid'])
                self.assertEqual(output['stats']['publications'], 0)
                self.assertNotIn('secret', json.dumps(output))

    def test_read_only_probe_never_refreshes(self):
        output = self.run_probe({}, refresh=False)
        self.assertEqual(output['stats']['refreshes'], 0)
        self.assertEqual(output['result']['reason'], 'evaluation-identity-mismatch')

    def test_delayed_official_publication_uses_subscription_and_disposes(self):
        output = self.run_probe({'refreshSucceeds': True, 'delayedPublication': True})
        self.assertEqual(output['result']['status'], 'ready')
        self.assertEqual(output['stats']['disposed'], 2)

    def test_publication_timeout_remains_blocked_and_disposes(self):
        output = self.run_probe({'refreshSucceeds': True, 'publicationBlocked': True})
        self.assertEqual(output['result']['status'], 'blocked')
        self.assertEqual(output['result']['reason'], 'publication-not-ready')
        self.assertEqual(output['stats']['disposed'], 2)

    def test_ambiguous_runtime_is_not_used(self):
        output = self.run_probe({'ambiguous': True})
        self.assertEqual(output['result']['status'], 'unavailable')
        self.assertEqual(output['stats']['refreshes'], 0)

    def test_bootstrap_references_are_not_mistaken_for_service_exports(self):
        output = self.run_probe({'bootstrapModule': True, 'refreshSucceeds': True})
        self.assertEqual(output['result']['status'], 'ready')

    def test_gate_alone_cannot_pass_launcher_verification(self):
        module = test_policy.PolicyTests().configure(
            '{gateName:"805",featureKey:"guardian_approval"}')
        state = {'patched': True, 'gates': {'805': True}}
        self.assertIn('guardian-publication', module.verification_failures(state))
        state['guardian_approval'] = {'status': 'ready', 'official_publication': 'passed'}
        self.assertEqual(module.verification_failures(state), [])

    def test_offline_override_reaches_menu_and_execution_without_refresh(self):
        output = self.run_probe({}, refresh=False, local=True)
        self.assertEqual(output['result']['status'], 'ready-local')
        self.assertEqual(output['result']['official_publication'], 'blocked')
        self.assertEqual(output['result']['local_override'], 'passed')
        self.assertFalse(output['result']['identity_valid'])
        self.assertEqual(output['stats']['refreshes'], 0)
        self.assertEqual(output['stats']['publications'], 0)
        self.assertTrue(output['features']['guardian_approval'])
        self.assertEqual(output['assignments']['defaultEnableFeatures'],
                         {'unrelated': False, 'guardian_approval': True})
        self.assertEqual(output['assignments']['identity']['stableId'], 'current')
        self.assertEqual(output['assignments']['values'], {'personality': {}})
        self.assertEqual(output['readonly']['status'], 'ready-local')
        self.assertNotIn('guardian_approval', output['afterIdentityChange'])

    def test_offline_override_refuses_different_main_process_principal(self):
        output = self.run_probe({'wrongPrincipal': True}, refresh=False, local=True)
        self.assertNotEqual(output['result']['status'], 'ready-local')
        self.assertNotIn('guardian_approval', output['features'])
        self.assertEqual(output['stats']['refreshes'], 0)

    def test_verified_local_override_can_pass_without_official_publication(self):
        module = test_policy.PolicyTests().configure(
            '{gateName:"805",featureKey:"guardian_approval"}')
        state = {'patched': True, 'gates': {'805': True}, 'guardian_approval': {
            'status': 'ready-local', 'official_publication': 'blocked', 'local_override': 'passed'}}
        self.assertEqual(module.verification_failures(state), [])

    def test_launcher_installs_offline_but_verify_only_does_not(self):
        from unittest.mock import AsyncMock
        module = test_policy.PolicyTests().configure(
            '{gateName:"805",featureKey:"guardian_approval"}')
        source = ASSET.read_text(encoding='utf-8')
        for verify_only in (False, True):
            with self.subTest(verify_only=verify_only):
                rpc = type('Rpc', (), {'evaluate': AsyncMock(return_value={'status': 'ready-local'})})()
                result = asyncio.run(module.probe_guardian(rpc, verify_only=verify_only))
                self.assertEqual(result['status'], 'ready-local')
                expression = rpc.evaluate.call_args.args[0]
                self.assertTrue(expression.startswith(source + '('))
                options = json.loads(expression[len(source) + 1:-1])
                self.assertFalse(options['refresh'])
                self.assertIs(options['installLocalOverride'], not verify_only)
                self.assertTrue(rpc.evaluate.call_args.kwargs['await_promise'])


if __name__ == '__main__':
    unittest.main()
