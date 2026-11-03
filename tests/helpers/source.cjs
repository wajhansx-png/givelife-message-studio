/* Pull code out of a browser script by name, so tests survive reformatting.
   The scripts are plain browser files (no modules), so tests evaluate just the pieces they need. */
const acorn = require('acorn');

const parse = (source) => acorn.parse(source, { ecmaVersion: 'latest', sourceType: 'script' });

const walk = (node, visit) => {
  if (!node || typeof node.type !== 'string') return;
  visit(node);
  for (const key of Object.keys(node)) {
    const child = node[key];
    if (Array.isArray(child)) child.forEach((item) => walk(item, visit));
    else if (child && typeof child.type === 'string') walk(child, visit);
  }
};

const find = (source, test) => {
  let found = null;
  walk(parse(source), (node) => {
    if (!found && test(node)) found = node;
  });
  return found;
};

/** Source of `function name(...) {...}` or `async function name(...) {...}`. */
const extractFunction = (source, name) => {
  const node = find(source, (n) => n.type === 'FunctionDeclaration' && n.id.name === name);
  if (!node) throw new Error(`function not found: ${name}`);
  return source.slice(node.start, node.end);
};

/** Source of the `let/const/var` statement that declares `name`. */
const extractDeclaration = (source, name) => {
  const node = find(
    source,
    (n) => n.type === 'VariableDeclaration' && n.declarations.some((d) => d.id.name === name),
  );
  if (!node) throw new Error(`declaration not found: ${name}`);
  return source.slice(node.start, node.end);
};

/** Several named functions joined, in the order asked for. */
const extractFunctions = (source, ...names) =>
  names.map((n) => extractFunction(source, n)).join('\n');

/** Source of an assignment such as `regen.onclick = async () => {...}`, matched on its left side. */
const extractAssignment = (source, left) => {
  const wanted = left.replace(/\s+/g, '');
  const node = find(
    source,
    (n) =>
      n.type === 'AssignmentExpression' &&
      source.slice(n.left.start, n.left.end).replace(/\s+/g, '') === wanted,
  );
  if (!node) throw new Error(`assignment not found: ${left}`);
  return source.slice(node.start, node.end);
};

/** The source with all whitespace removed, for "does this call exist" checks that ignore layout. */
const compact = (source) => source.replace(/\s+/g, '');

module.exports = {
  extractFunction,
  extractFunctions,
  extractDeclaration,
  extractAssignment,
  compact,
};
