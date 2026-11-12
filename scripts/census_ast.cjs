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
    const parents = new WeakMap();
    function positiveRegistry(object) {
      const array = parents.get(object), declaration = array && parents.get(array);
      if (array?.type !== 'ArrayExpression' || declaration?.type !== 'VariableDeclarator' || declaration.id.type !== 'Identifier') return false;
      let scope = parents.get(declaration);
      while (scope && !/Function/.test(scope.type) && scope.type !== 'Program') scope = parents.get(scope);
      if (!scope) return false;
      const name = declaration.id.name;
      // Bind this exact array to a positive gateName -> featureKey=true converter.
      const loops = [];
      const todo = [scope];
      let bindings = 0;
      while (todo.length) {
        const n = todo.pop();
        if (n.type === 'VariableDeclarator' && n.id.type === 'Identifier' && n.id.name === name) bindings++;
        if (n.type === 'ForOfStatement' && n.right.type === 'Identifier' && n.right.name === name) loops.push(n);
        for (const v of Object.values(n)) {
          if (Array.isArray(v)) { for (const c of v) if (c?.type) todo.push(c); }
          else if (v?.type) todo.push(v);
        }
      }
      if (bindings !== 1 || loops.length !== 1) return false;
      const loop = loops[0], variable = loop.left.declarations?.[0]?.id?.name;
      const body = loop.body.type === 'ExpressionStatement' ? loop.body.expression : null;
      if (!variable || body?.type !== 'LogicalExpression' || body.operator !== '&&') return false;
      const call = body.left, assignment = body.right;
      const arg = call?.type === 'CallExpression' ? call.arguments.at(-1) : null;
      const index = assignment?.left?.property;
      return arg?.type === 'MemberExpression' && !arg.computed && arg.object.name === variable && arg.property.name === 'gateName'
        && assignment?.type === 'AssignmentExpression' && assignment.operator === '='
        && assignment.left.type === 'MemberExpression' && assignment.left.computed
        && index?.type === 'MemberExpression' && !index.computed && index.object.name === variable && index.property.name === 'featureKey'
        && assignment.right.type === 'UnaryExpression' && assignment.right.operator === '!'
        && assignment.right.argument.type === 'Literal' && assignment.right.argument.value === 0;
    }
    const pending = [[tree, null]];
    while (pending.length) {
      const [node, parent] = pending.pop();
      if (parent) parents.set(node, parent);
      if (node.type === 'ObjectExpression') {
        const props = node.properties.filter(p => p.type === 'Property');
        const get = name => props.find(p => key(p) === name)?.value;
        const gate = get('gateName'), feature = get('featureKey');
        if (gate && feature) add('named-gate-feature', literal(feature), gate, literal(gate), {positive_registry:positiveRegistry(node)});
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
