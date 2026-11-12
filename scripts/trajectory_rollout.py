"""Initialization-only AST proof for the positive trajectory UI rollout.

No package/config writes, application launch, or startup hook. Call discover()
only during census refresh. IDs and webpack module names are derived, not pinned.
Templates deliberately fail closed on new evaluator semantics. Offsets are UTF-16.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess

ROLE = 'feature:codex.trajectory-refresh'
NAME = 'codex.trajectory-refresh'
ROOT = Path(__file__).resolve().parent

# Complete policy-building/evaluation expressions, alpha-normalized by the AST
# matcher. They are not substring markers: every operator and property must match.
BUILDER = '''function(e){let t={};for(let[n,r]of Object.entries(e))!function e(t,n,r,i){if(null!=t[n])throw Error(`Duplicate capability name: ${n}`);if(r.configFeatures?.length===0)throw Error(`Capability configFeatures must not be empty: ${n}`);if(r.settings?.length===0)throw Error(`Capability settings must not be empty: ${n}`);if(r.statsig?.length===0)throw Error(`Capability statsig must not be empty: ${n}`);if(r.supportedClients?.length===0)throw Error(`Capability supportedClients must not be empty: ${n}`);let a=r.supportedClients,s=i.supportedClients;null!=a&&(s=null==s?a:s.filter(e=>a.includes(e)));let o={accessPolicies:[...i.accessPolicies,...null==r.accessPolicy?[]:[r.accessPolicy]],configFeatures:[...i.configFeatures,...r.configFeatures??[]],requiresFirstPartyInference:i.requiresFirstPartyInference||!0===r.requiresFirstPartyInference,settings:[...i.settings,...r.settings??[]],statsig:[...i.statsig,...r.statsig??[]],supportedClients:s};for(let[i,a]of(t[n]=o,Object.entries(r.children??{})))e(t,i,a,o)}(t,n,r,{accessPolicies:[],configFeatures:[],requiresFirstPartyInference:!1,settings:[],statsig:[],supportedClients:void 0});return t}'''
EVALUATOR = '''(e,{get:t})=>{var n;let r=p[e.name];if(null==r||!(null==(n=r).supportedClients||n.supportedClients.includes("electron")))return{isLoading:!1,isError:!1,isCapable:!1};let l=[...r.accessPolicies.map(e=>{let n=c.B[e];return null==n?{isLoading:!1,isError:!0,isCapable:!1}:t(n)}),...r.statsig.map(e=>{let n=t(d.dx,e);return{isLoading:n,isError:!1,isCapable:!n&&t(d.JW,e)}}),...r.settings.map(e=>{let n=t(u.yB),r=t(u.Oe)||!n&&!t(u.dW);return{isLoading:r,isError:n,isCapable:!r&&!n&&!0===(0,u.CN)(t,(0,i.crQ)(e))}}),...r.configFeatures.map(n=>{if(n.clients?.includes("electron")===!1)return{isLoading:!1,isError:!1,isCapable:!0};n.host;let r="default"===n.host?"local":e.hostId;if(null==r)throw Error(`Explicit-host capability requires hostId: ${e.name}`);let i=t(o.u9,r),a=i.isError,s=i.isLoading||!a&&null==i.data,l=i.data?.find(e=>e.name===n.key);return{isLoading:s,isError:a,isCapable:!s&&!a&&l?.enabled!==!1}})];if(r.requiresFirstPartyInference&&t(d.JW,"3683713372")){let e=t(s.uV,{hostId:"local",cwd:null,failClosed:!0}),n=e.isError,r=!n&&null==e.data,i=null==e.data?null:(0,a.Y$)(e.data.config).model_provider;l.push({isLoading:r,isError:n,isCapable:!r&&!n&&(i??"openai")==="openai"})}return 0===l.length?{isLoading:!1,isError:!1,isCapable:!0}:{isLoading:l.some(e=>e.isLoading),isError:l.some(e=>e.isError),isCapable:l.every(e=>e.isCapable)}}'''

SCANNER = r'''
const fs=require('fs'),acorn=require(process.argv[1]);
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const parse=s=>acorn.parse(s,{ecmaVersion:'latest',sourceType:'module'});
const expr=s=>parse('('+s+')').body[0].expression;
const lit=n=>n?.type==='Literal'?n.value:undefined;
const key=p=>p && (p.computed?lit(p.key):p.key.name??lit(p.key));
const prop=(n,k)=>n?.type==='ObjectExpression'&&n.properties.find(p=>key(p)===k)?.value;
const mem=(n,k)=>n?.type==='MemberExpression'&&!n.computed&&n.property.name===k;
const ident=n=>n?.type==='Identifier'?n.name:null;
const unseq=n=>n?.type==='SequenceExpression'&&n.expressions.length===2&&lit(n.expressions[0])===0?n.expressions[1]:n;
const fn=n=>n&&['FunctionExpression','FunctionDeclaration','ArrowFunctionExpression'].includes(n.type);
function children(n){return Object.values(n).flatMap(v=>Array.isArray(v)?v.filter(x=>x?.type):v?.type?[v]:[])}
function walk(n,visit,skip=false){const todo=[n];while(todo.length){const x=todo.pop();visit(x);if(skip&&x!==n&&fn(x))continue;todo.push(...children(x));}}
function all(n,p,skip=false){const out=[];walk(n,x=>{if(p(x))out.push(x)},skip);return out}
// Compare complete ASTs; preserve member/property names, literals and operators.
function canonical(root){const names=new Map();function norm(n,parent,field){if(typeof n==='bigint')return {bigint:String(n)};if(!n||typeof n!=='object')return n;if(Array.isArray(n))return n.map(x=>norm(x,parent,field));if(n.type==='Identifier'){
 const fixed=(parent?.type==='MemberExpression'&&field==='property'&&!parent.computed)||(parent?.type==='Property'&&field==='key'&&!parent.computed);
 if(fixed)return {type:n.type,name:n.name};if(!names.has(n.name))names.set(n.name,names.size);return {type:n.type,name:names.get(n.name)};}
 const o={};for(const k of Object.keys(n).sort())if(!['start','end','raw'].includes(k))o[k]=norm(n[k],n,k);return o;}return JSON.stringify(norm(root));}
const builder=canonical(expr(input.builder)),evaluator=canonical(expr(input.evaluator));
const modules=[],errors=[],registry=[],consumers=[];
for(const [file,source] of input.sources){let tree;try{tree=parse(source)}catch(e){errors.push({file,error:e.message});continue}
 walk(tree,n=>{if(n.type==='Property'&&n.method&&fn(n.value)&&n.value.params.length===3&&n.value.params.every(ident))modules.push({id:String(key(n)),f:n.value,file,source})});}
// Webpack module keys are globally unique, or must be identical duplicate chunks.
const grouped=new Map();for(const m of modules){if(!grouped.has(m.id))grouped.set(m.id,[]);grouped.get(m.id).push(m)}
const unique=id=>{const ms=grouped.get(id)||[];return ms.length&&new Set(ms.map(m=>canonical(m.f))).size===1?ms[0]:null};
function imports(m){const req=ident(m.f.params[2]),map=new Map(),ds=all(m.f,n=>n.type==='VariableDeclarator',true);for(const d of ds)if(ident(d.id)&&ds.filter(x=>ident(x.id)===d.id.name).length===1&&!all(m.f,n=>(n.type==='AssignmentExpression'&&ident(n.left)===d.id.name)||(n.type==='UpdateExpression'&&ident(n.argument)===d.id.name),true).length&&d.init?.type==='CallExpression'&&ident(d.init.callee)===req&&d.init.arguments.length===1&&typeof lit(d.init.arguments[0])==='string')map.set(d.id.name,lit(d.init.arguments[0]));return map;}
function exported(m,name,binding){const req=ident(m.f.params[2]),out=ident(m.f.params[1]);return all(m.f,n=>n.type==='CallExpression'&&mem(n.callee,'d')&&ident(n.callee.object)===req&&ident(n.arguments[0])===out,true).some(n=>n.arguments.slice(1).some(a=>{const p=prop(a,name);return ident(p)===binding||(fn(p)&&ident(p.body)===binding)}));}
for(const m of modules){if(unique(m.id)!==m)continue;
 const declarations=all(m.f,n=>n.type==='VariableDeclarator',true),im=imports(m);
 for(const d of declarations){const call=d.init;if(!ident(d.id)||call?.type!=='CallExpression'||call.arguments.length!==1||canonical(call.callee)!==builder)continue;
 const object=call.arguments[0],entry=prop(object,input.name);if(!entry||entry.properties.length!==1||key(entry.properties[0])!=='statsig')continue;
 // Only a direct root capability: inherited policies cannot be silently dropped.
 const occurrences=all(object,n=>n.type==='Property'&&key(n)===input.name);if(occurrences.length!==1)continue;
 const gates=prop(entry,'statsig');if(gates?.type!=='ArrayExpression'||gates.elements.length!==1)continue;const id=lit(gates.elements[0]);if(typeof id!=='string'||!/^\d+$/.test(id))continue;
 for(const e of declarations){const c=e.init;if(!ident(e.id)||c?.type!=='CallExpression'||c.arguments.length<2)continue;
 const ev=c.arguments[1];if(!fn(ev)||canonical(ev)!==evaluator)continue;
 const reg=all(ev,n=>n.type==='MemberExpression'&&n.computed&&mem(n.property,'name'));
 if(reg.length!==1||ident(reg[0].object)!==d.id.name)continue;
 // Bind positive Statsig JW to the actual SDK value reader, not a lookalike.
 const gateCalls=all(ev,n=>n.type==='CallExpression'&&mem(n.arguments[0],'JW'));
 if(gateCalls.length!==2)continue;const sdkAlias=ident(gateCalls[0].arguments[0].object),sdk=unique(im.get(sdkAlias));
 if(!sdk||gateCalls.some(n=>ident(n.arguments[0].object)!==sdkAlias))continue;
 const sdkDecl=all(sdk.f,n=>n.type==='VariableDeclarator',true).find(n=>n.init?.type==='CallExpression'&&fn(n.init.arguments[1])&&canonical(n.init.arguments[1])===canonical(expr('(e,{get:t})=>t(s)?.getFeatureGate(e,{disableExposureLog:!0}).value??(0,a.wc)(e)?.value??!1')));
 if(!sdkDecl||!exported(sdk,'JW',ident(sdkDecl.id)))continue;
 // Export name is derived from the evaluator binding.
 const ex=[];walk(m.f,n=>{if(n.type==='Property'&&fn(n.value)&&ident(n.value.body)===e.id.name)ex.push(key(n))},true);
 for(const exportName of ex)if(exported(m,exportName,e.id.name))registry.push({id,module:m.id,exportName,file:m.file,offset:entry.start});
 }
 }
}
for(const m of modules){if(unique(m.id)!==m)continue;const im=imports(m);
 for(const f of all(m.f,fn).filter(f=>f!==m.f)){
 const ds=all(f,n=>n.type==='VariableDeclarator',true);
 const bindings=name=>ds.filter(d=>ident(d.id)===name);
 const unchanged=name=>bindings(name).length===1&&!all(f,n=>(n.type==='AssignmentExpression'&&ident(n.left)===name)||(n.type==='UpdateExpression'&&ident(n.argument)===name)).length;
 const safeAlias=name=>name&&!bindings(name).length&&!f.params.some(p=>ident(p)===name)&&!all(f,n=>(n.type==='AssignmentExpression'&&ident(n.left)===name)||(n.type==='UpdateExpression'&&ident(n.argument)===name),true).length;
 for(const d of ds){const v=d.init;if(!ident(d.id)||v?.type!=='BinaryExpression'||v.operator!=='==='||v.right.type!=='UnaryExpression'||v.right.operator!=='!'||lit(v.right.argument)!==0||v.left.type!=='ChainExpression'||!mem(v.left.expression,'isCapable'))continue;
 const call=v.left.expression.object;if(call?.type!=='CallExpression'||call.arguments.length!==2||lit(prop(call.arguments[1],'name'))!==input.name||call.arguments[1].properties.length!==1)continue;
 const hook=unseq(call.callee),select=call.arguments[0];if(!mem(hook,'_U')||im.get(ident(hook.object))!=='zTeN'||!safeAlias(ident(hook.object))||select.type!=='ConditionalExpression'||lit(select.alternate)!==null)continue;
 const cap=select.consequent;if(cap?.type!=='MemberExpression'||cap.computed||!safeAlias(ident(cap.object)))continue;
 // Exact positive standard/not-activity predicate, context obtained from useContext.
 const test=select.test;if(test.type!=='LogicalExpression'||test.operator!=='&&'||test.left.type!=='BinaryExpression'||test.left.operator!=='==='||lit(test.left.left)!=='standard'||test.right.type!=='UnaryExpression'||test.right.operator!=='!')continue;
 const activity=bindings(ident(test.right.argument));if(activity.length!==1)continue;const a=activity[0].init;
 if(a?.type!=='BinaryExpression'||a.operator!=='==='||lit(a.left)!=='activity')continue;
 const contexts=bindings(ident(a.right));if(contexts.length!==1)continue;const ctx=contexts[0],cc=ctx.init,react=unseq(cc?.callee);
 if(cc?.type!=='CallExpression'||!mem(react,'useContext')||im.get(ident(react.object))!=='zd8w'||!safeAlias(ident(react.object))||cc.arguments.length!==1)continue;
 if(!unchanged(d.id.name)||!unchanged(ctx.id.name)||!unchanged(activity[0].id.name))continue;
 // Source positions differ: compare the actual context expression by source text.
 const sinks=all(f,n=>n.type==='CallExpression'&&['jsx','jsxs'].some(k=>mem(unseq(n.callee),k))&&im.get(ident(unseq(n.callee).object))==='ABep'&&safeAlias(ident(unseq(n.callee).object))&&m.source.slice(n.arguments[0]?.start,n.arguments[0]?.end)===m.source.slice(cc.arguments[0].start,cc.arguments[0].end),true);
 if(!sinks.some(n=>{const p=prop(n.arguments[1],'value');return p?.type==='ConditionalExpression'&&ident(p.test)===d.id.name&&lit(p.consequent)==='chat-refresh'&&ident(p.alternate)===ctx.id.name}))continue;
 for(const r of registry)if(im.get(ident(cap.object))===r.module&&cap.property.name===r.exportName)consumers.push({...r,consumer_file:m.file,consumer_offset:d.start,offset_unit:'UTF-16 code units',rule:'root-capability-positive-sdk-value-and-context-sink'});
 }
 }
}
process.stdout.write(JSON.stringify({evidence:consumers,errors,registry}));
'''


def discover(sources, node=None):
    """Return (found, audit); never run this from launcher startup.

    Parse failures, ambiguous registries and missing consumer proofs fail closed.
    All sources are needed to resolve module imports (no nearest-ID matching).
    """
    runtime = node or shutil.which('node')
    if not runtime:
        raise RuntimeError('Node.js is required for trajectory AST review')
    entries = [(file, text) for file, text in sources
               if NAME in text or 'getFeatureGate' in text or 'chat-refresh' in text]
    payload = dict(sources=entries, name=NAME, builder=BUILDER, evaluator=EVALUATOR)
    result = subprocess.run([str(runtime), '-e', SCANNER, str(ROOT / 'vendor/acorn.cjs')],
                            input=json.dumps(payload, ensure_ascii=True), capture_output=True,
                            text=True, encoding='utf-8', timeout=180,
                            creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError('Trajectory AST review failed: ' + result.stderr[:1500])
    audit = json.loads(result.stdout)
    ids = {row['id'] for row in audit['evidence']}
    registry_ids = {row['id'] for row in audit['registry']}
    found = {ROLE: next(iter(ids))} if len(ids) == 1 and ids == registry_ids and not audit['errors'] else {}
    audit['decision'] = 'approve' if found else 'hold'
    audit['scope'] = 'rollout-gate-only; preserve capability/auth/config and UI predicates'
    return found, audit
