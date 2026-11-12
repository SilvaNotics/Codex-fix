// Acorn 8.15.0 (vendored, MIT) parses syntax; never executes package code.
const acorn = require('./vendor/acorn.cjs');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', s => { input += s; });
process.stdin.on('end', () => {
  const rows = [], errors = [];
  const methods = new Set(['getFeatureGate','checkGate','getLayer','getExperiment','getDynamicConfig']);
  for (const [file, source] of JSON.parse(input)) {
    const literal = n => n?.type === 'Literal' && ['string','number'].includes(typeof n.value) ? String(n.value)
      : n?.type === 'TemplateLiteral' && !n.expressions.length ? n.quasis[0].value.cooked : null;
    const key = p => p && (!p.computed && p.key.type === 'Identifier' ? p.key.name : literal(p.key));
    const add = (kind, name, node, id, extra={}) => rows.push({kind,name,id,file,offset:node.start,
      context:source.slice(Math.max(0,node.start-80),Math.min(source.length,node.end+80)),
      classification:id === null ? 'unclassified' : 'unknown', ...extra});
    let tree;
    try { tree = acorn.parse(source, {ecmaVersion:'latest',sourceType:'module',allowHashBang:true}); }
    catch (error) { errors.push({file,offset:error.pos,error:error.message}); continue; }
    // Iterative traversal avoids stack overflow on deeply minified expressions.
    const pending = [[tree, null]];
    while (pending.length) {
      const [node, parent] = pending.pop();
      if (node.type === 'ObjectExpression') {
        const props = node.properties.filter(p => p.type === 'Property');
        const get = name => props.find(p => key(p) === name)?.value;
        const gate = get('gateName'), feature = get('featureKey');
        if (gate && feature) add('named-gate-feature', literal(feature), gate, literal(gate));
        const statsig = get('statsig');
        if (statsig) {
          const name = parent?.type === 'Property' ? key(parent) : null;
          if (statsig.type === 'ArrayExpression') {
            for (const n of statsig.elements) if(n) add('capability-statsig',name,n,literal(n));
          } else add('capability-statsig',name,statsig,null);
        }
      }
      if (node.type === 'CallExpression' && node.callee.type === 'MemberExpression') {
        const member = node.callee;
        const method = member.computed ? literal(member.property) : member.property.name;
        if (methods.has(method)) add('sdk-call',method,node,literal(node.arguments[0]));
        else if (member.computed && method === null) add('computed-call',null,node,null);
      }
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) { for (const child of value) if(child?.type) pending.push([child,node]); }
        else if (value?.type) pending.push([value,node]);
      }
    }
  }
  rows.sort((a,b) => a.file.localeCompare(b.file) || a.offset-b.offset || a.kind.localeCompare(b.kind));
  process.stdout.write(JSON.stringify({rows,errors}));
});
